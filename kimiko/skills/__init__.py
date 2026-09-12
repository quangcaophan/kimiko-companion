"""
Kimiko Skill System — BaseSkill and SkillRegistry.

Provides a plugin architecture for registering tool-based skills that Kimiko
can invoke through Gemini function calling.

Usage:
    from kimiko.skills import SkillRegistry

    registry = SkillRegistry()
    registry.auto_discover()
    tools = registry.get_all_tool_definitions()
    result = registry.execute_tool("get_current_time", {})
"""
import importlib
import pkgutil
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional

from kimiko.core.logger import get_logger

logger = get_logger("skills.registry")


class BaseSkill(ABC):
    """Abstract base class for all Kimiko skills.

    Subclasses must define:
        name:             Unique skill identifier string
        tool_definitions: List of Gemini function-calling tool dicts
        execute():        Handler that receives tool_name + args and returns a result dict
    """

    name: str = ""
    tool_definitions: List[Dict[str, Any]] = []

    @abstractmethod
    def execute(self, tool_name: str, args: dict) -> dict:
        """Execute a tool call and return a result dict.

        Args:
            tool_name: The function name Gemini invoked.
            args:      Parsed arguments dict from the model.

        Returns:
            A dict with at minimum {"status": "success"|"error", ...}
        """
        ...

    def __repr__(self) -> str:
        tool_names = [t.get("name", "?") for t in self.tool_definitions]
        return f"<{self.__class__.__name__} name={self.name!r} tools={tool_names}>"


class SkillRegistry:
    """Central registry that auto-discovers, stores, and dispatches skill tool calls."""

    def __init__(self) -> None:
        self.skills: Dict[str, BaseSkill] = {}          # skill_name -> instance
        self._tool_map: Dict[str, BaseSkill] = {}       # tool_name -> owning skill
        self._all_tool_defs: List[Dict[str, Any]] = []  # merged list for Gemini

    def register(self, skill: BaseSkill) -> None:
        """Register a skill instance. Raises ValueError on duplicate tool names."""
        if not skill.name:
            raise ValueError(f"Skill {skill.__class__.__name__} has no 'name' attribute.")

        if skill.name in self.skills:
            logger.warning(f"Skill '{skill.name}' already registered — skipping duplicate.")
            return

        # Check for tool name collisions and ensure Gemini schema requirements
        for tool_def in skill.tool_definitions:
            if "type" not in tool_def:
                tool_def["type"] = "function"
            tool_name = tool_def.get("name", "")
            if tool_name in self._tool_map:
                existing = self._tool_map[tool_name]
                raise ValueError(
                    f"Tool name '{tool_name}' from skill '{skill.name}' "
                    f"collides with skill '{existing.name}'."
                )
            self._tool_map[tool_name] = skill

        self.skills[skill.name] = skill
        self._all_tool_defs.extend(skill.tool_definitions)
        tool_names = [t.get("name") for t in skill.tool_definitions]
        logger.info(f"Registered skill '{skill.name}' with tools: {tool_names}")

    def get_all_tool_definitions(self) -> List[Dict[str, Any]]:
        """Return the merged list of all tool definitions for Gemini."""
        return self._all_tool_defs

    def execute_tool(self, tool_name: str, args: dict) -> dict:
        """Dispatch a tool call to the owning skill.

        Args:
            tool_name: The function name from Gemini's tool call.
            args:      Parsed arguments dict.

        Returns:
            Result dict from the skill's execute() method.
        """
        skill = self._tool_map.get(tool_name)
        if skill is None:
            logger.error(f"No skill registered for tool '{tool_name}'.")
            return {"status": "error", "message": f"Unknown tool: {tool_name}"}

        logger.info(f"Dispatching tool '{tool_name}' to skill '{skill.name}'")
        try:
            return skill.execute(tool_name, args)
        except Exception as e:
            logger.error(f"Skill '{skill.name}' failed executing '{tool_name}': {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def auto_discover(self) -> None:
        """Auto-discover and register all *_skill.py modules in this package."""
        package = importlib.import_module("kimiko.skills")
        package_path = package.__path__

        for importer, module_name, is_pkg in pkgutil.iter_modules(package_path):
            if not module_name.endswith("_skill"):
                continue

            try:
                module = importlib.import_module(f"kimiko.skills.{module_name}")
            except Exception as e:
                logger.warning(f"Failed to import skill module '{module_name}': {e}")
                continue

            # Find all BaseSkill subclasses in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseSkill)
                    and attr is not BaseSkill
                    and attr.name  # skip abstract classes without a name
                ):
                    try:
                        instance = attr()
                        self.register(instance)
                    except Exception as e:
                        logger.warning(f"Failed to instantiate skill '{attr_name}': {e}")

        logger.info(
            f"Auto-discovery complete: {len(self.skills)} skill(s), "
            f"{len(self._tool_map)} tool(s) registered."
        )
