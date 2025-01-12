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
            if response.status == 401:
                err_str = "unauthorized"
            elif response.status == 429:
                err_str = "rate limit"
            elif response.status in [500, 502, 503]:
                err_str = "server"
            elif response.status in [400, 404]:
                err_str = "request"
            elif response.status != 200:
                err_str = f"AI 返回状态 {response.status}"
            
            if response.status != 200:
                raise HomeAssistantError(err_str)
                
            result = await response.json()
            return result

    except Exception as err:
        err_str = str(err).lower()
        error_msg = "很抱歉，我现在无法正确处理您的请求。" + (
            "与AI服务通信失败，请检查网络连接。" if any(x in err_str for x in ["通信", "communication", "connect", "socket"]) else
            "网络连接不稳定，请稍后重试。" if any(x in err_str for x in ["timeout", "connection", "network"]) else
            "API密钥可能已过期，请更新配置。" if any(x in err_str for x in ["api key", "token", "unauthorized", "authentication"]) else
            "服务器暂时无响应，请稍后再试。" if any(x in err_str for x in ["server", "service", "503", "502", "500"]) else
            "请求参数有误，请检查输入。" if any(x in err_str for x in ["request", "400", "404", "参数", "parameter"]) else
            "已达到调用频率限制，请稍后重试。" if any(x in err_str for x in ["rate limit", "too many", "频率", "次数"]) else
            "请稍后再试。与通信失败，请检查。"
        )
        LOGGER.error(f"与 AI 通信时出错: {err}")
        raise HomeAssistantError(error_msg)