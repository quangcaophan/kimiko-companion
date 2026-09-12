"""
DateTime Skill — Current time, date, and day-of-week.

No external API keys required. Uses Python's built-in datetime module.
"""
from datetime import datetime, timezone, timedelta
from kimiko.skills import BaseSkill
from kimiko.core.logger import get_logger

logger = get_logger("skills.datetime")

# Vietnam timezone (UTC+7)
_VN_TZ = timezone(timedelta(hours=7))


class DateTimeSkill(BaseSkill):
    """Provides current time and date information."""

    name = "datetime"

    tool_definitions = [
        {
            "type": "function",
            "name": "get_current_time",
            "description": (
                "Get the current local time. Use when the user asks "
                "\"what time is it?\", \"mấy giờ rồi?\", or similar."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "type": "function",
            "name": "get_current_date",
            "description": (
                "Get the current date including day of week. Use when the user asks "
                "\"what day is it?\", \"hôm nay ngày mấy?\", or similar."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    ]

    def execute(self, tool_name: str, args: dict) -> dict:
        if tool_name == "get_current_time":
            return self._get_time()
        if tool_name == "get_current_date":
            return self._get_date()

        logger.warning(f"Unknown datetime tool: {tool_name}")
        return {"status": "error", "message": f"Unknown tool: {tool_name}"}

    def _get_time(self) -> dict:
        now = datetime.now(_VN_TZ)
        time_str = now.strftime("%I:%M %p")  # e.g. "08:19 PM"
        time_24h = now.strftime("%H:%M")      # e.g. "20:19"
        logger.info(f"get_current_time -> {time_24h}")
        return {
            "status": "success",
            "time": time_str,
            "time_24h": time_24h,
            "timezone": "Asia/Ho_Chi_Minh (UTC+7)",
        }

    def _get_date(self) -> dict:
        now = datetime.now(_VN_TZ)
        date_str = now.strftime("%A, %B %d, %Y")  # e.g. "Friday, September 12, 2026"
        iso_date = now.strftime("%Y-%m-%d")
        day_of_week = now.strftime("%A")
        logger.info(f"get_current_date -> {iso_date} ({day_of_week})")
        return {
            "status": "success",
            "date": date_str,
            "iso_date": iso_date,
            "day_of_week": day_of_week,
            "timezone": "Asia/Ho_Chi_Minh (UTC+7)",
        }
