from typing import Generator, Tuple, Any, List, Dict, Optional
import os
import json
import time
from google import genai

from kimiko.core.logger import get_logger

logger = get_logger("gemini.adapter")


class GeminiAdapter:
    """Adapter wrapping Google GenAI Interactions API (v1alpha/experimental)."""

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None) -> None:
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise EnvironmentError("GEMINI_API_KEY is not set in environment or arguments.")
        self.client: genai.Client = genai.Client(api_key=key)
        self.model: str = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
        self.fallback_model: str = "gemini-2.5-flash-lite"
        logger.debug(f"Initialized GeminiAdapter with model: {self.model}")

    def run_turn(
        self,
        input_text: str,
        system_instruction: str,
        tools: List[Dict[str, Any]],
        thinking_level: Optional[str] = None
    ) -> Any:
        """Start a new streamed interaction turn with Gemini."""
        gen_config: Dict[str, Any] = {"max_output_tokens": 2048}
        if thinking_level and str(thinking_level).lower() not in {"none", "off", "0", "minimal", "low"}:
            gen_config["thinking_level"] = str(thinking_level).lower()

        tool_names = [t.get("name") for t in tools] if tools else []
        logger.info(
            f"Creating Gemini interaction [model={self.model}] "
            f"for query: {input_text[:60]!r} (tools: {tool_names})"
        )
        logger.debug(f"System instruction ({len(system_instruction)} chars): {system_instruction[:200]!r}...")

        t_start = time.time()
        try:
            stream = self.client.interactions.create(
                model=self.model,
                input=input_text,
                system_instruction=system_instruction,
                tools=tools,
                stream=True,
                generation_config=gen_config,
            )
            logger.debug(f"Interaction stream initiated in {time.time() - t_start:.2f}s")
            return stream
        except Exception as e:
            err_str = str(e).lower()
            if "thinking" in err_str:
                logger.warning(f"Model rejected thinking_level ({e}). Retrying without thinking_level...")
                gen_config.pop("thinking_level", None)
                return self.client.interactions.create(
                    model=self.model,
                    input=input_text,
                    system_instruction=system_instruction,
                    tools=tools,
                    stream=True,
                    generation_config=gen_config,
                )
            if ("quota" in err_str or "429" in err_str or "rate" in err_str) and self.model != self.fallback_model:
                # Use a local variable — do NOT mutate self.model permanently
                fallback = self.fallback_model
                logger.warning(
                    f"Primary model {self.model} hit quota/rate limit. "
                    f"Falling back to {fallback} for this turn only..."
                )
                return self.client.interactions.create(
                    model=fallback,
                    input=input_text,
                    system_instruction=system_instruction,
                    tools=tools,
                    stream=True,
                    generation_config=gen_config,
                )
            logger.error(f"Failed to create Gemini interaction: {e}")
            raise

    def continue_with_tool_result(
        self,
        previous_id: str,
        tool_call_id: str,
        tool_name: str,
        result: Any
    ) -> Any:
        """Feed a tool call execution result back into the interaction chain."""
        if not previous_id:
            raise ValueError("[GeminiAdapter.continue_with_tool_result] previous_id cannot be empty.")

        try:
            formatted_result = json.dumps(result) if not isinstance(result, str) else result
        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to JSON serialize tool result for {tool_name}: {e}. Falling back to str.")
            formatted_result = str(result)

        logger.info(
            f"Continuing interaction chain (id={previous_id}) with result of '{tool_name}' "
            f"(call_id={tool_call_id}): {formatted_result[:100]}"
        )
        try:
            return self.client.interactions.create(
                model=self.model,
                previous_interaction_id=previous_id,
                input=[{
                    "type": "function_result",
                    "name": tool_name,
                    "call_id": tool_call_id,
                    "result": formatted_result,
                }],
                stream=True,
            )
        except Exception as e:
            logger.error(f"Failed to continue interaction with tool result: {e}")
            raise
    
    def parse_text(self, stream: Any) -> Generator[Tuple[str, Any], None, None]:
        """Parse SSE interaction stream events into typed tuples:
        - ('interaction_id', id)
        - ('text', chunk)
        - ('tool_call', {'id': str, 'name': str, 'arguments': dict})
        """
        buffer: Dict[int, Dict[str, Any]] = {}
        total_chunks = 0
        total_text_len = 0

        try:
            for event in stream:
                if event.event_type == "interaction.created":
                    logger.debug(f"Interaction created event received: id={event.interaction.id}")
                    yield ("interaction_id", event.interaction.id)
                elif event.event_type == "step.delta" and event.delta.type == "text":
                    total_chunks += 1
                    total_text_len += len(event.delta.text)
                    yield ("text", event.delta.text)
                elif event.event_type == "step.start" and event.step.type == "function_call":
                    logger.info(f"Function call step started: {event.step.name} (id={event.step.id})")
                    buffer[event.index] = {"id": event.step.id, "name": event.step.name, "args": ""}
                elif event.event_type == "step.delta" and event.delta.type == "arguments_delta":
                    if event.index in buffer:
                        buffer[event.index]["args"] += getattr(event.delta, "arguments", "")
                elif event.event_type == "error":
                    err_msg = getattr(getattr(event, "error", None), "message", str(event))
                    logger.error(f"Gemini stream returned error event: {err_msg}")
        except Exception as e:
            logger.error(f"SSE stream interrupted or network dropped: {e}", exc_info=True)
            yield ("error", str(e))

        logger.debug(f"Stream parsing finished: {total_chunks} text chunks ({total_text_len} chars total)")

        for tool in buffer.values():
            raw_args = tool.get("args", "")
            try:
                parsed_args = json.loads(raw_args) if raw_args.strip() else {}
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(
                    f"Failed to JSON decode tool arguments for {tool.get('name')!r} "
                    f"(raw: {raw_args!r}): {e}. Defaulting to empty dict."
                )
                parsed_args = {}
            logger.info(f"Tool call fully received: {tool['name']} with args {parsed_args}")
            yield ("tool_call", {"id": tool["id"], "name": tool["name"], "arguments": parsed_args})
