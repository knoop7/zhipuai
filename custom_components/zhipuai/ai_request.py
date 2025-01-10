import aiohttp
from aiohttp import TCPConnector
from homeassistant.exceptions import HomeAssistantError
from .const import LOGGER, ZHIPUAI_URL

_SESSION = None

async def get_session():
    global _SESSION
    if _SESSION is None:
        connector = TCPConnector(ssl=False)
        _SESSION = aiohttp.ClientSession(connector=connector)
    return _SESSION

async def send_ai_request(api_key: str, payload: dict) -> dict:
    try:
        session = await get_session()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.post(ZHIPUAI_URL, json=payload, headers=headers, timeout=timeout) as response:
            if response.status != 200:
                raise HomeAssistantError(f"AI 返回状态 {response.status}")
            result = await response.json()
            return result

    except Exception as err:
        LOGGER.error(f"与 AI 通信时出错: {err}")
        raise HomeAssistantError(f"与 AI 通信时出错: {err}")
