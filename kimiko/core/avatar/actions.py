from typing import Dict, Any
import os 
from pathlib import Path

ANIMATION_DIR = Path("animations/mixamo")


ACTION_ANIMATIONS: dict[str, dict] = {
    "wave":         {"file": "Waving.fbx",            "play_once": True,  "lock_position": False},
    "walk":         {"file": "Walking_inplace.fbx",   "play_once": False, "lock_position": True},
    "backflip":     {"file": "Backflip.fbx",          "play_once": True,  "lock_position": False},
    "kiss":         {"file": "Kiss.fbx",            "play_once": True,  "lock_position": False},
    "flyingkick":   {"file": "Flying Kick.fbx",         "play_once": True,  "lock_position": False},
}

def execute(action_name: str) -> dict:
    entry = ACTION_ANIMATIONS.get(action_name, ACTION_ANIMATIONS["wave"])
    return {
        "type": "start_mixamo",
        "animation_url": (ANIMATION_DIR / entry["file"]).as_posix(),
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