"""Configuration loader for Kimiko Companion.

Loads settings and persona configuration from YAML files with environment variable overrides.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import yaml
except ImportError:
    yaml = None

from kimiko.core.logger import get_logger

logger = get_logger("config.loader")

_DEFAULT_PERSONA = (
    "You are Kimiko, a cute, playful, intelligent anime VTuber AI companion.\n"
    "You live inside a 3D VRM space and interact with your master, Quang.\n"
    "Keep responses concise (1-3 sentences).\n"
    "You can execute actions like wave, walk, backflip, kiss, flyingkick using the provided tools.\n"
    "When performing an action, always speak a playful voice line describing what you are doing.\n"
    "Always follow the bilingual format: English speech followed by Vietnamese subtitles:\n"
    "[EN] <English speech>\n"
    "[VI] <Vietnamese subtitle translation>"
)


@dataclass
class KimikoConfig:
    """Central configuration container for the Kimiko runtime."""
    # Persona
    persona: str = _DEFAULT_PERSONA

    # Embedding / LM Studio
    embedding_host: str = "127.0.0.1"
    embedding_port: str = "1234"
    embedding_model: str = "text-embedding-bge-m3"
    embedding_url: str = "http://127.0.0.1:1234/v1"

    # Memory
    memory_window_size: int = 20
    memory_top_k: int = 5
    memory_summarize_every_n_turns: int = 20

    # Audio & TTS
    sovits_url: str = "http://127.0.0.1:9880"
    sovits_speed_factor: float = 1.2
    sovits_ref_audio_path: str = "character_files/main_sample.wav"

    # LLM / Gemini
    gemini_model: str = "gemini-2.5-flash-lite"

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8001


def _read_yaml(file_path: Path) -> Dict[str, Any]:
    """Safely load a YAML file, returning an empty dict if not found or unparseable."""
    if not file_path.is_file():
        logger.debug(f"Config file not found: {file_path}")
        return {}

    if yaml is None:
        logger.warning(f"PyYAML is not installed. Cannot parse {file_path}")
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning(f"Failed to parse YAML file {file_path}: {e}")
        return {}


def load_config(config_dir: Optional[Path] = None) -> KimikoConfig:
    """Load configuration from config/ directory with environment variable overrides.

    Resolution precedence:
      1. Environment variables (highest priority)
      2. YAML config files (settings.yaml, persona.yaml)
      3. Built-in defaults
    """
    if config_dir is None:
        # Default to kimiko/config relative to this file
        config_dir = Path(__file__).resolve().parent

    persona_path = config_dir / "persona.yaml"
    settings_path = config_dir / "settings.yaml"

    persona_data = _read_yaml(persona_path)
    settings_data = _read_yaml(settings_path)

    # 1. Persona resolution
    persona = persona_data.get("persona", "").strip() or _DEFAULT_PERSONA

    # 2. Settings resolution
    embedding_cfg = settings_data.get("embedding", {})
    memory_cfg = settings_data.get("memory", {})
    server_cfg = settings_data.get("server", {})
    gemini_cfg = settings_data.get("gemini", {})
    sovits_cfg = settings_data.get("sovits", {})

    # Embedding host / port / url
    emb_host = os.getenv("LM_STUDIO_HOST") or embedding_cfg.get("lm_studio_host", "127.0.0.1")
    emb_port = os.getenv("LM_STUDIO_PORT") or str(embedding_cfg.get("lm_studio_port", "1234"))
    default_emb_url = f"http://{emb_host}:{emb_port}/v1"
    emb_url = os.getenv("LM_STUDIO_URL") or default_emb_url
    emb_model = embedding_cfg.get("model", "text-embedding-bge-m3")

    # Memory
    mem_window = int(memory_cfg.get("window_size", 20))
    mem_top_k = int(memory_cfg.get("top_k", 5))
    mem_summarize = int(memory_cfg.get("summarize_every_n_turns", 20))

    # SoVITS
    sovits_ping = persona_data.get("sovits_ping_config", {})
    sovits_url = (
        os.getenv("SOVITS_URL")
        or sovits_cfg.get("base_url")
        or sovits_ping.get("base_url", "http://127.0.0.1:9880")
    )
    sovits_speed = float(
        sovits_cfg.get("speed_factor")
        or sovits_ping.get("speed_factor", 1.2)
    )
    sovits_ref_audio = (
        sovits_cfg.get("ref_audio_path")
        or sovits_ping.get("ref_audio_path", "character_files/main_sample.wav")
    )

    # Gemini model
    gemini_model = os.getenv("GEMINI_MODEL") or gemini_cfg.get("model", "gemini-2.5-flash-lite")

    # Server
    srv_host = server_cfg.get("host", "0.0.0.0")
    srv_port = int(server_cfg.get("port", 8001))

    cfg = KimikoConfig(
        persona=persona,
        embedding_host=emb_host,
        embedding_port=emb_port,
        embedding_model=emb_model,
        embedding_url=emb_url,
        memory_window_size=mem_window,
        memory_top_k=mem_top_k,
        memory_summarize_every_n_turns=mem_summarize,
        sovits_url=sovits_url,
        sovits_speed_factor=sovits_speed,
        sovits_ref_audio_path=sovits_ref_audio,
        gemini_model=gemini_model,
        server_host=srv_host,
        server_port=srv_port,
    )

    logger.debug("Configuration successfully loaded.")
    return cfg
