"""
Region / bone -> reaction mapping for /send_click_interaction.

Pure data + selection logic. Returns broadcast-ready dicts (sound, animation,
idle) so server.py can hand them straight to notify_clients without any HTTP
self-calls or threading.

The payload shapes here intentionally mirror what /talk and /animate already
broadcast, so the client sees the same message types regardless of source.
"""
import random
from pathlib import Path
from typing import Tuple, Dict, Any, List


SOUND_DIR = Path("public/sounds")
ANIM_VRMA_DIR = Path("animations/vrma_xr")
ANIM_MIXAMO_DIR = Path("animations/mixamo")

FEEDBACK_SOUNDS: List[Tuple[str, str]] = [
    ("oh.wav", "oh?"),
    ("hey.wav", "hey"),
]


def _talk_payload(audio_path: Path, text: str, duration: int = 1, expression: str = "relaxed") -> Dict[str, Any]:
    return {
        "type": "start_animation",
        "audio_path": str(audio_path),
        "expression": expression,
        "audio_text": text,
        "audio_duraction": duration,
    }


def _vrma_payload(animation_path: Path, crop_start: float = 0.0, crop_end: float = 0.0) -> Dict[str, Any]:
    return {
        "type": "start_vrma",
        "animation_url": str(animation_path),
        "play_once": False,
        "crop_start": crop_start,
        "crop_end": crop_end,
        "lock_position": False,
        "track_position": True,
    }


def _idle_payload() -> Dict[str, Any]:
    return {
        "type": "start_mixamo",
        "animation_url": str(ANIM_MIXAMO_DIR / "Idle.fbx"),
        "play_once": False,
        "crop_start": 0.0,
        "crop_end": 0.0,
        "lock_position": False,
        "track_position": True,
    }


def _pick_animation(region: str, bone: str) -> Tuple[Path, float, float]:
    """Choose (animation_path, crop_start, idle_delay) from region/bone."""
    region_l = (region or "").lower()
    bone_l = bone or ""

    if region_l in {"chest", "bust", "belly"}:
        return ANIM_VRMA_DIR / "woah.vrma", 0.85, 3.0

    if bone_l in {"left_cat_ear", "right_cat_ear"}:
        return ANIM_VRMA_DIR / "touch_ears.vrma", 0.95, 3.0

    right_parts = ("right_hand", "right_arm", "right_shoulder", "right_thigh", "right_shin", "right_foot")
    if any(part in region_l for part in right_parts):
        return ANIM_VRMA_DIR / "lookright.vrma", 0.72, 2.2

    left_parts = ("left_hand", "left_arm", "left_shoulder", "left_thigh", "left_shin", "left_foot")
    if any(part in region_l for part in left_parts):
        return ANIM_VRMA_DIR / "lookleft.vrma", 0.82, 2.1

    if region_l in {"head", "neck", "hair"}:
        return ANIM_VRMA_DIR / "headpat_cover.vrma", 0.72, 2.8

    return ANIM_VRMA_DIR / "stop_it.vrma", 0.82, 1.7


def build_click_reaction(region: str, bone: str) -> Dict[str, Any]:
    """Build the sound + animation + idle payloads for a click interaction.

    Returns a dict with keys:
        sound       broadcast payload for the feedback voice line
        animation   broadcast payload for the reaction animation
        idle        broadcast payload that returns to idle
        idle_delay  seconds to wait before sending the idle payload
    """
    sound_file, sound_text = random.choice(FEEDBACK_SOUNDS)
    sound_payload = _talk_payload(SOUND_DIR / sound_file, sound_text)

    anim_path, crop_start, idle_delay = _pick_animation(region, bone)
    anim_payload = _vrma_payload(anim_path, crop_start=crop_start, crop_end=0.0)

    return {
        "sound": sound_payload,
        "animation": anim_payload,
        "idle": _idle_payload(),
        "idle_delay": idle_delay,
    }
