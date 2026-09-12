import sys
import time
from pathlib import Path

import re
from typing import Callable, Tuple, List

# Ensure project root is in sys.path when invoked directly
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

MAX_TOOL_ITERATIONS = 10  # Guard against infinite LLM tool call loops
from kimiko.core.logger import get_logger
from kimiko.core.memory.memory_service import MemoryService
from kimiko.core.gemini.adapter import GeminiAdapter

logger = get_logger("turn_engine")


def parse_bilingual(text: str) -> Tuple[str, str]:
    """Parse text containing [EN] ... [VI] ... tags.

    Returns (speech_text_en, subtitle_text_vi).
    If tags are missing, fallback to raw text for both.
    """
    en_match = re.search(r"\[EN\]\s*(.*?)(?=\[VI\]|$)", text, re.DOTALL | re.IGNORECASE)
    vi_match = re.search(r"\[VI\]\s*(.*?)(?=\[EN\]|$)", text, re.DOTALL | re.IGNORECASE)
    
    en_text = en_match.group(1).strip() if en_match else ""
    vi_text = vi_match.group(1).strip() if vi_match else ""
    
    if not en_text and not vi_text:
        return text.strip(), text.strip()
    return (en_text or vi_text), (vi_text or en_text)


def run_turn(
    user_text: str,
    session_id: int,
    persona: str,
    memory: MemoryService,
    gemini: GeminiAdapter,
    tools: list[dict],
    on_sentence: Callable[[str, str], None],
    on_action: Callable[[str, dict], dict],
) -> str:
    """Execute a complete conversational turn including memory context retrieval,
    Gemini Interactions streaming, incremental bilingual sentence dispatch, tool action calling,
    and turn history persistence.
    """
    t_turn_start = time.time()

    # 0. Validate user text
    if not user_text or not user_text.strip():
        logger.warning("Received empty user input, skipping turn.")
        return ""

    user_text = user_text.strip()
    logger.info(f"=== START CONVERSATION TURN (Session #{session_id}) ===")
    logger.info(f"User Input: {user_text!r}")

    # 1. Retrieve context & build system prompt from MemoryService
    try:
        t_mem_start = time.time()
        context = memory.get_context(user_text)
        system_instruction = memory.build_system_prompt(persona, context)
        facts_cnt = len(context.get("facts", []))
        turns_cnt = len(context.get("recent_turns", []))
        logger.info(
            f"Memory context retrieved in {time.time() - t_mem_start:.2f}s: "
            f"{facts_cnt} relevant facts, {turns_cnt} recent turns."
        )
        logger.debug(f"Full system instruction ({len(system_instruction)} chars): {system_instruction[:300]}...")
    except Exception as e:
        logger.error(f"Failed to build context from memory: {e}", exc_info=True)
        system_instruction = persona

    # 2. Start Gemini turn stream
    try:
        current_stream = gemini.run_turn(
            input_text=user_text,
            system_instruction=system_instruction,
            tools=tools,
            thinking_level=None
        )
    except Exception as e:
        logger.error(f"Gemini API turn failed: {e}", exc_info=True)
        fallback_response = "[EN] Sorry, I encountered a connection issue.\n[VI] Xin lỗi, mình đang gặp sự cố kết nối."
        en_fallback, vi_fallback = parse_bilingual(fallback_response)
        try:
            on_sentence(en_fallback, vi_fallback)
        except Exception as cb_err:
            logger.error(f"Fallback on_sentence callback error: {cb_err}")
        return fallback_response

    # 3. Initialize buffers and tracking
    full_response_text = ""
    sentence_buffer = ""
    current_interaction_id = None
    sentence_count = 0
    iteration_loop = 0

    while True:
        iteration_loop += 1
        pending_tool_calls = []
        logger.debug(f"Parsing stream events (iteration #{iteration_loop})...")

        try:
            for event_type, data in gemini.parse_text(current_stream):
                if event_type == "interaction_id":
                    current_interaction_id = data
                    logger.debug(f"Tracked interaction_id: {current_interaction_id}")
                
                elif event_type == "text":
                    full_response_text += data
                    sentence_buffer += data
                    
                    # Check if sentence_buffer contains a complete bilingual unit:
                    if "[VI]" in sentence_buffer.upper():
                        vi_part = sentence_buffer.upper().split("[VI]", 1)[1]
                        if "\n" in vi_part:
                            en_text, vi_text = parse_bilingual(sentence_buffer)
                            if en_text or vi_text:
                                sentence_count += 1
                                logger.info(
                                    f"Sentence #{sentence_count} completed -> "
                                    f"[EN]: {en_text!r} | [VI]: {vi_text!r}"
                                )
                                try:
                                    on_sentence(en_text, vi_text)
                                except Exception as e:
                                    logger.error(f"on_sentence callback error: {e}", exc_info=True)
                            sentence_buffer = ""
                
                elif event_type == "tool_call":
                    if isinstance(data, dict):
                        pending_tool_calls.append(data)
                elif event_type == "error":
                    logger.error(f"Stream returned error event: {data}. Aborting stream parsing.")
                    break
        except Exception as e:
            logger.error(f"Stream parsing error: {e}", exc_info=True)
            break

        # Guard: stop if too many tool iterations
        if iteration_loop >= MAX_TOOL_ITERATIONS:
            logger.error(f"Reached MAX_TOOL_ITERATIONS ({MAX_TOOL_ITERATIONS}). Breaking to prevent infinite loop.")
            break

        # 4. Handle tool calls: execute action and continue interaction
        if pending_tool_calls:
            logger.info(f"Received {len(pending_tool_calls)} pending tool call(s) to execute.")
            for tool in pending_tool_calls:
                tool_name = tool.get("name", "unknown_action")
                tool_args = tool.get("arguments", {})
                tool_id = tool.get("id", "")

                logger.info(f"Invoking action handler: '{tool_name}' with args {tool_args}")
                t_tool_start = time.time()
                try:
                    tool_result = on_action(tool_name, tool_args)
                    logger.info(
                        f"Action '{tool_name}' executed in {time.time() - t_tool_start:.2f}s: {tool_result}"
                    )
                except Exception as e:
                    logger.error(f"Tool execution failed for '{tool_name}': {e}", exc_info=True)
                    tool_result = {"status": "error", "message": str(e)}
                
                if not current_interaction_id:
                    logger.warning(f"Missing current_interaction_id; skipping continuation for {tool_name}")
                    pending_tool_calls = []
                    break

                # Feed result back to continue generation
                try:
                    current_stream = gemini.continue_with_tool_result(
                        previous_id=current_interaction_id,
                        tool_call_id=tool_id,
                        tool_name=tool_name,
                        result=tool_result or {"status": "ok"}
                    )
                except Exception as e:
                    logger.error(f"continue_with_tool_result failed for '{tool_name}': {e}", exc_info=True)
                    pending_tool_calls = []
                    break

            if pending_tool_calls:
                continue
        break
    
    # 5. Flush any remaining text in buffer
    if sentence_buffer.strip():
        en_text, vi_text = parse_bilingual(sentence_buffer)
        if en_text or vi_text:
            sentence_count += 1
            logger.info(
                f"Sentence #{sentence_count} (final buffer) -> [EN]: {en_text!r} | [VI]: {vi_text!r}"
            )
            try:
                on_sentence(en_text, vi_text)
            except Exception as e:
                logger.error(f"Final on_sentence callback error: {e}", exc_info=True)

    # 5.1 Guarantee spoken response if no sentences were emitted (e.g. tool-only or silent response)
    if sentence_count == 0:
        logger.warning("No speech generated during turn. Providing automatic spoken acknowledgment.")
        fallback_msg = "[EN] I hear you!\n[VI] Mình nghe rõ rồi nè!"
        en_text, vi_text = parse_bilingual(fallback_msg)
        try:
            on_sentence(en_text, vi_text)
            sentence_count += 1
            full_response_text = fallback_msg
        except Exception as e:
            logger.error(f"Fallback on_sentence error: {e}", exc_info=True)

    # 6. Record turns to MemoryDB (both user and assistant)
    try:
        t_rec = time.time()
        memory.record_turn(role="user", content=user_text, session_id=session_id)
        if full_response_text.strip():
            memory.record_turn(role="assistant", content=full_response_text, session_id=session_id)
        logger.info(f"Persisted conversational turn to MemoryDB ({time.time() - t_rec:.2f}s).")
    except Exception as e:
        logger.error(f"Failed to persist turns to memory: {e}", exc_info=True)

    elapsed_turn = time.time() - t_turn_start
    logger.info(
        f"=== COMPLETED CONVERSATION TURN in {elapsed_turn:.2f}s "
        f"({sentence_count} sentences dispatched) ==="
    )
    return full_response_text
