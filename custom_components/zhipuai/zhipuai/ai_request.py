from __future__ import annotations
import aiohttp
import json
import asyncio
import time
from typing import AsyncGenerator, Dict, Any, Protocol, Callable
from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import HomeAssistant
from .const import (
    LOGGER, ZHIPUAI_URL, CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT,
    ERROR_INVALID_AUTH, ERROR_TOO_MANY_REQUESTS, ERROR_SERVER_ERROR, ERROR_TIMEOUT, ERROR_UNKNOWN
)

_SESSION = None

async def get_session() -> aiohttp.ClientSession:
    global _SESSION
    if _SESSION is None:
        connector = aiohttp.TCPConnector(
            limit=10,             
            limit_per_host=5,      
            keepalive_timeout=20.0
        )
        _SESSION = aiohttp.ClientSession(connector=connector)
    return _SESSION

class AIRequestHandler(Protocol):
    async def send_request(self, api_key: str, payload: Dict[str, Any], options: Dict[str, Any]) -> Any: pass
    async def handle_tool_call(self, api_key: str, tool_call: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]: pass

def _handle_error_status(status: int, error_text: str) -> None:
    if status == 401:
        raise HomeAssistantError(ERROR_INVALID_AUTH)
    elif status == 429:
        raise HomeAssistantError(ERROR_TOO_MANY_REQUESTS)
    elif status in [500, 502, 503, 504]:
        raise HomeAssistantError(ERROR_SERVER_ERROR)
    else:
        raise HomeAssistantError(f"{ERROR_UNKNOWN}: {error_text}")

class StreamingRequestHandler:
    async def send_request(self, api_key: str, payload: Dict[str, Any], options: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        payload["stream"] = True
        if "request_id" not in payload:
            payload["request_id"] = f"req_{int(time.time() * 1000)}"
        
        LOGGER.info("发送给AI的消息: %s", json.dumps(payload, ensure_ascii=False))

        for attempt in range(3):
            try:
                session = await get_session()
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                timeout = aiohttp.ClientTimeout(total=options.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT))
                api_url = options.get("base_url", ZHIPUAI_URL)
                
                async with session.post(api_url, json=payload, headers=headers, timeout=timeout) as response:
                    if response.status != 200:
                        _handle_error_status(response.status, await response.text())

                    buffer = ""
                    async for chunk in response.content:
                        if not chunk: 
                            continue
                            
                        chunk_text = chunk.decode('utf-8')
                        buffer += chunk_text
                        
                        lines = buffer.split("\n")
                        if len(lines) > 1:
                            buffer = lines.pop()
                            
                            for line in lines:
                                line = line.strip()
                                if not line or line == "data: [DONE]":
                                    continue
                                    
                                if line.startswith("data: "):
                                    try:
                                        yield json.loads(line[6:])
                                    except:
                                        pass
                    
                    if buffer.startswith("data: ") and "data: [DONE]" not in buffer:
                        try:
                            yield json.loads(buffer[6:])
                        except:
                            pass
                    
                    return
                    
            except (aiohttp.ClientConnectorError, aiohttp.ServerTimeoutError, aiohttp.ClientOSError, asyncio.TimeoutError):
                if attempt < 2: 
                    await asyncio.sleep(1.0)
            except Exception as e:
                raise HomeAssistantError(f"{ERROR_UNKNOWN}: {str(e)}")
        
        raise HomeAssistantError(f"{ERROR_UNKNOWN}")

    async def handle_tool_call(self, api_key: str, tool_call: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(3):
            try:
                session = await get_session()
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                timeout = aiohttp.ClientTimeout(total=options.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT))
                api_url = options.get("base_url", ZHIPUAI_URL)
                tool_url = f"{api_url}/tool_calls"
                
                payload = {
                    "tool_call_id": tool_call["id"],
                    "name": tool_call["function"]["name"],
                    "arguments": tool_call["function"]["arguments"],
                    "stream": False
                }
                
                async with session.post(tool_url, json=payload, headers=headers, timeout=timeout) as response:
                    if response.status != 200:
                        _handle_error_status(response.status, await response.text())
                    return await response.json()
                    
            except (aiohttp.ClientConnectorError, aiohttp.ServerTimeoutError, aiohttp.ClientOSError, asyncio.TimeoutError):
                if attempt < 2: 
                    await asyncio.sleep(1.0)
            except Exception as e:
                raise HomeAssistantError(f"{ERROR_UNKNOWN}: {str(e)}")
                
        raise HomeAssistantError(f"{ERROR_UNKNOWN}")

class DirectRequestHandler:
    async def send_request(self, api_key: str, payload: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
        for attempt in range(3):
            try:
                session = await get_session()
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                timeout = aiohttp.ClientTimeout(total=options.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT))
                payload_copy = dict(payload)
                payload_copy["stream"] = False
                
                api_url = options.get("base_url", ZHIPUAI_URL)
                async with session.post(api_url, json=payload_copy, headers=headers, timeout=timeout) as response:
                    response_json = await response.json()
                    if response.status != 200:
                        _handle_error_status(response.status, str(response_json))
                    return response_json
                    
            except (aiohttp.ClientConnectorError, aiohttp.ServerTimeoutError, aiohttp.ClientOSError, asyncio.TimeoutError):
                if attempt < 2: 
                    await asyncio.sleep(1.0)
            except Exception as e:
                raise HomeAssistantError(f"{ERROR_UNKNOWN}: {str(e)}")
                
        raise HomeAssistantError(f"{ERROR_UNKNOWN}")

    async def handle_tool_call(self, api_key: str, tool_call: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
        return await StreamingRequestHandler().handle_tool_call(api_key, tool_call, options)

def create_request_handler(streaming: bool = True) -> AIRequestHandler:
    return StreamingRequestHandler() if streaming else DirectRequestHandler()

async def send_ai_request(api_key: str, payload: Dict[str, Any], options: Dict[str, Any] = None, timeout=30) -> AsyncGenerator[Dict[str, Any], None]:
    options = options or {}
    handler = create_request_handler(True)
    async for chunk in handler.send_request(api_key, payload, options):
        yield chunk

async def send_api_request(api_key: str, payload: Dict[str, Any], options: Dict[str, Any] = None, timeout=30) -> Dict[str, Any]:
    options = options or {}
    handler = create_request_handler(False)
    return await handler.send_request(api_key, payload, options)

async def handle_tool_call(api_key: str, tool_call: Dict[str, Any], options: Dict[str, Any] = None) -> Dict[str, Any]:
    options = options or {}
    handler = create_request_handler(False)
    return await handler.handle_tool_call(api_key, tool_call, options)