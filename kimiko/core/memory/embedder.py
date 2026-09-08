from typing import Union, List
from openai import OpenAI


class LMStudioEmbedder:
    """Local text embedding client using LM Studio's OpenAI-compatible API."""

    def __init__(self, base_url: str, model: str) -> None:
        """Initialize LMStudioEmbedder.

        Args:
            base_url: The LM Studio v1 base URL (e.g. 'http://127.0.0.1:1234/v1').
            model: Embedding model name (e.g. 'text-embedding-bge-m3').
        """
        self.client: OpenAI = OpenAI(base_url=base_url, api_key="lm-studio", timeout=60.0)
        self.model: str = model

    def embed(self, input: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        """Generate embedding vector(s) for a string or list of strings.

        Args:
            input: Single text string or list of text strings.

        Returns:
            A 1D float list (dimension 1024) if input is a single string,
            or a 2D float list if input is a list of strings.
            Falls back safely to zero-vectors if LM Studio is unreachable.
        """
        is_list = isinstance(input, list)
        texts = input if is_list else [input]
        
        # Handle empty text input safely
        if not texts:
            return [] if is_list else [0.0] * 1024

        try:
            response = self.client.embeddings.create(model=self.model, input=texts)
            embeddings = [d.embedding for d in response.data]
            return embeddings if is_list else embeddings[0]
        except Exception as e:
            err_type = type(e).__name__
            print(f"[LMStudioEmbedder.embed] LM Studio unavailable [{err_type}]: {e}. Using zero-vector fallback.")
            zero_vec = [0.0] * 1024
            return [zero_vec for _ in texts] if is_list else zero_vec



# --- Test block ---
# from kimiko.core.memory.lifecycle import *

# server_ready = start_llm(BASE_URL)
# embedder = LMStudioEmbedder(base_url=BASE_URL, model='text-embedding-bge-m3')

# try:
#     if server_ready:
#         models = embedder.client.models.list()
#         print("✅ Connection OK. Loaded models:", [m.id for m in models.data])
#     else:
#         print("❌ Timeout! Check if lms CLI is functioning.")
# except Exception as e:
#     print("❌ Error during interaction:", repr(e))
# finally:
#     end_llm()