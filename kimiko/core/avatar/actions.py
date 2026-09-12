from typing import Dict, Any
from pathlib import Path

from kimiko.core.logger import get_logger

logger = get_logger("avatar.actions")

ANIMATION_DIR = Path("animations/mixamo")


ACTION_ANIMATIONS: Dict[str, Dict[str, Any]] = {
    "wave":         {"file": "Waving.fbx",            "play_once": True,  "lock_position": False},
    "walk":         {"file": "Walking_inplace.fbx",   "play_once": False, "lock_position": True},
    "backflip":     {"file": "Backflip.fbx",          "play_once": True,  "lock_position": False},
    "kiss":         {"file": "Kiss.fbx",              "play_once": True,  "lock_position": False},
    "flyingkick":   {"file": "Flying Kick.fbx",       "play_once": True,  "lock_position": False},
}


def execute(action_name: str) -> Dict[str, Any]:
    """Resolve an LLM action name into a broadcast-ready Three.js Mixamo animation payload.

    Args:
        action_name: One of 'wave', 'walk', 'backflip', 'kiss', 'flyingkick'.
                     Falls back safely to 'wave' if unknown or invalid.

    Returns:
        WebSocket broadcast payload dict formatted for Three.js VRM client.
    """
    normalized_name = str(action_name or "").lower().strip()
    entry = ACTION_ANIMATIONS.get(normalized_name)
    if not entry:
        logger.warning(f"Unrecognized action {action_name!r}. Falling back to default 'wave'.")
        entry = ACTION_ANIMATIONS["wave"]
    else:
        logger.debug(f"Resolved action '{normalized_name}' -> file '{entry['file']}'")

    anim_path = ANIMATION_DIR / entry["file"]
    return {
        "type": "start_mixamo",
        "animation_url": anim_path.as_posix(),
        "play_once": entry["play_once"],
        "crop_start": 0.0,
        "crop_end": 0.0,
        "lock_position": entry["lock_position"],
        "track_position": True,
    }