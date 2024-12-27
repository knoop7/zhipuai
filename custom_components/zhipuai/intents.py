from __future__ import annotations
import logging
import re
from datetime import timedelta
from typing import Any, Dict, List, Optional, Set
import voluptuous as vol
from homeassistant.components import camera
from homeassistant.components.conversation import DOMAIN as CONVERSATION_DOMAIN
from homeassistant.components.lock import LockState
from homeassistant.components.timer import (
    ATTR_DURATION, ATTR_REMAINING,
    CONF_DURATION, CONF_ICON,
    DOMAIN as TIMER_DOMAIN,
    SERVICE_START, SERVICE_PAUSE, SERVICE_CANCEL
)
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_ENTITY_ID
from homeassistant.core import Context, HomeAssistant, ServiceResponse, State
from homeassistant.helpers import area_registry, device_registry, entity_registry, intent
from .const import DOMAIN, LOGGER

INTENT_CAMERA_ANALYZE = "ZhipuAICameraAnalyze"
INTENT_WEB_SEARCH = "ZhipuAIWebSearch"
INTENT_NEVERMIND = "nevermind"
SERVICE_PROCESS = "process"
ERROR_NO_CAMERA = "no_camera"
ERROR_NO_RESPONSE = "no_response"
ERROR_SERVICE_CALL = "service_call_error"
ERROR_NO_QUERY = "no_query"

_LOGGER = logging.getLogger(__name__)

async def async_setup_intents(hass: HomeAssistant) -> None:
    intent.async_register(hass, CameraAnalyzeIntent())
    intent.async_register(hass, WebSearchIntent())


class CameraAnalyzeIntent(intent.IntentHandler):
    intent_type = INTENT_CAMERA_ANALYZE
    slot_schema = {vol.Required("camera_name"): str, vol.Required("question"): str}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        target_camera = next((e for e in intent_obj.hass.states.async_all(camera.DOMAIN) 
            if slots["camera_name"]["value"].lower() in (e.name.lower(), e.entity_id.lower())), None)
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        return (self._set_error_response(response, ERROR_NO_CAMERA, f"找不到名为 {slots['camera_name']['value']} 的摄像头") 
            if not target_camera else await self._handle_camera_analysis(intent_obj.hass, response, target_camera, slots["question"]["value"]))

    async def _handle_camera_analysis(self, hass, response, target_camera, question) -> intent.IntentResponse:
        try:
            result = await hass.services.async_call(DOMAIN, "image_analyzer", 
                service_data={"model": "glm-4v-flash", "temperature": 0.8, "max_tokens": 1024, 
                    "stream": False, "image_entity": target_camera.entity_id, "message": question}, 
                blocking=True, return_response=True)
            return (self._set_speech_response(response, result.get("message", "")) 
                if result and isinstance(result, dict) and result.get("success", False) else 
                self._set_error_response(response, ERROR_SERVICE_CALL, result.get("message", "服务调用失败")) 
                if result and isinstance(result, dict) else 
                self._set_error_response(response, ERROR_NO_RESPONSE, "未能获取到有效的分析结果"))
        except Exception as e:
            _LOGGER.error("Error calling image analyzer service: %s", str(e))
            return self._set_error_response(response, ERROR_SERVICE_CALL, f"服务调用出错：{str(e)}")

    def _set_error_response(self, response, code, message) -> intent.IntentResponse:
        response.async_set_error(code=code, message=message)
        return response

    def _set_speech_response(self, response, message) -> intent.IntentResponse:
        response.async_set_speech(message)
        return response


class WebSearchIntent(intent.IntentHandler):
    intent_type = INTENT_WEB_SEARCH
    slot_schema = {vol.Required("query"): str}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        query = slots["query"]["value"]
        
        if not query:
            response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
            return self._set_error_response(response, ERROR_NO_QUERY, "未提供搜索内容")
        
        return await self._handle_web_search(intent_obj.hass, intent_obj, query)

    async def _handle_web_search(
        self, hass: HomeAssistant, intent_obj: intent.Intent, query: str
    ) -> intent.IntentResponse:
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        
        try:
            result = await hass.services.async_call(
                DOMAIN,
                "web_search",
                service_data={
                    "query": query,
                    "stream": False
                },
                blocking=True,
                return_response=True
            )
            
            if result and isinstance(result, dict):
                if result.get("success", False):
                    return self._set_speech_response(response, result.get("message", ""))
                return self._set_error_response(
                    response, ERROR_SERVICE_CALL, result.get("message", "搜索服务调用失败")
                )
            
            return self._set_error_response(
                response, ERROR_NO_RESPONSE, "未能获取到有效的搜索结果"
            )
            
        except Exception as e:
            return self._set_error_response(
                response, ERROR_SERVICE_CALL, f"搜索服务调用出错：{str(e)}"
            )

    def _set_error_response(self, response, code, message) -> intent.IntentResponse:
        response.async_set_error(code=code, message=message)
        return response

    def _set_speech_response(self, response, message) -> intent.IntentResponse:
        response.async_set_speech(message)
        return response


def extract_intent_info(user_input: str, hass: HomeAssistant) -> Optional[Dict[str, Any]]:
    entity_match = re.search(r'([\w_]+\.[\w_]+)', user_input)
    entity_id = entity_match.group(1) if entity_match else None
    domain = entity_id.split('.')[0] if entity_id else None
    
    intent_mappings = {
        r'打开|开启|解锁|turn on|open|unlock': 'turn_on',
        r'关闭|关掉|锁定|turn off|close|lock': 'turn_off',
        r'切换|toggle': 'toggle',
        r'停止|暂停|stop|pause': 'stop',
        r'继续|resume': 'start',
        r'设置|调整|set|adjust': 'set',
        r'没事|算了|再见|闭嘴|退下|nevermind|bye': INTENT_NEVERMIND
    }
    
    action = next((action for pattern, action in intent_mappings.items() 
                  if re.search(pattern, user_input)), 'turn_on')
    
    action = 'lock' if domain == 'lock' and action == 'turn_on' else \
             'unlock' if domain == 'lock' and action == 'turn_off' else action

    intent_data = {'domain': domain, 'action': action, 'data': {'entity_id': entity_id}} if entity_id else None

  
    if action == 'set' and intent_data:
        number_match = re.search(r'(\d+)', user_input)
        value = int(number_match.group(1)) if number_match else None
        if value is not None:
            intent_data['data'].update({
                'position': value if domain == 'cover' else
                min(255, value * 255 // 100) if domain == 'light' else
                value if domain == 'climate' else None
            })
    
    return intent_data
    
class IntentHandler:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.area_reg = area_registry.async_get(hass)
        self.device_reg = device_registry.async_get(hass)
        self.entity_reg = entity_registry.async_get(hass)

    async def call_service(self, domain: str, service: str, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            entity_id = data.pop("entity_id", None)
            entity = self.hass.states.get(entity_id)
            friendly_name = entity.attributes.get("friendly_name") if entity else "设备"
            service_data = {**data, "entity_id": entity_id} if entity_id else data
            await self.hass.services.async_call(domain, service, service_data, blocking=True)
            return {"success": True, "message": f"您好，我已执行 {friendly_name}", "data": service_data}
        except Exception as e:
            return {"success": False, "message": str(e), "data": data}

    async def handle_intent(self, intent_info: Dict[str, Any]) -> Dict[str, Any]:
        domain = intent_info.get('domain')
        action = intent_info.get('action', '')
        data = intent_info.get('data', {})
        name = data['name'].get('value') if isinstance(data.get('name'), dict) else data.get('name')
        area = data['area'].get('value') if isinstance(data.get('area'), dict) else data.get('area')
        entity_id = data.get('entity_id')

        return await (
            self.handle_nevermind_intent() if domain == CONVERSATION_DOMAIN and action == INTENT_NEVERMIND else
            self.call_service(domain, action, data) if entity_id and await self._validate_service_for_entity(domain, action, entity_id) else
            self.handle_cover_intent(action, name, area, data) if domain == "cover" else
            self.handle_lock_intent(action, name, area, data) if domain == "lock" else
            self.handle_timer_intent(action, name, area, data) if domain == TIMER_DOMAIN else
            self.call_service(domain, action, data)
        )

    async def handle_nevermind_intent(self) -> Dict[str, Any]:
        try:
            await self.hass.services.async_call(CONVERSATION_DOMAIN, SERVICE_PROCESS, {"text": "再见"}, blocking=True)
            return {"success": True, "message": "再见!", "close_conversation": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def _validate_service_for_entity(self, domain: str, service: str, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return bool(
            state and entity_id in self.hass.states.async_entity_ids() and
            (supported_features := state.attributes.get("supported_features", 0)) and
            not (
                (domain == "fan" and service == "set_percentage" and not (supported_features & 1)) or
                (domain == "cover" and ((service == "close" and not (supported_features & 2)) or
                                      (service == "set_position" and not (supported_features & 4)))) or
                (domain == "lock" and ((service == "unlock" and not (supported_features & 1)) or
                                     (service == "lock" and not (supported_features & 2))))
            )
        )

    async def handle_timer_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        timer_name = name if name else "default"
        entity_id = f"timer.{timer_name}"
        return await (
            self.call_service(TIMER_DOMAIN, SERVICE_START, {"duration": data.get('duration'), "entity_id": entity_id})
            if action == "start" and data.get('duration') else
            self.call_service(TIMER_DOMAIN, SERVICE_PAUSE, {"entity_id": entity_id})
            if action == "pause" and name else
            self.call_service(TIMER_DOMAIN, SERVICE_CANCEL, {"entity_id": entity_id})
            if action == "cancel" and name else
            {"success": False, "message": f"不支持的定时器操作: {action}"}
        )

    async def handle_cover_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        entity_id = data.get('entity_id')
        return (
            {"success": False, "message": "未指定窗帘实体"} if not entity_id else
            await self.call_service("cover", "set_cover_position", 
                {"entity_id": entity_id, "position": data.get('position')})
            if action == "set" and data.get('position') is not None else
            await self.call_service("cover", action, {"entity_id": entity_id})
        )

    async def handle_lock_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        entity_id = data.get('entity_id')
        return (
            {"success": False, "message": "未指定门锁实体"} if not entity_id else
            await self.call_service("lock", action, {"entity_id": entity_id})
        )

def get_intent_handler(hass: HomeAssistant) -> IntentHandler:
    return IntentHandler(hass)