import aiohttp
from aiohttp import TCPConnector
from homeassistant.exceptions import HomeAssistantError
from .const import LOGGER, ZHIPUAI_URL

async def send_ai_request(api_key: str, payload: dict) -> dict:
    try:
        connector = TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            async with session.post(ZHIPUAI_URL, json=payload, headers=headers) as response:
                if response.status != 200:
                    raise HomeAssistantError(f"AI 返回状态 {response.status}")
                result = await response.json()
                return result

    except Exception as err:
        LOGGER.error(f"与 AI 通信时出错: {err}")
        raise HomeAssistantError(f"与 AI 通信时出错: {err}")
