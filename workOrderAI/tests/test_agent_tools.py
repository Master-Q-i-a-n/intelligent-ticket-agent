import unittest
from unittest.mock import AsyncMock, patch

from workOrderAI.agent.agent_tools import get_current_weather, get_tools


class CurrentWeatherToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_current_weather_uses_single_internal_flow(self):
        with (
            patch("workOrderAI.agent.agent_tools._get_current_city_name", AsyncMock(return_value="无锡市")),
            patch("workOrderAI.agent.agent_tools._lookup_city_coordinates", AsyncMock(return_value=(31.49, 120.31))),
            patch(
                "workOrderAI.agent.agent_tools._fetch_weather_for_coordinates",
                AsyncMock(return_value="无锡市 weather: temperature 21.5C, humidity 76%, wind speed 11.6km/h"),
            ),
        ):
            result = await get_current_weather.ainvoke({})

        self.assertIn("无锡市 weather", result)

    def test_public_tools_expose_only_combined_weather_tool(self):
        tool_names = [tool.name for tool in get_tools()]
        self.assertIn("get_current_weather", tool_names)
        self.assertNotIn("get_current_city", tool_names)
        self.assertNotIn("get_weather", tool_names)


if __name__ == "__main__":
    unittest.main()
