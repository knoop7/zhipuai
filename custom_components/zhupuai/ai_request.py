import aiohttp
from aiohttp import TCPConnector
from homeassistant.exceptions import HomeAssistantError
from .const import LOGGER, ZHIPUAI_URL, CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT

_SESSION = None

async def get_session():
    global _SESSION
    if _SESSION is None:
        connector = TCPConnector(ssl=False)
        _SESSION = aiohttp.ClientSession(connector=connector)
    return _SESSION

async def send_ai_request(api_key: str, payload: dict, options: dict = None) -> dict:
    try:
        session = await get_session()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        timeout = aiohttp.ClientTimeout(total=options.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT))
        async with session.post(ZHIPUAI_URL, json=payload, headers=headers, timeout=timeout) as response:
            if response.status == 401:
                err_str = "API密钥无效或已过期"
            elif response.status == 429:
                err_str = "请求过于频繁，请稍后再试"
            elif response.status in [500, 502, 503]:
                err_str = "AI服务器暂时不可用，请稍后再试"
            elif response.status == 400:
                result = await response.json()
                err_str = f"请求参数错误: {result.get('error', {}).get('message', '未知错误')}"
            elif response.status != 200:
                err_str = f"AI服务返回错误 {response.status}"
            
            if response.status != 200:
                LOGGER.error("AI请求错误: %s", err_str)
                raise HomeAssistantError(err_str)
                
            result = await response.json()
            if "error" in result:
                err_msg = result["error"].get("message", "未知错误")
                LOGGER.error("AI返回错误: %s", err_msg)
                if "token" in err_msg.lower():
                    raise HomeAssistantError("生成的文本太长，请尝试缩短请求或减小max_tokens值")
                elif "rate" in err_msg.lower():
                    raise HomeAssistantError("请求过于频繁，请稍后再试")
                else:
                    raise HomeAssistantError(f"AI服务返回错误: {err_msg}")
            return result

    except Exception as err:
        err_str = str(err).lower() if str(err) else "未知错误"
        LOGGER.error("AI通信错误: %s", err_str)
        
        if not err_str or err_str.isspace():
            error_msg = "与AI服务通信失败，请检查网络连接和API密钥配置。"
        else:
            error_msg = "很抱歉，我现在无法正确处理您的请求。" + (
                "网络连接失败，请检查网络设置。" if any(x in err_str for x in ["通信", "communication", "connect", "socket"]) else
                "请求超时，尝试减小max_tokens值或缩短请求。" if any(x in err_str for x in ["timeout", "connection", "network"]) else
                "API密钥无效或已过期，请更新配置。" if any(x in err_str for x in ["api key", "token", "unauthorized", "authentication"]) else
                "请求参数错误，请检查配置。" if "参数" in err_str or "parameter" in err_str else
                f"发生错误: {err_str}"
            )
        
        LOGGER.error("与 AI 通信时出错: %s", err_str)
        raise HomeAssistantError(error_msg)