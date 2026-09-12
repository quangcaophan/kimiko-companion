from typing import Any, Dict
import requests
from kimiko.skills import BaseSkill
from kimiko.core.logger import get_logger

logger = get_logger("skill.weather")


class WeatherSkill(BaseSkill):
    """Skill to fetch current weather and forecasts using wttr.in (free, no API key)."""

    name = "weather"
    description = "Provides real-time weather information and temperature"

    tool_definitions = [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get current weather conditions and temperature for a given city or location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city or location name, e.g. 'Ho Chi Minh', 'Hanoi', 'Tokyo'. Defaults to 'Ho Chi Minh'.",
                    }
                },
                "required": [],
            },
        }
    ]

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name != "get_weather":
            return {"status": "error", "message": f"Unknown tool: {tool_name}"}

        location = arguments.get("location") or "Ho Chi Minh"
        city_query = location.strip().replace(" ", "+")
        url = f"https://wttr.in/{city_query}?format=j1"

        try:
            logger.info(f"Fetching weather for: {location}")
            resp = requests.get(
                url,
                timeout=6,
                headers={"User-Agent": "Kimiko-Companion/1.0"},
            )

            if resp.status_code != 200:
                return {
                    "status": "error",
                    "message": f"Could not retrieve weather (HTTP {resp.status_code})",
                }

            data = resp.json()
            current = data.get("current_condition", [{}])[0]
            today_forecast = data.get("weather", [{}])[0]

            condition_desc = (
                current.get("weatherDesc", [{}])[0].get("value", "Unknown")
            )
            result = {
                "status": "success",
                "location": location,
                "temperature_c": f"{current.get('temp_C', 'N/A')} C",
                "feels_like_c": f"{current.get('FeelsLikeC', 'N/A')} C",
                "condition": condition_desc,
                "humidity": f"{current.get('humidity', 'N/A')}%",
                "wind_speed_kmph": current.get("windspeedKmph", "N/A"),
                "uv_index": current.get("uvIndex", "N/A"),
                "temp_max_c": f"{today_forecast.get('maxtempC', 'N/A')} C",
                "temp_min_c": f"{today_forecast.get('mintempC', 'N/A')} C",
            }

            logger.info(
                f"Weather result -> {location}: {result['temperature_c']}, {condition_desc}"
            )
            return result

        except requests.exceptions.Timeout:
            logger.error(f"Weather request timed out for {location}")
            return {"status": "error", "message": "Weather service timed out."}
        except Exception as e:
            logger.error(f"Weather request failed: {e}")
            return {"status": "error", "message": f"Failed to get weather: {str(e)}"}
