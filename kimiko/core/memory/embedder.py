from typing import Union, List
from openai import OpenAI

from kimiko.core.logger import get_logger

logger = get_logger("memory.embedder")


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
        logger.debug(f"Initialized LMStudioEmbedder: url={base_url}, model={model}")

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

        logger.debug(f"Embedding {len(texts)} item(s) with model '{self.model}'...")
        try:
            response = self.client.embeddings.create(model=self.model, input=texts)
            embeddings = [d.embedding for d in response.data]
            logger.debug(f"Generated {len(embeddings)} embedding(s), dim={len(embeddings[0]) if embeddings else 0}")
            return embeddings if is_list else embeddings[0]
        except Exception as e:
            err_type = type(e).__name__
            logger.warning(f"LM Studio unavailable [{err_type}]: {e}. Using zero-vector fallback.")
            zero_vec = [0.0] * 1024
            return [zero_vec for _ in texts] if is_list else zero_vec