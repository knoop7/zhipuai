from __future__ import annotations

import json
import logging
import uuid
import time
from typing import Any, Dict

import voluptuous as vol
import requests
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    LOGGER,
    ZHIPUAI_WEB_SEARCH_URL,
)

WEB_SEARCH_SCHEMA = vol.Schema({
    vol.Required("query"): cv.string,
    vol.Optional("stream", default=False): cv.boolean,
})

async def async_setup_web_search(hass: HomeAssistant) -> None:
    
    async def handle_web_search(call: ServiceCall) -> None:
        try:
            config_entries = hass.config_entries.async_entries(DOMAIN)
            if not config_entries:
                raise ValueError("未找到 ZhipuAI 配置")
            api_key = config_entries[0].data.get("api_key")
            if not api_key:
                raise ValueError("在配置中找不到 API 密钥")

            query = call.data["query"]
            stream = call.data.get("stream", False)
            request_id = str(uuid.uuid4())

            messages = [{"role": "user", "content": query}]
            payload = {
                "request_id": request_id,
                "tool": "web-search-pro",
                "stream": stream,
                "messages": messages
            }

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }

            try:
                response = await hass.async_add_executor_job(
                    lambda: requests.post(
                        ZHIPUAI_WEB_SEARCH_URL,
                        headers=headers,
                        json=payload,
                        stream=stream,
                        timeout=300
                    )
                )
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                LOGGER.error(f"API请求失败: {str(e)}")
                raise ServiceValidationError(f"API请求失败: {str(e)}")

            if stream:
                event_id = f"zhipuai_response_{int(time.time())}"
                
                try:
                    hass.bus.async_fire(f"{DOMAIN}_stream_start", {
                        "event_id": event_id,
                        "type": "web_search"
                    })
                    
                    accumulated_text = ""
                    for line in response.iter_lines():
                        if line:
                            try:
                                line_text = line.decode('utf-8').strip()
                                if line_text.startswith('data: '):
                                    line_text = line_text[6:]
                                if line_text == '[DONE]':
                                    break
                                
                                json_data = json.loads(line_text)
                                if 'choices' in json_data and json_data['choices']:
                                    choice = json_data['choices'][0]
                                    if 'message' in choice and 'tool_calls' in choice['message']:
                                        tool_calls = choice['message']['tool_calls']
                                        for tool_call in tool_calls:
                                            if tool_call.get('type') == 'search_result':
                                                search_results = tool_call.get('search_result', [])
                                                for result in search_results:
                                                    content = result.get('content', '')
                                                    if content:
                                                        accumulated_text += content + "\n"
                                                        hass.bus.async_fire(
                                                            f"{DOMAIN}_stream_token",
                                                            {
                                                                "event_id": event_id,
                                                                "content": content,
                                                                "full_content": accumulated_text
                                                            }
                                                        )
                            except json.JSONDecodeError as e:
                                LOGGER.error(f"解析流式响应失败: {str(e)}")
                                continue
                    
                    hass.bus.async_fire(f"{DOMAIN}_stream_end", {
                        "event_id": event_id,
                        "full_content": accumulated_text
                    })
                    
                    hass.bus.async_fire(f"{DOMAIN}_response", {
                        "type": "web_search",
                        "content": accumulated_text,
                        "success": True
                    })
                    return {"success": True, "event_id": event_id, "message": accumulated_text}
                    
                except Exception as e:
                    error_msg = f"处理流式响应时出错: {str(e)}"
                    LOGGER.error(error_msg)
                    hass.bus.async_fire(f"{DOMAIN}_stream_error", {
                        "event_id": event_id,
                        "error": error_msg
                    })
                    return {"success": False, "message": error_msg}
            else:
                result = response.json()
                content = ""
                if result.get("choices") and result["choices"][0].get("message", {}).get("tool_calls"):
                    tool_calls = result["choices"][0]["message"]["tool_calls"]
                    for tool_call in tool_calls:
                        if tool_call.get("type") == "search_result":
                            search_results = tool_call.get("search_result", [])
                            for result in search_results:
                                if result_content := result.get("content"):
                                    content += result_content + "\n"
                
                if content:
                    hass.bus.async_fire(f"{DOMAIN}_response", {
                        "type": "web_search",
                        "content": content,
                        "success": True
                    })
                    return {"success": True, "message": content}
                else:
                    error_msg = "未从API获取到搜索结果"
                    return {"success": False, "message": error_msg}

        except Exception as e:
            error_msg = f"Web search failed: {str(e)}"
            LOGGER.error(f"网络搜索错误: {str(e)}")
            return {"success": False, "message": error_msg}

    hass.services.async_register(
        DOMAIN,
        "web_search",
        handle_web_search,
        schema=WEB_SEARCH_SCHEMA,
        supports_response=True
    )

    @callback
    def async_unload_services() -> None:
        hass.services.async_remove(DOMAIN, "web_search")

    return async_unload_services
