"""Avatar Actions — Physical avatar animations via Mixamo FBX and VRMA.

Scans all animation assets in kimiko/assets/client/animations, including
FBX (Mixamo) and VRMA files, and maps them to callable action names with
natural aliases, durations, and loop settings.
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
import re

from kimiko.core.logger import get_logger

logger = get_logger("avatar.actions")

# Root directory for animation files on the filesystem
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "client" / "animations"
if not _ROOT_DIR.is_dir():
    _ROOT_DIR = Path("kimiko/assets/client/animations").resolve()

# Curated natural-language aliases for common / expressive actions
ALIASES: Dict[str, str] = {
    # Dances & Fun
    "dance": "Bling-Bang-Bang-Born",
    "bling": "Bling-Bang-Bang-Born",
    "bling_bang_bang_born": "Bling-Bang-Bang-Born",
    "shikanoko": "shikanoko",
    "dance_shikanoko": "shikanoko",
    "spin": "Spin",
    "squat": "Squat",
    # Greetings & Poses
    "wave": "Waving",
    "waving": "Waving",
    "peace": "Peace_sign",
    "peace_sign": "Peace_sign",
    "model_pose": "Model_pose",
    "pose": "Model_pose",
    "greeting": "Greeting",
    "hello": "004_hello_1",
    "kiss": "Kiss",
    "shoot": "Shoot",
    "touch_ears": "touch_ears",
    "headpat": "headpat1",
    "woah": "woah",
    "stop_it": "stop_it",
    # Acrobatics & Combat
    "backflip": "Backflip",
    "frontflip": "Front Flip",
    "front_flip": "Front Flip",
    "running_flip": "Running Forward Flip",
    "running_forward_flip": "Running Forward Flip",
    "flyingkick": "Flying Kick",
    "flying_kick": "Flying Kick",
    "kick": "Flying Kick",
    "punch": "Punch Combo",
    "punch_combo": "Punch Combo",
    "cross_punch": "Cross Punch",
    "jump": "jump",
    "bicycle_crunch": "Bicycle Crunch",
    "workout": "Bicycle Crunch",
    # Emotions & Expressions
    "happy": "Happy",
    "laugh": "Happy",
    "excited": "Excited",
    "angry": "Angry",
    "sad": "Sad Idle",
    "sad_idle": "Sad Idle",
    "shy": "Bashful",
    "bashful": "Bashful",
    "thinking": "Thinking",
    "loser": "Loser",
    # Gestures
    "nod": "head nod yes",
    "head_nod": "head nod yes",
    "agree": "head nod yes",
    "shake_head": "shaking head no",
    "head_no": "shaking head no",
    "disagree": "shaking head no",
    "happy_gesture": "happy hand gesture",
    "cocky": "being cocky",
    "dismiss": "dismissing gesture",
    "sigh": "relieved sigh",
    "look_away": "look away gesture",
    "look_around": "Look Around",
    "talking": "Talking",
    # Daily Life & Resting
    "bow": "002_dogeza",
    "dogeza": "002_dogeza",
    "apologize": "002_dogeza",
    "drink": "006_drinkwater",
    "drink_water": "006_drinkwater",
    "phone": "005_smartphone",
    "smartphone": "005_smartphone",
    "sleep": "Laying Sleeping",
    "sleeping": "Laying Sleeping",
    "sit": "Sitting",
    "sitting": "Sitting",
    "stand_to_sit": "Stand To Sit",
    "sit_to_stand": "Sit To Stand",
    # Locomotion
    "walk": "Walking_inplace",
    "walking": "Walking_inplace",
    "run": "running",
    "running": "running",
    "goofy_run": "Goofy Running",
    "catwalk": "Catwalk Walk",
    "sneak": "Sneak Walk",
}

# Fine-tuned metadata (durations, loop, lock position)
CUSTOM_METADATA: Dict[str, Dict[str, Any]] = {
    # Dances
    "Bling-Bang-Bang-Born": {"duration": 8.0, "play_once": True, "lock_position": False},
    "shikanoko": {"duration": 8.0, "play_once": True, "lock_position": False},
    "Spin": {"duration": 3.5, "play_once": True, "lock_position": False},
    "Squat": {"duration": 3.0, "play_once": True, "lock_position": False},
    # Acrobatics
    "Backflip": {"duration": 3.5, "play_once": True, "lock_position": False},
    "Front Flip": {"duration": 3.5, "play_once": True, "lock_position": False},
    "Running Forward Flip": {"duration": 3.5, "play_once": True, "lock_position": False},
    "Flying Kick": {"duration": 3.0, "play_once": True, "lock_position": False},
    "Punch Combo": {"duration": 3.0, "play_once": True, "lock_position": False},
    "Cross Punch": {"duration": 2.5, "play_once": True, "lock_position": False},
    "jump": {"duration": 2.0, "play_once": True, "lock_position": False},
    "Bicycle Crunch": {"duration": 4.0, "play_once": True, "lock_position": True},
    # Poses & Daily Life
    "002_dogeza": {"duration": 4.5, "play_once": True, "lock_position": False},
    "006_drinkwater": {"duration": 4.0, "play_once": True, "lock_position": False},
    "005_smartphone": {"duration": 4.0, "play_once": True, "lock_position": False},
    "Peace_sign": {"duration": 3.0, "play_once": True, "lock_position": False},
    "Model_pose": {"duration": 3.5, "play_once": True, "lock_position": False},
    "Greeting": {"duration": 3.0, "play_once": True, "lock_position": False},
    "004_hello_1": {"duration": 3.0, "play_once": True, "lock_position": False},
    "Kiss": {"duration": 2.5, "play_once": True, "lock_position": False},
    "Shoot": {"duration": 3.0, "play_once": True, "lock_position": False},
    "Sitting": {"duration": 3.5, "play_once": True, "lock_position": True},
    "Laying Sleeping": {"duration": 4.0, "play_once": True, "lock_position": True},
    # Locomotion (Loops)
    "Walking_inplace": {"duration": 3.0, "play_once": False, "lock_position": True},
    "Walking": {"duration": 3.0, "play_once": False, "lock_position": False},
    "running": {"duration": 3.0, "play_once": False, "lock_position": True},
    "Catwalk Walk": {"duration": 3.5, "play_once": False, "lock_position": True},
    "Sneak Walk": {"duration": 3.0, "play_once": False, "lock_position": True},
    "Goofy Running": {"duration": 3.0, "play_once": False, "lock_position": True},
    "Idle": {"duration": 3.0, "play_once": False, "lock_position": True},
}


def _normalize_key(key: str) -> str:
    """Normalize a string key: lowercase, strip punctuation/spaces to underscores."""
    s = re.sub(r"[\s\-]+", "_", str(key or "").lower().strip())
    return re.sub(r"[^a-z0-9_]", "", s)


class ActionCatalog:
    """Discovers and caches all animation files from the codebase."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.files_by_stem: Dict[str, Path] = {}
        self.files_by_norm_key: Dict[str, Path] = {}
        self._scan()

    def _scan(self) -> None:
        if not self.root_dir.is_dir():
            logger.warning(f"Animations directory not found at {self.root_dir}")
            return

        for path in self.root_dir.rglob("*"):
            if path.suffix.lower() in {".fbx", ".vrma"}:
                stem = path.stem
                self.files_by_stem[stem] = path

                norm = _normalize_key(stem)
                self.files_by_norm_key[norm] = path

                # Also strip numeric prefixes like '002_dogeza' -> 'dogeza'
                no_num = re.sub(r"^\d+_", "", norm)
                if no_num != norm and no_num not in self.files_by_norm_key:
                    self.files_by_norm_key[no_num] = path

        logger.info(
            f"ActionCatalog scanned {len(self.files_by_stem)} animation files "
            f"from {self.root_dir.name}"
        )

    def resolve(self, action_name: str) -> Optional[Dict[str, Any]]:
        """Resolve an action name or alias to its animation entry dict."""
        raw = str(action_name or "").strip()
        norm = _normalize_key(raw)

        # 1. Direct check in ALIASES
        target_stem = ALIASES.get(norm) or ALIASES.get(raw)
        if target_stem and target_stem in self.files_by_stem:
            return self._build_entry(target_stem, self.files_by_stem[target_stem], norm)

        # 2. Check exact stem (e.g. 'Backflip', 'Bling-Bang-Bang-Born')
        if raw in self.files_by_stem:
            return self._build_entry(raw, self.files_by_stem[raw], norm)

        # 3. Check normalized key
        if norm in self.files_by_norm_key:
            path = self.files_by_norm_key[norm]
            return self._build_entry(path.stem, path, norm)

        # 4. Check stripped without underscores
        stripped = norm.replace("_", "")
        for k, p in self.files_by_norm_key.items():
            if k.replace("_", "") == stripped:
                return self._build_entry(p.stem, p, norm)

        return None

    def _build_entry(self, stem: str, file_path: Path, action_key: str) -> Dict[str, Any]:
        rel_path = file_path.relative_to(self.root_dir).as_posix()
        url = f"animations/{rel_path}"
        ext = file_path.suffix.lower()
        anim_type = "start_mixamo" if ext == ".fbx" else "start_vrma"

        # Apply custom metadata or intelligent defaults
        meta = CUSTOM_METADATA.get(stem, {})
        is_loop = "walk" in stem.lower() or "idle" in stem.lower() or "run" in stem.lower()

        play_once = meta.get("play_once", not is_loop)
        lock_position = meta.get("lock_position", "inplace" in stem.lower() or "idle" in stem.lower())
        duration = meta.get("duration", 2.5)

        return {
            "type": anim_type,
            "animation_url": url,
            "play_once": play_once,
            "crop_start": meta.get("crop_start", 0.0),
            "crop_end": meta.get("crop_end", 0.0),
            "lock_position": lock_position,
            "track_position": True,
            "duration": duration,
            "stem": stem,
            "action_key": action_key,
        }


# Singleton catalog instance
catalog = ActionCatalog(_ROOT_DIR)


def get_available_actions() -> List[str]:
    """Return a sorted list of all callable action names (aliases + file stems)."""
    actions_set = set(ALIASES.keys())
    actions_set.update(catalog.files_by_norm_key.keys())
    return sorted(list(actions_set))


def execute(action_name: str) -> Dict[str, Any]:
    """Resolve an LLM action name into a broadcast-ready animation payload.

    Args:
        action_name: Action alias, canonical name, or file stem (e.g. 'dance', 'wave', 'backflip').
                     Falls back safely to 'wave' if unrecognized.

    Returns:
        WebSocket broadcast payload dict formatted for Three.js VRM client,
        including 'duration' and 'action_key'.
    """
    entry = catalog.resolve(action_name)
    if not entry:
        logger.warning(
            f"Unrecognized action '{action_name}'. Falling back to default 'wave'."
        )
        entry = catalog.resolve("wave")
        if not entry:
            # Absolute fallback if wave file missing
            return {
                "type": "start_mixamo",
                "animation_url": "animations/mixamo/Waving.fbx",
                "play_once": True,
                "crop_start": 0.0,
                "crop_end": 0.0,
                "lock_position": False,
                "track_position": True,
                "duration": 2.5,
                "action_key": "wave",
            }
    else:
        logger.info(
            f"Resolved action '{action_name}' -> file '{entry['animation_url']}' "
            f"(type={entry['type']}, duration={entry['duration']}s)"
        )

    return {
        "type": entry["type"],
        "animation_url": entry["animation_url"],
        "play_once": entry["play_once"],
        "crop_start": entry["crop_start"],
        "crop_end": entry["crop_end"],
        "lock_position": entry["lock_position"],
        "track_position": entry["track_position"],
        "duration": entry["duration"],
        "action_key": entry.get("action_key", action_name),
    }