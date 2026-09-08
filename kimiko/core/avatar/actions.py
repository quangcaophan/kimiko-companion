from typing import Dict, Any
from pathlib import Path

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
        print(f"[avatar.actions] Unrecognized action {action_name!r}. Falling back to 'wave'.")
        entry = ACTION_ANIMATIONS["wave"]

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



# if __name__ == "__main__":
#     for action in ["wave", "walk", "backflip", "kiss", "flyingkick"]:
#         payload = execute(action)   
#         print(action, "->", payload["animation_url"])
#         assert payload["type"] == "start_mixamo"
#         assert os.path.exists(payload["animation_url"]), f"File not found: {payload['animation_url']}"

#     payload_unknown = execute("nonexistent_action")
#     assert payload_unknown["animation_url"].endswith("Waving.fbx")