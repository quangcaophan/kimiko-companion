from typing import Generator, Tuple, Any, List, Dict, Optional
import os
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()


class GeminiAdapter:
    """Adapter wrapping Google GenAI Interactions API (v1alpha/experimental)."""

    def __init__(self, model: str = "gemini-3.5-flash-lite", api_key: Optional[str] = None) -> None:
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise EnvironmentError("GEMINI_API_KEY is not set in environment or arguments.")
        self.client: genai.Client = genai.Client(api_key=key)
        self.model: str = model

    def run_turn(
        self,
        input_text: str,
        system_instruction: str,
        tools: List[Dict[str, Any]],
        thinking_level: str = "low"
    ) -> Any:
        """Start a new streamed interaction turn with Gemini."""
        level = "low" if str(thinking_level).lower() in {"minimal", "low"} else "high"
        gen_config: Dict[str, Any] = {"thinking_level": level, "max_output_tokens": 1024}

        try:
            return self.client.interactions.create(
                model=self.model,
                input=input_text,
                system_instruction=system_instruction,
                tools=tools,
                stream=True,
                generation_config=gen_config,
            )
        except Exception as e:
            if "thinking_level" in str(e).lower():
                print(f"[GeminiAdapter.run_turn] thinking_level error: {e}. Retrying without thinking_level...")
                gen_config.pop("thinking_level", None)
                return self.client.interactions.create(
                    model=self.model,
                    input=input_text,
                    system_instruction=system_instruction,
                    tools=tools,
                    stream=True,
                    generation_config=gen_config,
                )
            print(f"[GeminiAdapter.run_turn] Failed to create interaction: {e}")
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
            print(f"[GeminiAdapter.continue_with_tool_result] Failed to serialize tool result: {e}")
            formatted_result = str(result)

        try:
            return self.client.interactions.create(
                model=self.model,
                previous_interaction_id=previous_id,
                input=[{
                    "type": "function_result",
                    "name": tool_name,
                    "call_id": tool_call_id,
                    "result": [{"type": "text", "text": formatted_result}],
                }],
                stream=True,
            )
        except Exception as e:
            print(f"[GeminiAdapter.continue_with_tool_result] Failed to continue interaction: {e}")
            raise
    
    def parse_text(self, stream: Any) -> Generator[Tuple[str, Any], None, None]:
        """Parse SSE interaction stream events into typed tuples:
        - ('interaction_id', id)
        - ('text', chunk)
        - ('tool_call', {'id': str, 'name': str, 'arguments': dict})
        """
        buffer: Dict[int, Dict[str, Any]] = {}
        try:
            for event in stream:
                if event.event_type == "interaction.created":
                    yield ("interaction_id", event.interaction.id)
                elif event.event_type == "step.delta" and event.delta.type == "text":
                    yield ("text", event.delta.text)
                elif event.event_type == "step.start" and event.step.type == "function_call":
                    buffer[event.index] = {"id": event.step.id, "name": event.step.name, "args": ""}
                elif event.event_type == "step.delta" and event.delta.type == "arguments_delta":
                    if event.index in buffer:
                        buffer[event.index]["args"] += getattr(event.delta, "arguments", "")
        except Exception as e:
            print(f"[GeminiAdapter.parse_text] Stream interrupted or network error: {e}")

        for tool in buffer.values():
            raw_args = tool.get("args", "")
            try:
                parsed_args = json.loads(raw_args) if raw_args.strip() else {}
            except (json.JSONDecodeError, TypeError) as e:
                print(f"[GeminiAdapter.parse_text] Failed to decode arguments for {tool.get('name')!r} (raw: {raw_args!r}): {e}")
                parsed_args = {}
            yield ("tool_call", {"id": tool["id"], "name": tool["name"], "arguments": parsed_args})

