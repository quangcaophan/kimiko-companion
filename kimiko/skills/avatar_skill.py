"""Avatar Skill — Physical avatar animations via Mixamo FBX and VRMA.

Exposes avatar body gestures, acrobatic moves, dances, and daily poses
as a Gemini-callable tool. Delegates animation resolution to
kimiko/core/avatar/actions.py, which dynamically scans all animation assets.
"""
from typing import Dict, Any, List
from kimiko.skills import BaseSkill
from kimiko.core.avatar import actions
from kimiko.core.logger import get_logger

logger = get_logger("skills.avatar")

CURATED_ACTIONS: List[str] = [
    # Dances & Fun
    "dance", "shikanoko", "spin", "squat",
    # Greetings & Poses
    "wave", "peace_sign", "kiss", "bow", "model_pose", "greeting", "shoot", "touch_ears", "headpat",
    # Acrobatics & Combat
    "backflip", "frontflip", "running_flip", "flyingkick", "punch", "cross_punch", "jump",
    # Emotions & Reactions
    "happy", "excited", "angry", "sad", "bashful", "thinking", "loser",
    # Gestures
    "nod", "shake_head", "dismiss", "cocky", "sigh", "look_around",
    # Locomotion
    "walk", "run", "catwalk", "sneak", "goofy_run",
    # Daily Life & Resting
    "drink_water", "phone", "sleep", "sit", "stand",
]


class AvatarSkill(BaseSkill):
    """Exposes 3D avatar animations and gestures as a Gemini-callable tool."""

    name = "avatar"
    description = "Control 3D avatar body animations, acrobatics, dances, and physical gestures"

    tool_definitions = [
        {
            "type": "function",
            "name": "perform_action",
            "description": (
                "Perform a physical avatar action, gesture, or dance on the 3D VRM model. "
                "Available actions:\n"
                "- Dances: dance (Bling-Bang-Bang-Born), shikanoko, spin, squat\n"
                "- Greetings & Poses: wave, peace_sign, kiss, bow (dogeza/apology), model_pose, greeting, shoot, touch_ears, headpat\n"
                "- Acrobatics & Combat: backflip, frontflip, running_flip, flyingkick, punch, cross_punch, jump\n"
                "- Emotions: happy, excited, angry, sad, bashful (shy), thinking, loser\n"
                "- Gestures: nod, shake_head, dismiss, cocky, sigh, look_around\n"
                "- Locomotion: walk, run, catwalk, sneak, goofy_run\n"
                "- Daily Life: drink_water, phone, sleep, sit, stand\n"
                "Use this whenever the user asks Kimiko to move, gesture, dance, or perform an action."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": CURATED_ACTIONS,
                        "description": "The animation action to perform on the 3D avatar model."
                    }
                },
                "required": ["action"],
            },
        }
    ]

    def execute(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "perform_action":
            action_name = args.get("action", "wave")
            logger.info(f"Executing avatar action: {action_name}")
            payload = actions.execute(action_name)
            duration = payload.get("duration", 2.5)
            resolved_key = payload.get("action_key", action_name)
            return {
                "status": "success",
                "action": resolved_key,
                "duration": duration,
                "payload": payload,
            }

        logger.warning(f"Unknown avatar tool: {tool_name}")
        return {"status": "error", "message": f"Unknown tool: {tool_name}"}
