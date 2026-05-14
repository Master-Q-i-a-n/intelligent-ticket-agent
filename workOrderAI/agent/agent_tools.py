from langchain_core.tools import tool
from workOrderAI.app.service.rag_service import RagService
import datetime

@tool(description="用于从向量数据库里检索文档并生成摘要，返回摘要")
async def rag_summarize(query: str) -> str:
    """从向量数据库里检索文档并生成摘要"""
    result = await RagService().rag_summary(query)
    return result

@tool(description="用于获取当前年月日时分的工具")
async def get_time_now() -> str:
    """获取当前年月日时分的工具"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

@tool(description="用于获取当前城市的工具")
async def get_current_city() -> str:
    """获取当前城市"""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://myip.ipip.net/json", timeout=5.0)
            data = response.json()
            city = data.get("data", {}).get("location", [])[2] if data.get("data") else "未知"
            return f"当前城市是：{city}"
    except Exception as e:
        return f"获取城市失败：{str(e)}"

@tool(description="用于查询指定城市的天气，输入为城市名称，输出为该城市的天气情况")
async def get_weather(city: str) -> str:
    """查询指定城市的天气"""
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.open-meteo.com/v1/forecast?latitude=31.23&longitude=121.47&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&timezone=Asia/Shanghai",
                timeout=15.0
            )
            data = response.json()
            current = data.get("current", {})
            temp = current.get("temperature_2m", "未知")
            humidity = current.get("relative_humidity_2m", "未知")
            wind_speed = current.get("wind_speed_10m", "未知")
            weather_code = current.get("weather_code", 0)
            weather_map = {
                0: "晴朗", 1: "多云", 2: "多云", 3: "阴天",
                45: "雾", 48: "雾凇", 51: "小毛毛雨", 53: "中毛毛雨", 55: "大毛毛雨",
                61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "大冻雨",
                71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
                80: "小阵雨", 81: "中阵雨", 82: "大阵雨",
                95: "雷暴", 96: "雷暴冰雹", 99: "强雷暴冰雹"
            }
            weather_desc = weather_map.get(weather_code, "未知")
            return f"{city}当前天气：{weather_desc}，温度：{temp}°C，湿度：{humidity}%，风速：{wind_speed}km/h"
    except Exception as e:
        return f"查询天气失败：{str(e)}"

def generate_external_data():
    """
    {
        "user_id": {
            "month" : {"特征": xxx, "效率": xxx, ...}
            "month" : {"特征": xxx, "效率": xxx, ...}
            "month" : {"特征": xxx, "效率": xxx, ...}
            ...
        },
        "user_id": {
            "month" : {"特征": xxx, "效率": xxx, ...}
            "month" : {"特征": xxx, "效率": xxx, ...}
            "month" : {"特征": xxx, "效率": xxx, ...}
            ...
        },
        "user_id": {
            "month" : {"特征": xxx, "效率": xxx, ...}
            "month" : {"特征": xxx, "效率": xxx, ...}
            "month" : {"特征": xxx, "效率": xxx, ...}
            ...
        },
        ...
    }
    :return:
    """
    if not external_data:
        external_data_path = r'E:\MyWork\Agent\workOrder-my\workOrderAI\data\external\records.csv'

        if not os.path.exists(external_data_path):
            raise FileNotFoundError(f"外部数据文件{external_data_path}不存在")

        with open(external_data_path, "r", encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                arr: list[str] = line.strip().split(",")

                user_id: str = arr[0].replace('"', "")
                feature: str = arr[1].replace('"', "")
                efficiency: str = arr[2].replace('"', "")
                consumables: str = arr[3].replace('"', "")
                comparison: str = arr[4].replace('"', "")
                time: str = arr[5].replace('"', "")

                if user_id not in external_data:
                    external_data[user_id] = {}

                external_data[user_id][time] = {
                    "特征": feature,
                    "效率": efficiency,
                    "耗材": consumables,
                    "对比": comparison,
                }


@tool(description="从外部系统中获取指定用户在指定月份的使用记录，以纯字符串形式返回， 如果未检索到返回空字符串")
def fetch_external_data(user_id: str, month: str) -> str:
    generate_external_data()

    try:
        return external_data[user_id][month]
    except KeyError:
        logger.warning(f"[fetch_external_data]未能检索到用户：{user_id}在{month}的使用记录数据")
        return ""

def get_tools():
    """返回本模块的所有工具"""
    return [
        rag_summarize,
        get_time_now,
        get_current_city,
        get_weather,
        fetch_external_data,
    ]

if __name__ == '__main__':
    import asyncio
    async def test():
        city_result = await get_current_city.ainvoke({})
        print(city_result)
        city = city_result.replace("当前城市是：", "").strip()
        weather_result = await get_weather.ainvoke({"city": city})
        print(weather_result)
    asyncio.run(test())


