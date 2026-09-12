# Kimiko Skill Template

Create your own skills by adding a `<name>_skill.py` file to `kimiko/skills/`.  
The registry auto-discovers all `*_skill.py` modules on startup.

---

## Minimal Template

```python
"""<Skill Name> Skill for Kimiko."""
from kimiko.skills import BaseSkill
from kimiko.core.logger import get_logger

logger = get_logger("skills.<name>")


class YourSkill(BaseSkill):
    """One-line description."""

    name = "your_skill"

    tool_definitions = [
        {
            "type": "function",
            "name": "your_tool_name",
            "description": "What this tool does — Kimiko reads this to decide when to call it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "param1": {
                        "type": "string",
                        "description": "Description of param1"
                    },
                },
                "required": ["param1"],
            },
        },
    ]

    def execute(self, tool_name: str, args: dict) -> dict:
        if tool_name == "your_tool_name":
            param1 = args.get("param1", "")
            # Your logic here
            return {"status": "success", "result": f"Done with {param1}"}

        return {"status": "error", "message": f"Unknown tool: {tool_name}"}
```

---

## Rules

| Rule | Detail |
|------|--------|
| File naming | `<name>_skill.py` — required for auto-discovery |
| Class | Must inherit `BaseSkill` |
| `name` | Unique string identifier |
| `tool_definitions` | List of dicts in Gemini function-calling format |
| `execute()` | Must return a `dict` with `"status"` key |
| Tool descriptions | Clear descriptions help Kimiko know **when** to use the tool |
| Error handling | Catch exceptions → return `{"status": "error", ...}` |

## Parameter Types

| Type | Use for |
|------|---------|
| `"string"` | Text |
| `"integer"` | Whole numbers |
| `"number"` | Decimals/floats |
| `"boolean"` | True/false |
| `"array"` | Lists (add `"items"` sub-schema) |

Add `"enum": ["opt1", "opt2"]` to restrict values.

---

## Example: Dice Roll Skill

```python
"""Dice Roll Skill."""
import random
from kimiko.skills import BaseSkill
from kimiko.core.logger import get_logger

logger = get_logger("skills.dice")


class DiceSkill(BaseSkill):
    name = "dice"

    tool_definitions = [
        {
            "type": "function",
            "name": "roll_dice",
            "description": "Roll dice. Example: 2d20 = two 20-sided dice.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "Number of dice (default 1)"},
                    "sides": {"type": "integer", "description": "Sides per die (default 6)"},
                },
                "required": [],
            },
        }
    ]

    def execute(self, tool_name: str, args: dict) -> dict:
        if tool_name == "roll_dice":
            count = max(1, min(args.get("count", 1), 100))
            sides = max(2, min(args.get("sides", 6), 1000))
            rolls = [random.randint(1, sides) for _ in range(count)]
            return {"status": "success", "rolls": rolls, "total": sum(rolls)}
        return {"status": "error", "message": f"Unknown tool: {tool_name}"}
```
