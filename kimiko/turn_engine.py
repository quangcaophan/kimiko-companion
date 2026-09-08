import sys
from pathlib import Path

# Prevent Windows CP1252 emoji crash in console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure workspace root is in sys.path when running turn_engine.py directly
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


import re
from typing import Callable, Tuple, List
from kimiko.core.memory.memory_service import MemoryService
from kimiko.core.gemini.adapter import GeminiAdapter



def parse_bilingual(text: str) -> Tuple[str, str]:
    """
    Parse text containing [EN] ... [VI] ... tags.
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

    # 0. Validate user text
    if not user_text or not user_text.strip():
        print("[turn_engine] Received empty user input, skipping turn.")
        return ""

    user_text = user_text.strip()

    # 1. Retrieve context & build system prompt from MemoryService
    try:
        context = memory.get_context(user_text)
        system_instruction = memory.build_system_prompt(persona, context)
    except Exception as e:
        print(f"[turn_engine] Failed to build context from memory: {e}")
        system_instruction = persona

    # 2. Start Gemini turn stream
    try:
        current_stream = gemini.run_turn(
            input_text=user_text,
            system_instruction=system_instruction,
            tools=tools,
            thinking_level="low"
        )

    except Exception as e:
        print(f"[turn_engine] Gemini API turn failed: {e}")
        fallback_response = "[EN] Sorry, I encountered a connection issue.\n[VI] Xin lỗi, mình đang gặp sự cố kết nối."
        en_fallback, vi_fallback = parse_bilingual(fallback_response)
        try:
            on_sentence(en_fallback, vi_fallback)
        except Exception as cb_err:
            print(f"[turn_engine] Fallback on_sentence callback error: {cb_err}")
        return fallback_response

    # 3. Initialize buffers and tracking
    full_response_text = ""
    sentence_buffer = ""
    current_interaction_id = None

    while True:
        pending_tool_calls = []
        try:
            # Consume streaming events from adapter.parse_text()
            for event_type, data in gemini.parse_text(current_stream):
                if event_type == "interaction_id":
                    current_interaction_id = data
                
                elif event_type == "text":
                    full_response_text += data
                    sentence_buffer += data
                    
                    # Check if sentence_buffer contains a complete bilingual unit:
                    if "[VI]" in sentence_buffer.upper():
                        vi_part = sentence_buffer.upper().split("[VI]", 1)[1]
                        if "\n" in vi_part:
                            en_text, vi_text = parse_bilingual(sentence_buffer)
                            if en_text:
                                try:
                                    on_sentence(en_text, vi_text)
                                except Exception as e:
                                    print(f"[turn_engine] on_sentence callback error: {e}")
                            sentence_buffer = ""
                
                elif event_type == "tool_call":
                    if isinstance(data, dict):
                        pending_tool_calls.append(data)
        except Exception as e:
            print(f"[turn_engine] Stream parsing error: {e}")
            break

        # 4. Handle tool calls: execute action and continue interaction
        if pending_tool_calls:
            for tool in pending_tool_calls:
                tool_name = tool.get("name", "unknown_action")
                tool_args = tool.get("arguments", {})
                tool_id = tool.get("id", "")

                try:
                    tool_result = on_action(tool_name, tool_args)
                except Exception as e:
                    print(f"[turn_engine] Tool execution failed for {tool_name}: {e}")
                    tool_result = {"status": "error", "message": str(e)}
                
                if not current_interaction_id:
                    print(f"[turn_engine] Missing current_interaction_id; skipping tool feedback for {tool_name}")
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
                    print(f"[turn_engine] continue_with_tool_result failed: {e}")
                    pending_tool_calls = []
                    break
            if pending_tool_calls:
                continue
        break
    
    # 5. Flush any remaining text in buffer
    if sentence_buffer.strip():
        en_text, vi_text = parse_bilingual(sentence_buffer)
        if en_text or vi_text:
            try:
                on_sentence(en_text, vi_text)
            except Exception as e:
                print(f"[turn_engine] Final on_sentence callback error: {e}")
    
    # 6. Record turns to MemoryDB (both user and assistant)
    try:
        memory.record_turn(role="user", content=user_text, session_id=session_id)
        if full_response_text.strip():
            memory.record_turn(role="assistant", content=full_response_text, session_id=session_id)
    except Exception as e:
        print(f"[turn_engine] Failed to persist turns to memory: {e}")
    return full_response_text



# if __name__ == "__main__":
#     import os
#     from kimiko.core.gemini.adapter import GeminiAdapter
#     from kimiko.core.gemini.tools import ACTION_TOOLS

#     # 1. Mock MemoryService for standalone testing without SQLite / LM Studio
#     class MockMemoryService:
#         def get_context(self, user_text: str):
#             return {
#                 "profile": "User name is Quang, developer.",
#                 "facts": ["Kimiko likes matcha and gaming."],
#                 "recent_turns": []
#             }
        
#         def build_system_prompt(self, persona: str, context: dict) -> str:
#             return (
#                 f"{persona}\n\n"
#                 f"User Profile: {context['profile']}\n"
#                 f"Relevant Memories: {', '.join(context['facts'])}\n\n"
#                 f"Subtitle Instruction:\n"
#                 f"You speak English. For your response, format your speech with Vietnamese subtitles using this exact structure:\n"
#                 f"[EN] <Spoken English response>\n"
#                 f"[VI] <Vietnamese subtitle translation>"
#             )

#         def record_turn(self, role: str, content: str, session_id: int):
#             print(f"[Memory Recorded] {role.upper()}: {content[:60]}...")

#     # 2. Mock Callbacks
#     def mock_on_sentence(speech_en: str, sub_vi: str):
#         print(f"\n[TTS Voice EN]: {speech_en}")
#         print(f"[Subtitle VI]: {sub_vi}")

#     def mock_on_action(action_name: str, args: dict):
#         print(f"\n[Avatar Action]: {action_name} with args: {args}")
#         return {"status": "success", "action": args.get("action")}

#     # 3. Initialize adapter and run test cases
#     gemini = GeminiAdapter()
#     memory = MockMemoryService()
#     persona = "You are Kimiko, a cheerful anime VTuber. Keep answers concise (1-2 sentences)."

#     print("=" * 60)
#     print("TEST 1: Regular conversation")
#     print("=" * 60)
#     run_turn(
#         user_text="Hi Kimiko, do you know my name?",
#         session_id=1,
#         persona=persona,
#         memory=memory,
#         gemini=gemini,
#         tools=ACTION_TOOLS,
#         on_sentence=mock_on_sentence,
#         on_action=mock_on_action
#     )

#     print("\n" + "=" * 60)
#     print("TEST 2: Action Trigger (Tool Calling)")
#     print("=" * 60)
#     run_turn(
#         user_text="Can you wave at me and say hello?",
#         session_id=1,
#         persona=persona,
#         memory=memory,
#         gemini=gemini,
#         tools=ACTION_TOOLS,
#         on_sentence=mock_on_sentence,
#         on_action=mock_on_action
#     )
