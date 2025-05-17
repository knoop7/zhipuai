from __future__ import annotations

import json
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
    CONF_WEB_SEARCH,
    DEFAULT_WEB_SEARCH
)

WEB_SEARCH_API_URL = "https://open.bigmodel.cn/api/paas/v4/web_search"

WEB_SEARCH_SCHEMA = vol.Schema({
    vol.Required("query"): cv.string,
    vol.Optional("stream", default=False): cv.boolean,
    vol.Optional("search_engine", default="search_std"): cv.string,
    vol.Optional("time_query", default=""): cv.string,
})

async def async_setup_web_search(hass: HomeAssistant) -> None:
    
    async def handle_web_search(call: ServiceCall) -> None:
        try:
            config_entries = hass.config_entries.async_entries(DOMAIN)
            if not config_entries:
                raise ValueError("未找到 ZhipuAI 配置")
            
            entry = config_entries[0]
            if not entry.options.get(CONF_WEB_SEARCH, DEFAULT_WEB_SEARCH):
                raise ValueError("联网搜索功能已关闭，请在配置中开启")
                
            api_key = entry.data.get("api_key")
            if not api_key:
                raise ValueError("在配置中找不到 API 密钥")

            query = call.data["query"]
            stream = call.data.get("stream", False)
            search_engine = call.data.get("search_engine", "search_std")
            time_query = call.data.get("time_query", "")
            
            request_id = str(uuid.uuid4())
            
            
            search_query = query
            if time_query:
                search_query = f"{query} {time_query}"

            payload = {
                "request_id": request_id,
                "search_engine": search_engine,
                "search_query": search_query
            }

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            try:
                response = await hass.async_add_executor_job(
                    lambda: requests.post(
                        WEB_SEARCH_API_URL,
                        headers=headers,
                        json=payload,
                        stream=stream,
                        timeout=300
                    )
                )
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
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
                                if 'search_result' in json_data:
                                    search_results = json_data.get('search_result', [])
                                    for result in search_results:
                                        if result_content := result.get('content'):
                                            accumulated_text += result_content + "\n"
                                            if link := result.get('link'):
                                                accumulated_text += f"来源: {link}\n"
                                            accumulated_text += "---\n"
                                            hass.bus.async_fire(
                                                f"{DOMAIN}_stream_token",
                                                {
                                                    "event_id": event_id,
                                                    "content": result_content,
                                                    "full_content": accumulated_text
                                                }
                                            )
                            except json.JSONDecodeError:
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
                    hass.bus.async_fire(f"{DOMAIN}_stream_error", {
                        "event_id": event_id,
                        "error": error_msg
                    })
                    return {"success": False, "message": error_msg}
            else:
                result = response.json()
                content = ""
                
                if "error" in result:
                    return {"success": False, "message": f"API返回错误: {result.get('error')}"}
                
                if "search_result" in result:
                    search_results = result.get("search_result", [])
                    for result_item in search_results:
                        title = result_item.get("title", "")
                        if title:
                            content += f"标题: {title}\n"
                        
                        if result_content := result_item.get("content"):
                            content += f"{result_content}\n"
                            
                        if link := result_item.get("link"):
                            content += f"来源: {link}\n"
                            
                        content += "---\n"
                
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
