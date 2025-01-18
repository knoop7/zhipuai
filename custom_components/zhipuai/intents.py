from __future__ import annotations
import re
import os
import yaml
import asyncio
from datetime import timedelta, datetime
from typing import Any, Dict, List, Optional, Set
import voluptuous as vol
from homeassistant.components import camera
from homeassistant.components.conversation import DOMAIN as CONVERSATION_DOMAIN
from homeassistant.components.lock import LockState
from homeassistant.components.timer import (
    ATTR_DURATION,
    ATTR_REMAINING,
    CONF_DURATION,
    CONF_ICON,
    DOMAIN as TIMER_DOMAIN,
    SERVICE_CANCEL,
    SERVICE_PAUSE,
    SERVICE_START,
)
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_ENTITY_ID
from homeassistant.core import Context, HomeAssistant, ServiceResponse, State
from homeassistant.helpers import area_registry, device_registry, entity_registry, intent
from .const import DOMAIN, LOGGER

_YAML_CACHE = {}

async def async_load_yaml_config(hass: HomeAssistant, path: str) -> dict:
    if path not in _YAML_CACHE:
        if os.path.exists(path):
            def _load_yaml():
                with open(path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            _YAML_CACHE[path] = await hass.async_add_executor_job(_load_yaml)
    return _YAML_CACHE.get(path, {})

INTENT_CAMERA_ANALYZE = "ZhipuAICameraAnalyze"
INTENT_WEB_SEARCH = "ZhipuAIWebSearch"
INTENT_TIMER = "HassTimerIntent"
INTENT_NOTIFY = "HassNotifyIntent"
INTENT_COVER_GET_STATE = "ZHIPUAI_CoverGetStateIntent"
INTENT_COVER_SET_POSITION = "ZHIPUAI_CoverSetPositionIntent"
INTENT_CLIMATE_SET_TEMP = "ClimateSetTemperature"
INTENT_CLIMATE_SET_MODE = "ClimateSetMode"
INTENT_CLIMATE_SET_FAN = "ClimateSetFanMode"
INTENT_NEVERMIND = "nevermind"
SERVICE_PROCESS = "process"
ERROR_NO_CAMERA = "no_camera"
ERROR_NO_RESPONSE = "no_response"
ERROR_SERVICE_CALL = "service_call_error"
ERROR_NO_QUERY = "no_query"
ERROR_NO_TIMER = "no_timer"
ERROR_NO_MESSAGE = "no_message"
ERROR_INVALID_POSITION = "invalid_position"


async def async_setup_intents(hass: HomeAssistant) -> None:
    yaml_path = os.path.join(os.path.dirname(__file__), "intents.yaml")
    intents_config = await async_load_yaml_config(hass, yaml_path)
    if intents_config:
        LOGGER.info("从 %s 加载的 intent 配置", yaml_path)
    
    intent.async_register(hass, CameraAnalyzeIntent(hass))
    intent.async_register(hass, WebSearchIntent(hass))
    intent.async_register(hass, HassTimerIntent(hass))
    intent.async_register(hass, HassNotifyIntent(hass))
    intent.async_register(hass, ClimateSetTemperatureIntent(hass))
    intent.async_register(hass, ClimateSetModeIntent(hass))
    intent.async_register(hass, ClimateSetFanModeIntent(hass))
    intent.async_register(hass, ClimateSetHumidityIntent(hass))
    intent.async_register(hass, ClimateSetSwingModeIntent(hass))
    intent.async_register(hass, CoverControlAllIntent(hass))


class CameraAnalyzeIntent(intent.IntentHandler):
    intent_type = INTENT_CAMERA_ANALYZE
    slot_schema = {vol.Required("camera_name"): str, vol.Required("question"): str}

    def __init__(self, hass: HomeAssistant):
        super().__init__()
        self.hass = hass
        self.config = {}
        self._config_loaded = False

    async def _load_config(self):
        if not self._config_loaded:
            yaml_path = os.path.join(os.path.dirname(__file__), "intents.yaml")
            config = await async_load_yaml_config(self.hass, yaml_path)
            self.config = config.get(INTENT_CAMERA_ANALYZE, {})
            self._config_loaded = True

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        await self._load_config()
        slots = self.async_validate_slots(intent_obj.slots)
        camera_name = self.get_slot_value(slots.get("camera_name"))
        question = self.get_slot_value(slots.get("question"))
        
        LOGGER.info("Camera analyze intent info - 原始插槽: %s", slots)
        
        target_camera = next((e for e in intent_obj.hass.states.async_all(camera.DOMAIN) 
            if camera_name.lower() in (e.name.lower(), e.entity_id.lower())), None)
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        
        if self.config and "speech" in self.config:
            response.async_set_speech(self.config["speech"]["text"])
            
        return (self._set_error_response(response, ERROR_NO_CAMERA, f"找不到名为 {camera_name} 的摄像头") 
            if not target_camera else await self._handle_camera_analysis(intent_obj.hass, response, target_camera, question))

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
            return self._set_error_response(response, ERROR_SERVICE_CALL, f"服务调用出错：{str(e)}")

    def _set_error_response(self, response, code, message) -> intent.IntentResponse:
        response.async_set_error(code=code, message=message)
        return response

    def _set_speech_response(self, response, message) -> intent.IntentResponse:
        response.async_set_speech(message)
        return response

    def get_slot_value(self, slot_data):
        return None if not slot_data else slot_data.get('value') if isinstance(slot_data, dict) else getattr(slot_data, 'value', None) if hasattr(slot_data, 'value') else str(slot_data)


class WebSearchIntent(intent.IntentHandler):
    intent_type = INTENT_WEB_SEARCH
    slot_schema = {
        vol.Required("query"): str,
        vol.Optional("time_query"): str, 
    }

    def __init__(self, hass: HomeAssistant):
        super().__init__()
        self.hass = hass
        self.config = {}
        self._config_loaded = False

    async def _load_config(self):
        if not self._config_loaded:
            yaml_path = os.path.join(os.path.dirname(__file__), "intents.yaml")
            config = await async_load_yaml_config(self.hass, yaml_path)
            self.config = config.get(INTENT_WEB_SEARCH, {})
            self._config_loaded = True

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        await self._load_config()
        slots = self.async_validate_slots(intent_obj.slots)
        query = self.get_slot_value(slots.get("query"))
        time_query = self.get_slot_value(slots.get("time_query"))  
        
        LOGGER.info("Web search info - 原始插槽:%s", slots)
        
        if not query:
            response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
            return self._set_error_response(response, ERROR_NO_QUERY, "未提供搜索内容")
        
        if time_query:
            now = datetime.now()  
            if time_query in ["昨天", "昨日", "yesterday"]:
                date = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            elif time_query in ["明天", "明日", "tomorrow"]:
                date = (now + timedelta(days=1)).strftime('%Y-%m-%d')
            else:  
                date = now.strftime('%Y-%m-%d')
            query = f"{date} {query}"
        
        return await self._handle_web_search(intent_obj.hass, intent_obj, query)

    async def _handle_web_search(
        self, hass: HomeAssistant, intent_obj: intent.Intent, query: str
    ) -> intent.IntentResponse:
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        
        try:
            LOGGER.info("Web search service call - Query: %s", query)
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
                LOGGER.info("Web search result: %s", result)
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
        if len(message.encode('utf-8')) > 24 * 1024:
            message = message[:24 * 1024].rsplit(' ', 1)[0] + "..."
        response.async_set_speech(message)
        return response

    def get_slot_value(self, slot_data):
        return None if not slot_data else slot_data.get('value') if isinstance(slot_data, dict) else getattr(slot_data, 'value', None) if hasattr(slot_data, 'value') else str(slot_data)

class HassTimerIntent(intent.IntentHandler):
    intent_type = "HassTimerIntent"
    slot_schema = {
        vol.Required("action"): str,
        vol.Optional("duration"): str,
        vol.Optional("timer_name"): str
    }

    def __init__(self, hass: HomeAssistant):
        super().__init__()
        self.hass = hass
        self.config = {}
        self._config_loaded = False

    async def _load_config(self):
        if not self._config_loaded:
            yaml_path = os.path.join(os.path.dirname(__file__), "intents.yaml")
            self.config = (await async_load_yaml_config(self.hass, yaml_path)).get("HassTimerIntent", {})
            self._config_loaded = True

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        await self._load_config()
        slots = self.async_validate_slots(intent_obj.slots)
        get_slot_value = lambda slot_name: self.get_slot_value(slots.get(slot_name))
        action = get_slot_value("action")
        duration = get_slot_value("duration")
        timer_name = get_slot_value("timer_name")
        
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        return response.async_set_error(code="no_action", message="未指定操作类型") if not action else await self._handle_timer(response, action, duration, timer_name)

    async def _handle_timer(self, response, action, duration, timer_name):
        action_map = {"set": "start", "add": "start", "create": "start", "stop": "pause", "remove": "cancel", "delete": "cancel", "end": "finish", "提醒": "start"}
        action = action_map.get(action, action)
        LOGGER.info("Hass timer intent info - 原始插槽: %s", {"action": action, "duration": duration, "timer_name": timer_name})

        timer_entities = self.hass.states.async_entity_ids("timer")
        return response.async_set_error(code="no_timer", message="未找到可用的计时器，请先在Home Assistant中创建一个计时器") if not timer_entities else await self._process_timer(response, action, duration, timer_name, timer_entities[0])

    async def _process_timer(self, response, action, duration, timer_name, timer_id):
        time_words = {'早上': 7, '早晨': 7, '上午': 9, '中午': 12, '下午': 14, '晚上': 20, '傍晚': 18, '凌晨': 5,
                     '早饭': 7, '早餐': 7, '午饭': 12, '午餐': 12, '晚饭': 18, '晚餐': 18, '夜宵': 22}

        def parse_time(text):
            return (None, None) if not text else self._parse_time_impl(text.lower(), time_words)

        minutes, is_absolute = parse_time(timer_name) or parse_time(duration) or (None, None)
        
        try:
            data = {}
            if minutes is not None and minutes > 0:
                hours = minutes // 60
                mins = minutes % 60
                data["duration"] = f"{hours:02d}:{mins:02d}:00"
                target_time = datetime.now() + timedelta(minutes=minutes)
                
                if is_absolute:
                    time_str = target_time.strftime('%H:%M')
                    response.async_set_speech(f"好的，已设置{timer_name if timer_name else '计时器'}，将在{time_str}提醒您")
                else:
                    time_str = (f"{hours}小时{mins}分钟后" if hours > 0 and mins > 0 else
                              f"{hours}小时后" if hours > 0 else
                              f"{mins}分钟后")
                    response.async_set_speech(f"好的，已设置{timer_name if timer_name else '计时器'}，将在{time_str}提醒您")
            else:
                response.async_set_speech(f"好的，已{action}计时器")
            await self.hass.services.async_call("timer", action, {"entity_id": timer_id, **data}, blocking=True)
            return response
        except Exception as e:
            return response.async_set_error(code="service_call_error", message=f"操作失败：{str(e)}")

    def _parse_time_impl(self, text, time_words):
        hour_match = re.search(r"(\d+)[点时:](\d+)?", text)
        is_absolute = bool(hour_match or any(word in text for word in time_words.keys()))
        
        if is_absolute:
            target_time = datetime.now() + timedelta(days=("明天" in text) + ("后天" in text) * 2)
            hour = int(hour_match.group(1)) if hour_match else next((h for w, h in time_words.items() if w in text), None)
            minute = int(hour_match.group(2)) if hour_match and hour_match.group(2) else 0
            hour = hour + 12 if hour and hour <= 12 and any(w in text for w in ['下午', '晚上', '傍晚', '晚饭', '晚餐', '夜宵']) else hour
            target_time = target_time.replace(hour=hour, minute=minute) if hour is not None else target_time
            minutes = int((target_time - datetime.now()).total_seconds() / 60)
            return (minutes, True) if minutes > 0 else (None, True)
        
        matches = re.findall(r'(\d+)\s*([小时分钟天hmd]|hour|minute|min|hr|h|m)s?', text)
        total_minutes = sum(int(value) * (60 if unit.startswith('h') or unit in ['小时'] else
                                        1 if unit.startswith('m') or unit in ['分钟'] or unit == 'm' else
                                        24 * 60) for value, unit in matches)
        return total_minutes or None, False

    def get_slot_value(self, slot_data):
        return None if not slot_data else slot_data.get('value') if isinstance(slot_data, dict) else getattr(slot_data, 'value', None) if hasattr(slot_data, 'value') else str(slot_data)


class HassNotifyIntent(intent.IntentHandler):
    intent_type = "HassNotifyIntent"
    slot_schema = {vol.Required("message"): str}

    def __init__(self, hass: HomeAssistant):
        super().__init__()
        self.hass = hass

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")

        try:
            message = self.get_slot_value(intent_obj.slots.get("message"))
            if not message:
                response.async_set_error("no_message", "请提供要发送的通知内容")
                return response

            title_result = await self.hass.services.async_call(
                "conversation", "process", 
                {
                    "agent_id": "conversation.zhi_pu_qing_yan",
                    "language": "zh-cn",
                    "text": f"请为这条消息生成一个简短的标题（不超过8个字）：{message}"
                },
                blocking=True,
                return_response=True
            )

            title = "新通知"
            if title_result and isinstance(title_result, dict):
                ai_title = title_result.get("response", {}).get("speech", {}).get("plain", {}).get("speech", "")
                if ai_title:
                    title = ai_title

            result = await self.hass.services.async_call(
                "conversation", "process", 
                {
                    "agent_id": "conversation.zhi_pu_qing_yan",
                    "language": "zh-cn",
                    "text": f"请将以下内容改写成一条通知消息，只需返回改写后的文本内容，不要添加也不需要执行动作工具任何代码或格式,注意要使用表情emoji：{message}"
                },
                blocking=True,
                return_response=True
            )

            if not result or not isinstance(result, dict):
                response.async_set_error("invalid_response", "AI 响应格式错误")
                return response

            ai_response = result.get("response", {})
            ai_message = ai_response.get("speech", {}).get("plain", {}).get("speech", "")
            if not ai_message:
                ai_message = message

            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            from homeassistant.components import persistent_notification
            persistent_notification.async_create(
                self.hass,
                f"{ai_message}\n\n创建时间：{current_time}",
                title=f"{title}"
            )
            
            response.async_set_speech(f"已创建通知: {message}")
            return response

        except Exception as err:
            LOGGER.exception("发送通知失败")
            response.async_set_error("notification_error", f"发送通知失败: {str(err)}")
            return response

    def get_slot_value(self, slot_data):
        return None if not slot_data else slot_data.get('value') if isinstance(slot_data, dict) else getattr(slot_data, 'value', None) if hasattr(slot_data, 'value') else str(slot_data)


class ClimateBaseIntent(intent.IntentHandler):
    
    def __init__(self, hass: HomeAssistant):
        super().__init__()
        self.hass = hass

    def _set_error_response(self, response, code: str, message: str) -> intent.IntentResponse:
        response.async_set_error(code=code, message=message)
        return response

    def _set_speech_response(self, response, message) -> intent.IntentResponse:
        response.async_set_speech(message)
        return response

    def async_validate_slots(self, slots):
        validated = {}
        for key, value in slots.items():
            if isinstance(value, dict) and "value" in value:
                validated[key] = value["value"]
            else:
                validated[key] = value
        return validated

    def get_slot_value(self, slot_data):
        return None if not slot_data else slot_data.get('value') if isinstance(slot_data, dict) else getattr(slot_data, 'value', None) if hasattr(slot_data, 'value') else str(slot_data)

    def find_climate_entity(self, name: str) -> Optional[State]:
        return next((state for state in self.hass.states.async_all() if state.domain == "climate" and (str(name).lower() in state.attributes.get('friendly_name', '').lower() or str(name).lower() in state.entity_id.lower())), None)

    def get_mode_value(self, mode) -> str:
        return mode.value if hasattr(mode, 'value') else str(mode).strip("'[]")

    def normalize_mode_list(self, modes) -> List[str]:
        return [self.get_mode_value(mode) for mode in (modes.strip("[]").replace("'", "").split(", ") if isinstance(modes, str) else modes)]

    async def ensure_entity_on(self, entity_id: str) -> None:
        state = self.hass.states.get(entity_id)
        state.state == 'off' and await self.hass.services.async_call("climate", "turn_on", {"entity_id": entity_id}) and await asyncio.sleep(1)  

class ClimateSetModeIntent(ClimateBaseIntent):
    intent_type = INTENT_CLIMATE_SET_MODE
    slot_schema = {vol.Required("name"): str, vol.Required("mode"): str}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        name, mode = self.get_slot_value(slots.get("name")), self.get_slot_value(slots.get("mode"))
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        return (self._set_error_response(response, "invalid_slots", "缺少必要的参数") if not name or not mode else 
                self._set_error_response(response, "not_found", f"找不到名为 {name} 的空调") if not (state := self.find_climate_entity(name)) else
                await self._handle_mode_setting(response, state, name, mode))

    async def _handle_mode_setting(self, response, state, name, mode):
        available_modes = self.normalize_mode_list(state.attributes.get('hvac_modes', []))
        mode_maps = {"制冷": ["cool", "cooling"], "制热": ["heat", "heating"], "自动": ["auto", "heat_cool", "automatic"],
                    "除湿": ["dry", "dehumidify"], "送风": ["fan_only", "fan"], "关闭": ["off"], "停止": ["off"]}
        mode_lower = mode.lower()
        target_mode = (mode_lower if mode_lower in available_modes else 
                      next((m for cn_mode, en_modes in mode_maps.items() 
                           for m in en_modes if m in available_modes
                           and (mode_lower == cn_mode.lower() or any(em in mode_lower for em in en_modes))), None))
        return (self._set_error_response(response, "invalid_mode", 
                f"不支持的模式: {mode}。支持的模式: {', '.join([cn_mode for cn_mode, en_modes in mode_maps.items() if any(m in available_modes for m in en_modes)])}") 
                if not target_mode else 
                await self._set_mode(response, state, name, mode, target_mode))

    async def _set_mode(self, response, state, name, mode, target_mode):
        try:
            await self.hass.services.async_call("climate", "set_hvac_mode", 
                {"entity_id": state.entity_id, "hvac_mode": target_mode})
            return self._set_speech_response(response, f"已将{name}设置为{mode}模式")
        except Exception as e:
            return self._set_error_response(response, "operation_failed", f"设置模式失败: {str(e)}")

class ClimateSetFanModeIntent(ClimateBaseIntent):
    intent_type = INTENT_CLIMATE_SET_FAN
    slot_schema = {vol.Required("name"): str, vol.Required("fan_mode"): str}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        name, fan_mode = self.get_slot_value(slots.get("name")), self.get_slot_value(slots.get("fan_mode"))
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        return (self._set_error_response(response, "invalid_slots", "缺少必要的参数") if not name or not fan_mode else
                self._set_error_response(response, "not_found", f"找不到名为 {name} 的空调") if not (state := self.find_climate_entity(name)) else
                await self._handle_fan_mode_setting(response, state, name, fan_mode))

    async def _handle_fan_mode_setting(self, response, state, name, fan_mode):
        await self.ensure_entity_on(state.entity_id)
        available_modes = self.normalize_mode_list(state.attributes.get('fan_modes', []))
        fan_mode_maps = {
            "自动": ["auto", "auto_low", "auto_high", "自动"],
            "低速": ["on_low", "low", "一档", "一挡", "低风"],
            "中速": ["medium", "mid", "二档", "二挡", "中风"],
            "高速": ["on_high", "high", "七档", "高风"],
            "关闭": ["off"]
        }
        fan_mode_clean = str(fan_mode).rstrip('档挡')
        target_mode = (fan_mode if fan_mode in available_modes else
                      next((mode for mode in available_modes if str(fan_mode_clean) in mode or 
                           f"{'一二三四五六七八九十'[int(fan_mode_clean)-1]}" in mode or
                           mode.rstrip('档挡') == fan_mode_clean), None) if fan_mode_clean.isdigit() else
                      next((m for cn_mode, en_modes in fan_mode_maps.items() 
                           for m in en_modes if m in available_modes
                           and (fan_mode_clean == cn_mode or any(em in fan_mode_clean for em in en_modes))), None))
        return (self._set_error_response(response, "invalid_fan_mode", 
                f"不支持的风速模式: {fan_mode}。支持的模式: {', '.join(available_modes)}") if not target_mode else
                await self._set_fan_mode(response, state, name, target_mode))

    async def _set_fan_mode(self, response, state, name, target_mode):
        try:
            await self.hass.services.async_call("climate", "set_fan_mode", 
                {"entity_id": state.entity_id, "fan_mode": target_mode})
            return self._set_speech_response(response, f"已将{name}的风速设置为{target_mode}")
        except Exception as e:
            return (self._set_speech_response(response, f"已开启{name}并设置风速为{target_mode}") 
                    if "设备在当前状态下无法执行此操作" in str(e) and 
                       not await self.ensure_entity_on(state.entity_id) and
                       not await self.hass.services.async_call("climate", "set_fan_mode", 
                           {"entity_id": state.entity_id, "fan_mode": target_mode}) else
                    self._set_error_response(response, "operation_failed", f"设置风速失败: {str(e)}"))

class ClimateSetTemperatureIntent(ClimateBaseIntent):
    intent_type = INTENT_CLIMATE_SET_TEMP
    slot_schema = {vol.Required("name"): str, vol.Required("temperature"): int}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        name = self.get_slot_value(slots.get("name"))
        temperature = self.get_slot_value(slots.get("temperature"))
        
        try:
            temperature = int(temperature) if temperature is not None else None
        except (TypeError, ValueError):
            response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
            return self._set_error_response(response, "invalid_temperature", "温度必须是一个有效的数字")
                    
        if not name or temperature is None:
            response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
            return self._set_error_response(response, "invalid_slots", "缺少必要的参数")

        state = self.find_climate_entity(name)
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        
        if not state:
            return self._set_error_response(response, "not_found", f"找不到名为 {name} 的空调")

        await self.ensure_entity_on(state.entity_id)
        
        min_temp = float(state.attributes.get('min_temp', 16))
        max_temp = float(state.attributes.get('max_temp', 30))
        
        if temperature < min_temp or temperature > max_temp:
            return self._set_error_response(response, "invalid_temperature", 
                f"温度必须在{min_temp}度到{max_temp}度之间")
            
        current_temp = state.attributes.get('current_temperature')
        if current_temp is not None:
            current_temp = float(current_temp)
            if current_temp > temperature:
                await self.hass.services.async_call("climate", "set_hvac_mode", 
                    {"entity_id": state.entity_id, "hvac_mode": "cool"})
            elif current_temp < temperature:
                await self.hass.services.async_call("climate", "set_hvac_mode", 
                    {"entity_id": state.entity_id, "hvac_mode": "heat"})
        
        try:
            await self.hass.services.async_call("climate", "set_temperature", 
                {"entity_id": state.entity_id, "temperature": temperature})
            return self._set_speech_response(response, f"已将{name}温度设置为{temperature}度")
        except Exception as e:
            LOGGER.error("设置温度失败: %s", str(e))
            return self._set_error_response(response, "operation_failed", f"设置温度失败: {str(e)}")

class ClimateSetHumidityIntent(ClimateBaseIntent):
    intent_type = "ClimateSetHumidity"
    slot_schema = {vol.Required("name"): str, vol.Required("humidity"): int}

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        name = self.get_slot_value(slots.get("name"))
        humidity = self.get_slot_value(slots.get("humidity"))
        
        try:
            humidity = int(humidity) if humidity is not None else None
        except (TypeError, ValueError):
            response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
            return self._set_error_response(response, "invalid_humidity", "湿度必须是一个有效的数字")
        
        if not name or humidity is None:
            response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
            return self._set_error_response(response, "invalid_slots", "缺少必要的参数")

        state = self.find_climate_entity(name)
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        
        if not state:
            return self._set_error_response(response, "not_found", f"未找到名为 {name} 的空调")

        await self.ensure_entity_on(state.entity_id)
        
        if humidity < 10 or humidity > 100:
            return self._set_error_response(response, "invalid_humidity", 
                "湿度必须在10%到100%之间")
        
        try:
            await self.hass.services.async_call("climate", "set_humidity", 
                {"entity_id": state.entity_id, "humidity": humidity})
            return self._set_speech_response(response, f"已将{name}湿度设置为{humidity}%")
        except Exception as e:
            LOGGER.error("设置湿度失败: %s", str(e))
            return self._set_error_response(response, "operation_failed", f"设置湿度失败: {str(e)}")


class ClimateSetSwingModeIntent(ClimateBaseIntent):
    intent_type = "ClimateSetSwingMode"
    slot_schema = {vol.Required("name"): str, vol.Required("swing_mode"): str}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        name, swing_mode = self.get_slot_value(slots.get("name")), self.get_slot_value(slots.get("swing_mode"))
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        
        if not name or not swing_mode:
            return self._set_error_response(response, "invalid_slots", "缺少必要的参数")
            
        state = self.find_climate_entity(name)
        if not state:
            return self._set_error_response(response, "not_found", f"找不到名为 {name} 的空调")
            
        return await self._handle_swing_mode_setting(response, state, name, swing_mode)

    async def _handle_swing_mode_setting(self, response, state, name, swing_mode) -> intent.IntentResponse:
        available_modes = state.attributes.get("swing_modes", [])
        if not available_modes:
            return self._set_error_response(response, "not_supported", f"{name}不支持摆动模式设置")

        target_mode = None
        normalized_mode = swing_mode.lower()
        
        mode_mapping = {
            "off": ["关闭", "停止", "关", "off", "stop"],
            "on": ["开启", "打开", "开", "on", "start"],
            "vertical": ["上下", "垂直", "vertical"],
            "horizontal": ["左右", "水平", "horizontal"],
            "both": ["全开", "全部", "both"],
            "auto": ["自动", "智能", "auto", "automatic"]
        }
        
        for mode in available_modes:
            mode_lower = mode.lower()
            for key, values in mode_mapping.items():
                if mode_lower == key or any(val in normalized_mode for val in values):
                    target_mode = mode
                    break
            if target_mode:
                break
                
        if not target_mode:
            modes_str = "、".join(available_modes)
            return self._set_error_response(response, "invalid_mode", 
                f"不支持的摆动模式。{name}支持的模式有：{modes_str}")
                
        try:
            await self.hass.services.async_call(
                "climate", "set_swing_mode",
                {"entity_id": state.entity_id, "swing_mode": target_mode}
            )
            return self._set_speech_response(response, f"已将{name}的摆动模式设置为{target_mode}")
        except Exception as e:
            return self._set_error_response(response, "operation_failed", f"设置摆动模式失败：{str(e)}")

class CoverControlAllIntent(intent.IntentHandler):
    intent_type = "CoverControlAll"
    slot_schema = {}

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        
        covers = [state for state in self.hass.states.async_all() 
                 if state.entity_id.startswith("cover.")]
        
        if not covers:
            return self._set_error_response(response, "not_found", "未找到任何窗帘设备")
        
        try:
            for cover in covers:
                await self.hass.services.async_call(
                    "cover", "close_cover",
                    {"entity_id": cover.entity_id}
                )
            return self._set_speech_response(response, f"已关闭所有{len(covers)}个窗帘")
        except Exception as e:
            return self._set_error_response(response, "operation_failed", f"操作失败: {str(e)}")

    def _set_speech_response(self, response: intent.IntentResponse, speech: str) -> intent.IntentResponse:
        response.response_type = intent.IntentResponseType.ACTION_DONE
        response.speech = {"plain": {"speech": speech, "extra_data": None}}
        return response

    def _set_error_response(self, response: intent.IntentResponse, error: str, message: str) -> intent.IntentResponse:
        response.response_type = intent.IntentResponseType.ERROR
        response.error_code = error
        response.speech = {"plain": {"speech": message, "extra_data": None}}
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

    climate_modes = {"cool": "制冷模式", "heat": "制热模式", "auto": "自动模式", "dry": "除湿模式", "fan_only": "送风模式", "off": "关闭"}
    fan_modes = {"on_high": "高速风", "on_low": "低速风", "auto_high": "自动高速", "auto_low": "自动低速", "off": "关闭风速"}
    media_actions = {"turn_on": "打开", "turn_off": "关闭", "volume_up": "调高音量", "volume_down": "调低音量", "volume_mute": "静音", "media_play": "播放", "media_pause": "暂停", "media_stop": "停止", "media_next_track": "下一曲", "media_previous_track": "上一曲", "select_source": "切换输入源", "shuffle_set": "随机播放", "repeat_set": "循环播放", "play_media": "播放媒体"}
    cover_actions = {"open_cover": "打开", "close_cover": "关闭", "stop_cover": "停止", "toggle": "切换", "set_cover_position": "设置位置", "set_cover_tilt_position": "设置角度"}
    vacuum_actions = {"start": "启动", "pause": "暂停", "stop": "停止", "return_to_base": "返回充电", "clean_spot": "定点清扫", "locate": "定位", "set_fan_speed": "设置吸力"}
    fan_directions = {"forward": "正向", "reverse": "反向"}
    automation_actions = {"turn_on": "启用", "turn_off": "禁用", "trigger": "触发", "toggle": "切换"}
    boolean_actions = {"turn_on": "打开", "turn_off": "关闭", "toggle": "切换"}
    timer_actions = {"start": "启动", "pause": "暂停", "cancel": "取消", "finish": "结束", "reload": "重新加载"}
    select_actions = {"select_next": "下一个", "select_previous": "上一个", "select_first": "第一个", "select_last": "最后一个", "select_option": "选择"}

    async def call_service(self, domain: str, service: str, data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            entity_id = data.get("entity_id")
            entity = self.hass.states.get(entity_id)
            friendly_name = entity.attributes.get("friendly_name") if entity else "设备"
            await self.hass.services.async_call(domain, service, {**data, "entity_id": entity_id} if entity_id else data, blocking=True)
            target_temp = data.get('temperature')
            current_temp = entity.attributes.get('current_temperature') if entity and domain == "climate" and service == "set_temperature" else None
            _ = await self.hass.services.async_call(domain, "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "cool" if current_temp > target_temp else "heat"}, blocking=True) if current_temp is not None and target_temp is not None else None
            return ({"success": True, "message": f"已设置 {friendly_name} {'制冷' if current_temp > target_temp else '制热'}模式，温度{target_temp}度"} if domain == "climate" and service == "set_temperature" and current_temp is not None and target_temp is not None else
                    {"success": True, "message": f"已设置 {friendly_name} 温度{target_temp}度"} if domain == "climate" and service == "set_temperature" and target_temp is not None else
                    {"success": True, "message": f"已执行 {friendly_name} {self.climate_modes.get(data.get('hvac_mode'), data.get('hvac_mode'))}"} if domain == "climate" and service == "set_hvac_mode" else
                    {"success": True, "message": f"已执行 {friendly_name} {self.fan_modes.get(data.get('fan_mode'), data.get('fan_mode'))}"} if domain == "climate" and service == "set_fan_mode" else
                    {"success": True, "message": f"已执行 {friendly_name} 湿度{data.get('humidity')}%"} if domain == "climate" and service == "set_humidity" else
                    {"success": True, "message": f"已执行 {friendly_name} 亮度{int(data['brightness'] * 100 / 255)}%"} if domain == "light" and service == "turn_on" and "brightness" in data else
                    {"success": True, "message": f"已设置 {friendly_name} {'颜色' if 'rgb_color' in data else '色温'}"} if domain == "light" and service == "turn_on" and ("rgb_color" in data or "color_temp" in data) else
                    {"success": True, "message": f"已{'打开' if service == 'turn_on' else '关闭'} {friendly_name}"} if domain == "light" and service in ["turn_on", "turn_off"] else
                    {"success": True, "message": f"已{self.media_actions.get(service, service)} {friendly_name}"} if domain == "media_player" else
                    {"success": True, "message": f"已设置 {friendly_name} {'位置到' + str(data['position']) + '%' if 'position' in data else '角度到' + str(data['tilt_position']) + '%'}"} if domain == "cover" and ("position" in data or "tilt_position" in data) else
                    {"success": True, "message": f"已{self.cover_actions.get(service, service)} {friendly_name}"} if domain == "cover" else
                    {"success": True, "message": f"已{'打开' if service == 'turn_on' else '关闭'} {friendly_name}"} if domain == "switch" and service in ["turn_on", "turn_off"] else
                    {"success": True, "message": f"已设置 {friendly_name} {'风速' + str(data['percentage']) + '%' if 'percentage' in data else data['preset_mode'] + '模式'}"} if domain == "fan" and service == "turn_on" and ("percentage" in data or "preset_mode" in data) else
                    {"success": True, "message": f"已{'打开' if service == 'turn_on' else '关闭'} {friendly_name}"} if domain == "fan" and service in ["turn_on", "turn_off"] else
                    {"success": True, "message": f"已{'开启' if data.get('oscillating') else '关闭'} {friendly_name} 摆风"} if domain == "fan" and service == "oscillate" else
                    {"success": True, "message": f"已设置 {friendly_name} {self.fan_directions.get(data.get('direction'), data.get('direction'))}旋转"} if domain == "fan" and service == "set_direction" else
                    {"success": True, "message": f"已启动场景 {friendly_name}"} if domain == "scene" and service == "turn_on" else
                    {"success": True, "message": f"已执行脚本 {friendly_name}"} if domain == "script" and service in ["turn_on", "start"] else
                    {"success": True, "message": f"已{self.automation_actions.get(service, service)}自动化 {friendly_name}"} if domain == "automation" else
                    {"success": True, "message": f"已{self.boolean_actions.get(service, service)} {friendly_name}"} if domain == "input_boolean" else
                    {"success": True, "message": f"已{self.timer_actions.get(service, service)}计时器 {friendly_name}"} if domain == "timer" else
                    {"success": True, "message": f"已设置 {friendly_name} 吸力为{data['fan_speed']}"} if domain == "vacuum" and service == "set_fan_speed" and "fan_speed" in data else
                    {"success": True, "message": f"已{self.vacuum_actions.get(service, service)} {friendly_name}"} if domain == "vacuum" else
                    {"success": True, "message": f"已按下 {friendly_name}"} if domain == "button" and service == "press" else
                    {"success": True, "message": f"已设置 {friendly_name} 为 {data['value']}"} if domain == "number" and service == "set_value" else
                    {"success": True, "message": f"已切换到{friendly_name}{self.select_actions.get(service, '选项')}"} if domain == "select" else
                    {"success": True, "message": f"已执行 {friendly_name} {service}"})
        except Exception as e:
            return {"success": False, "message": str(e)}

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

    async def handle_timer_intent(self, action: str, name: str, area: str, data: Dict[str, Any]) -> Dict[str, Any]:
        duration = data.get("duration", "")
        timer_id = data.get('entity_id')
        
        minutes = (
            int(''.join(filter(str.isdigit, duration))) if "minutes" in duration else
            int(minutes_match.group(1)) if (minutes_match := re.search(r'(\d+)\s*分钟', duration)) else
            None
        )
        
        return {
            "action": f"timer.{action}",
            "data": {"duration": f"00:{minutes:02d}:00"} if action == "start" and minutes is not None else {},
            "target": {"entity_id": timer_id}
        }

def get_intent_handler(hass: HomeAssistant) -> IntentHandler:
    return IntentHandler(hass)