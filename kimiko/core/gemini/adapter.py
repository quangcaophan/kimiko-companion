from google import genai
from dotenv import load_dotenv
import os
import json

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)


class GeminiAdapter:
    def __init__(self, model="gemini-3.5-flash-lite"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def run_turn(self, input_text, system_instruction, tools, thinking_level="minimal"):
        return self.client.interactions.create(
            model=self.model,
            input=input_text,
            system_instruction=system_instruction,
            tools=tools,
            stream=True,
            generation_config={"thinking_level": thinking_level, "max_output_tokens": 1024},
        )

    def continue_with_tool_result(self, previous_id, tool_call_id, tool_name, result):
        return self.client.interactions.create(
            model=self.model,
            previous_interaction_id=previous_id,
            input=[{
                "type": "function_result",
                "name": tool_name,
                "call_id": tool_call_id,
                "result": [{"type": "text", "text": json.dumps(result) if not isinstance(result, str) else result}],
            }],
            stream=True,
        )
    
    def parse_text(self, stream):
        buffer = {}
        for event in stream:
            if event.event_type == "interaction.created":
                yield ("interaction_id", event.interaction.id)
            elif event.event_type == "step.delta" and event.delta.type == "text":
                yield ("text", event.delta.text)
            elif event.event_type == "step.start" and event.step.type == "function_call":
                buffer[event.index] = {"id": event.step.id, "name": event.step.name, "args": ""}
            elif event.event_type == "step.delta" and event.delta.type == "arguments_delta":
                buffer[event.index]["args"] += event.delta.arguments
        for tool in buffer.values():
            yield ("tool_call", {"id": tool["id"], "name": tool["name"], "arguments": json.loads(tool["args"])})
