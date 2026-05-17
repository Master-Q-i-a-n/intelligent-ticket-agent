import datetime
import json

import httpx
from langchain_core.tools import tool

from workOrderAI.agent.agent_context import get_current_username_value
from workOrderAI.app.model.database import get_db_connection
from workOrderAI.app.service.rag_service import RagService
from workOrderAI.utils.logger_handler import logger


@tool(description="Summarize related knowledge base content for the current question.")
async def rag_summarize(query: str) -> str:
    result = await RagService().rag_summary_for_suggestion(query)
    return result


@tool(description="Get the current local time.")
async def get_time_now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


async def _get_current_city_name(client: httpx.AsyncClient) -> str:
    response = await client.get("https://myip.ipip.net/json", timeout=5.0)
    data = response.json()
    location = data.get("data", {}).get("location") or []
    return str(location[2] if len(location) > 2 else "").strip()


def _city_search_candidates(city: str) -> list[str]:
    city = str(city or "").strip()
    candidates = [city] if city else []
    if city.endswith("市"):
        candidates.append(city[:-1])
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


async def _lookup_city_coordinates(client: httpx.AsyncClient, city: str) -> tuple[float, float] | None:
    for candidate in _city_search_candidates(city):
        response = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={
                "name": candidate,
                "count": 1,
                "language": "zh",
                "format": "json",
            },
            timeout=10.0,
        )
        data = response.json()
        results = data.get("results") or []
        if results:
            result = results[0]
            latitude = result.get("latitude")
            longitude = result.get("longitude")
            if latitude is not None and longitude is not None:
                return float(latitude), float(longitude)
    return None


async def _fetch_weather_for_coordinates(
    client: httpx.AsyncClient,
    city: str,
    latitude: float,
    longitude: float,
) -> str:
    response = await client.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "Asia/Shanghai",
        },
        timeout=15.0,
    )
    data = response.json()
    current = data.get("current", {})
    temp = current.get("temperature_2m", "unknown")
    humidity = current.get("relative_humidity_2m", "unknown")
    wind_speed = current.get("wind_speed_10m", "unknown")
    return f"{city} weather: temperature {temp}C, humidity {humidity}%, wind speed {wind_speed}km/h"


@tool(description="Get current weather information for the current user city.")
async def get_current_weather() -> str:
    try:
        async with httpx.AsyncClient() as client:
            city = await _get_current_city_name(client)
            if not city:
                return "failed to get current weather: current city is unavailable"

            coordinates = await _lookup_city_coordinates(client, city)
            if not coordinates:
                return f"failed to get current weather: coordinates not found for {city}"

            return await _fetch_weather_for_coordinates(client, city, *coordinates)
    except Exception as e:
        return f"failed to get current weather: {e}"


def _format_user_records(rows: list[dict]) -> str:
    records = [
        {
            "\u65f6\u95f4": row.get("record_month") or "",
            "\u7279\u5f81": row.get("feature") or "",
            "\u6e05\u6d01\u6548\u7387": row.get("clean_efficiency") or "",
            "\u8017\u6750": row.get("consumable") or "",
            "\u5bf9\u6bd4": row.get("comparison") or "",
        }
        for row in rows
    ]
    return json.dumps(records, ensure_ascii=False)


@tool(description="Get the username of the current work order owner.")
def get_current_username() -> str:
    return get_current_username_value()


@tool(description="Fetch user records from the user_records database table by user id and optional month.")
def fetch_external_data(user_id: str, month: str = "") -> str:
    user_id = str(user_id or "").strip()
    month = str(month or "").strip()
    if not user_id:
        logger.warning("[fetch_external_data] user_id is empty")
        return ""

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            if month:
                cursor.execute(
                    """
                    select record_month, feature, clean_efficiency, consumable, comparison
                    from user_records
                    where owner_username = %s and record_month = %s
                    order by record_month asc
                    """,
                    (user_id, month),
                )
            else:
                cursor.execute(
                    """
                    select record_month, feature, clean_efficiency, consumable, comparison
                    from user_records
                    where owner_username = %s
                    order by record_month asc
                    """,
                    (user_id,),
                )
            rows = cursor.fetchall()
    except Exception as e:
        logger.error(f"[fetch_external_data] database query failed: {e}", exc_info=True)
        return ""
    finally:
        if conn:
            conn.close()

    if not rows:
        logger.warning(f"[fetch_external_data] no records found for user_id={user_id}, month={month or '*'}")
        return json.dumps(
            {
                "found": False,
                "records": [],
                "message": "no records found",
                "user_id": user_id,
                "month": month,
            },
            ensure_ascii=False,
        )

    return _format_user_records(rows)


def get_tools():
    return [
        rag_summarize,
        get_time_now,
        get_current_weather,
        get_current_username,
        fetch_external_data,
    ]


if __name__ == "__main__":
    import asyncio

    async def test():
        weather_result = await get_current_weather.ainvoke({})
        print(weather_result)

    asyncio.run(test())
