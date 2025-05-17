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
from custom_components.zhipuai.api.musicapi import search_song, async_search_song, async_get_playlist_songs
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
import json
import random
import urllib.parse

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
INTENT_MASS_PLAY_MEDIA = "MassPlayMediaAssist"
INTENT_IMAGE_GEN = "ZhipuAIImageGen"

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
    intent.async_register(hass, MassPlayMediaAssist(hass))
    intent.async_register(hass, ZhipuAIImageGenIntent(hass))
    intent.async_register(hass, HassLightSetAllIntent(hass))

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
    slot_schema = {vol.Required("query"): str, vol.Optional("time_query"): str, vol.Optional("search_engine"): str}

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
        
        query = self.get_slot_value(slots.get("query", ""))
        time_query = self.get_slot_value(slots.get("time_query"))
        search_engine = self.get_slot_value(slots.get("search_engine"))
        
        LOGGER.info("Web search info - 原始插槽:%s", slots)
        
        simplified_engine_mapping = {"jc": "基础版", "gj": "高阶版", "kk": "夸克", "sg": "搜狗"}
        search_engine = simplified_engine_mapping.get(search_engine, search_engine)
        
        search_engine_keywords = {
            "基础版": ["基础版", "jc"], "高阶版": ["高阶版", "gj"],
            "夸克": ["夸克搜索", "夸克", "kk"], "搜狗": ["搜狗搜索", "搜狗", "sg"]
        }
        
        for engine, keywords in search_engine_keywords.items():
            for keyword in keywords:
                if query and not search_engine and keyword in query:
                    query = query.replace(keyword, "").strip()
                    search_engine = engine
        
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        
        if not query:
            return self._set_error_response(response, ERROR_NO_QUERY, "未提供搜索内容")
        
        return await self._handle_web_search(
            intent_obj.hass, intent_obj, query, time_query, search_engine
        )

    async def _handle_web_search(self, hass: HomeAssistant, intent_obj: intent.Intent, query: str, time_query: str = None, search_engine: str = None) -> intent.IntentResponse:
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        
        try:
            service_data = {"query": query, "stream": False}
            
            time_query_value = None
            if isinstance(time_query, dict) and 'value' in time_query:
                time_query_value = time_query['value']
            elif hasattr(time_query, 'value'):
                time_query_value = time_query.value
            else:
                time_query_value = time_query
            
            now = datetime.now()
            
            if time_query_value:
                LOGGER.debug("处理时间查询: %s", time_query_value)
                
                if time_query_value in ["昨天", "昨日", "yesterday"]:
                    target_date = now - timedelta(days=1)
                elif time_query_value in ["前天"]:
                    target_date = now - timedelta(days=2)
                elif time_query_value in ["大前天"]:
                    target_date = now - timedelta(days=3)
                elif time_query_value in ["明天", "明日", "tomorrow"]:
                    target_date = now + timedelta(days=1)
                elif time_query_value in ["后天"]:
                    target_date = now + timedelta(days=2)
                elif time_query_value in ["大后天"]:
                    target_date = now + timedelta(days=3)
                elif time_query_value in ["今天", "今日", "today"]:
                    target_date = now
                elif time_query_value in ["本周", "这周", "this week"]:
                    days_since_monday = now.weekday()
                    target_date = now - timedelta(days=days_since_monday)
                elif time_query_value in ["上周", "上个星期", "last week"]:
                    days_since_monday = now.weekday()
                    target_date = now - timedelta(days=days_since_monday + 7)
                elif time_query_value in ["下周", "下个星期", "next week"]:
                    days_since_monday = now.weekday()
                    target_date = now + timedelta(days=7 - days_since_monday)
                elif time_query_value in ["本月", "这个月", "this month"]:
                    target_date = now.replace(day=1)
                elif time_query_value in ["上个月", "上月", "last month"]:
                    if now.month == 1:
                        target_date = now.replace(year=now.year-1, month=12, day=1)
                    else:
                        target_date = now.replace(month=now.month-1, day=1)
                elif time_query_value in ["下个月", "下月", "next month"]:
                    if now.month == 12:
                        target_date = now.replace(year=now.year+1, month=1, day=1)
                    else:
                        target_date = now.replace(month=now.month+1, day=1)
                elif time_query_value in ["今年", "本年", "this year"]:
                    target_date = now.replace(month=1, day=1)
                elif time_query_value in ["去年", "上一年", "last year"]:
                    target_date = now.replace(year=now.year-1, month=1, day=1)
                elif time_query_value in ["明年", "下一年", "next year"]:
                    target_date = now.replace(year=now.year+1, month=1, day=1)
                else:
                    target_date = now
                    
                service_data["time_query"] = target_date.strftime('%Y-%m-%d')
                LOGGER.debug("时间查询转换为: %s", service_data["time_query"])
            else:
                service_data["time_query"] = now.strftime('%Y-%m-%d')
            
            if search_engine:
                service_data["search_engine"] = search_engine
            
            result = await hass.services.async_call(DOMAIN, "web_search", service_data, blocking=True, return_response=True)
            
            if result and isinstance(result, dict) and result.get("success", False):
                return self._set_speech_response(response, result.get("message", ""))
            elif result and isinstance(result, dict):
                return self._set_error_response(response, ERROR_SERVICE_CALL, result.get("message", "搜索服务调用失败"))
            else:
                return self._set_error_response(response, ERROR_NO_RESPONSE, "未能获取到有效的搜索结果")
            
        except Exception as e:
            LOGGER.exception("搜索服务调用出错: %s", str(e))
            return self._set_error_response(response, ERROR_SERVICE_CALL, f"搜索服务调用出错：{str(e)}")

    def _set_error_response(self, response, code, message) -> intent.IntentResponse:
        response.async_set_error(code=code, message=message)
        return response

    def _set_speech_response(self, response, message) -> intent.IntentResponse:
        response.async_set_speech(len(message.encode('utf-8')) > 24 * 1024 and message[:24 * 1024].rsplit(' ', 1)[0] + "..." or message)
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

            notify_service = "persistent_notification"  
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if "notify_service" in entry.options:
                    notify_service = entry.options.get("notify_service")
                    break

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
            
            if notify_service != "persistent_notification":
                await self.hass.services.async_call(
                    "notify", 
                    notify_service, 
                    {
                        "title": title,
                        "message": f"{ai_message}"
                    },
                    blocking=True
                )
            else:
                await self.hass.services.async_call(
                    "persistent_notification", 
                    "create", 
                    {
                        "title": title,
                        "message": f"{ai_message}\n\n\n\n创建时间：{current_time}"
                    },
                    blocking=True
                )
            
            response.async_set_speech(f"已创建通知: {message}")
            return response

        except Exception as err:
            LOGGER.exception("发送通知失败: %s", str(err))
            response.async_set_error("notification_error", f"发送通知失败: {str(err)}")
            return response

    def get_slot_value(self, slot_data):
        if not slot_data:
            return None
        
        if isinstance(slot_data, dict) and 'value' in slot_data:
            return slot_data['value']
        
        if hasattr(slot_data, 'value'):
            return getattr(slot_data, 'value')
        
        return slot_data


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
    slot_schema = {vol.Required("action"): str}
    def __init__(self, hass: HomeAssistant) -> None: self.hass = hass
    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        try:
            action = self.async_validate_slots(intent_obj.slots)["action"]["value"]
            is_close = any(x in action for x in ["关", "close"])
            service = "close_cover" if is_close else "open_cover"
            action_text = "关闭" if is_close else "打开"
            covers = [state.entity_id for state in self.hass.states.async_all() 
                     if state.entity_id.startswith("cover.") and 
                     not any(x in state.entity_id.lower() for x in ["garage", "车库"])]
            if not covers: return self._set_error_response(response, "not_found", "未找到任何窗帘设备")
            success_count, failed_entities = 0, []
            for entity_id in covers:
                try:
                    await self.hass.services.async_call("cover", service, {"entity_id": entity_id}, blocking=True)
                    success_count += 1
                except Exception:
                    try:
                        tilt_service = "close_cover_tilt" if is_close else "open_cover_tilt"
                        await self.hass.services.async_call("cover", tilt_service, {"entity_id": entity_id}, blocking=True)
                        success_count += 1
                    except Exception: failed_entities.append(entity_id)
            if success_count == 0: return self._set_error_response(response, "operation_failed", "所有设备操作都失败了")
            message = f"已{action_text} {success_count} 个窗帘"
            if failed_entities: message += f"，但有 {len(failed_entities)} 个设备失败"
            return self._set_speech_response(response, message)
        except vol.Invalid as e: return self._set_error_response(response, "invalid_format", f"命令格式错误: {str(e)}")
        except Exception as e: return self._set_error_response(response, "operation_failed", f"操作失败: {str(e)}")
    def _set_speech_response(self, response: intent.IntentResponse, speech: str) -> intent.IntentResponse:
        response.response_type = intent.IntentResponseType.ACTION_DONE
        response.speech = {"plain": {"speech": speech, "extra_data": None}}
        return response
    def _set_error_response(self, response: intent.IntentResponse, error: str, message: str) -> intent.IntentResponse:
        response.response_type = intent.IntentResponseType.ERROR
        response.error_code = error
        response.speech = {"plain": {"speech": message, "extra_data": None}}
        return response

class HassLightSetAllIntent(intent.IntentHandler):
    intent_type = "HassLightSetAllIntent"
    slot_schema = {
        vol.Required("name"): str,
        vol.Optional("domain"): str,
        vol.Optional("action"): str,
        vol.Optional("color"): str,
        vol.Optional("brightness"): str,
        vol.Optional("color_temp"): str
    }

    def __init__(self, hass: HomeAssistant):
        super().__init__()
        self.hass = hass
        self.color_map = {
            "红": {"name": "red", "rgb": [255, 0, 0]},
            "绿": {"name": "green", "rgb": [0, 255, 0]},
            "蓝": {"name": "blue", "rgb": [0, 0, 255]},
            "黄": {"name": "yellow", "rgb": [255, 255, 0]},
            "白": {"name": "white", "rgb": [255, 255, 255]},
            "黑": {"name": "black", "rgb": [0, 0, 0]},
            "紫": {"name": "purple", "rgb": [128, 0, 128]},
            "橙": {"name": "orange", "rgb": [255, 165, 0]},
            "粉": {"name": "pink", "rgb": [255, 192, 203]},
            "棕": {"name": "brown", "rgb": [165, 42, 42]},
            "灰": {"name": "gray", "rgb": [128, 128, 128]}
        }
        self.color_temp_map = {
            "暖": 2600, "暖白": 2600, "暖黄": 2600, "暖光": 2600,
            "中": 3800, "中性": 3800, "自然": 3800, "自然光": 3800,
            "冷": 6500, "冷白": 6500, "白光": 6500, "日光": 6500
        }

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        name = self.get_slot_value(slots.get("name"))
        domain = self.get_slot_value(slots.get("domain")) or "light"
        action = self.get_slot_value(slots.get("action"))
        color = self.get_slot_value(slots.get("color"))
        brightness = self.get_slot_value(slots.get("brightness"))
        color_temp = self.get_slot_value(slots.get("color_temp"))

        LOGGER.info("Light intent info - 原始插槽: %s", {
            "name": name, "domain": domain, "action": action,
            "color": color, "brightness": brightness, "color_temp": color_temp
        })

        entity_id = next(
            (state.entity_id for state in self.hass.states.async_all(domain)
             if name and name.lower() in state.name.lower()),
            None
        )

        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        
        if not entity_id:
            response.async_set_error("no_valid_targets", f"未找到名为{name}的{domain}实体")
            return response

        if action and any(term in action.lower() for term in ["关", "关闭", "off", "turn off"]):
            try:
                await self.hass.services.async_call(
                    domain, "turn_off",
                    {"entity_id": entity_id},
                    blocking=True,
                    context=intent_obj.context
                )
                response.async_set_speech(f"已关闭{name}")
                return response
            except Exception as err:
                response.async_set_error("failed_to_handle", f"关闭失败: {err}")
                return response

        if domain != "light":
            try:
                await self.hass.services.async_call(
                    domain, "turn_on",
                    {"entity_id": entity_id},
                    blocking=True,
                    context=intent_obj.context
                )
                response.async_set_speech(f"已打开{name}")
                return response
            except Exception as err:
                response.async_set_error("failed_to_handle", f"打开失败: {err}")
                return response

        service_data = {"entity_id": entity_id}
        message_parts = []
        has_settings = False

        if color:
            for cn_color, color_info in self.color_map.items():
                if cn_color in color:
                    service_data["rgb_color"] = color_info["rgb"]
                    message_parts.append(f"颜色设为{color}")
                    has_settings = True
                    break

        if brightness is not None:
            try:
                value = None
                if isinstance(brightness, str):
                    if "%" in brightness:
                        value = int(brightness.replace("%", "").strip())
                    else:
                        match = re.search(r"(\d+)", brightness)
                        if match:
                            value = int(match.group(1))
                elif isinstance(brightness, (int, float)):
                    value = int(brightness)

                if value is not None:
                    service_data["brightness"] = int(max(0, min(100, value)) * 255 / 100)
                    message_parts.append(f"亮度设为{value}%")
                    has_settings = True
            except (ValueError, AttributeError, TypeError):
                pass

        if color_temp:
            for keyword, value in self.color_temp_map.items():
                if keyword in color_temp:
                    service_data["color_temp_kelvin"] = value
                    message_parts.append(f"色温设为{color_temp}")
                    has_settings = True
                    break
            else:
                self._try_parse_color_temp(color_temp, service_data, message_parts)
                has_settings = True

        if not has_settings and not action:
            message_parts.append("已打开")

        try:
            if has_settings:
                await self.hass.services.async_call(
                    "light", "turn_on",
                    {"entity_id": entity_id},
                    blocking=True,
                    context=intent_obj.context
                )


            if service_data:
                await self.hass.services.async_call(
                    "light", "turn_on",
                    service_data,
                    blocking=True,
                    context=intent_obj.context
                )

            response.async_set_speech(f"{name}的灯" + "，".join(message_parts))
            return response
        except Exception as err:
            response.async_set_error("failed_to_handle", f"设置失败: {err}")
            return response

    def _try_parse_color_temp(self, color_temp, service_data, message_parts):
        try:
            match = re.search(r"(\d+)", color_temp)
            if match:
                value = max(2000, min(6500, int(match.group(1))))
                service_data["color_temp_kelvin"] = value
                message_parts.append(f"色温设为{value}K")
        except (ValueError, AttributeError):
            pass

    def get_slot_value(self, slot_data):
        if not slot_data:
            return None
        if isinstance(slot_data, dict):
            return slot_data.get('value')
        if hasattr(slot_data, 'value'):
            return getattr(slot_data, 'value')
        return str(slot_data)

class MassPlayMediaAssist(intent.IntentHandler):
    intent_type = "MassPlayMediaAssist"
    slot_schema = {
        vol.Required("query"): str, 
        vol.Optional("area"): str, 
        vol.Optional("name"): str,
        vol.Optional("action"): str 
    }
    
    def __init__(self, hass: HomeAssistant): 
        super().__init__()
        self.hass = hass
        self._area_reg = area_registry.async_get(hass)
        self._entity_reg = entity_registry.async_get(hass)
        self._media_actions = {
            "play": "media_play",
            "pause": "media_pause",
            "stop": "media_stop",
            "next": "media_next_track",
            "previous": "media_previous_track",
            "prev": "media_previous_track",
            "shuffle": "shuffle_set", 
            "repeat": "repeat_set"    
        }

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        response = intent.IntentResponse(intent=intent_obj, language="zh-cn")
        
        try:
            slots = self.async_validate_slots(intent_obj.slots)
            query = self._get_slot_value(slots.get("query", ""))
            area = self._get_slot_value(slots.get("area"))
            name = self._get_slot_value(slots.get("name"))
            action = self._get_slot_value(slots.get("action"))
            
            LOGGER.info("MassPlayMedia intent info - 原始插槽: %s", {"query": query, "area": area, "name": name, "action": action})
            
            if action and action in self._media_actions:
                return await self._handle_media_control(response, name, area, action)
                
            control_action = self._extract_control_action(query)
            if control_action:
                return await self._handle_media_control(response, name, area, control_action)
            
            service_request = hasattr(intent_obj, 'service_request') and intent_obj.service_request or await self._build_service_request(query, area, name)
            return await self._handle_service_call(service_request, response) if "error" not in service_request else response.async_set_error("invalid_request", service_request["error"])
            
        except Exception as err: 
            LOGGER.exception("处理失败: %s", str(err))
            response.async_set_error("play_error", f"播放失败: {str(err)}")
            return response

    def _extract_control_action(self, query: str) -> Optional[str]:
        query_lower = query.lower()
        
        if any(word in query_lower for word in ["播放"]):
            return "play"
        elif any(word in query_lower for word in ["暂停"]):
            return "pause"
        elif any(word in query_lower for word in ["停止", "结束"]):
            return "stop"
        elif any(word in query_lower for word in ["下一首", "下一曲"]):
            return "next"
        elif any(word in query_lower for word in ["上一首", "上一曲"]):
            return "prev"
        elif any(word in query_lower for word in ["随机播放"]):
            return "shuffle"
        elif any(word in query_lower for word in ["顺序播放", "列表循环", "循环播放"]):
            return "repeat"
        
        return None

    async def _handle_media_control(self, response: intent.IntentResponse, name: str, area: str, action: str) -> intent.IntentResponse:
        target = self._build_target(name, area)
        if "error" in target: return response.async_set_error("invalid_target", target["error"])
        
        service = self._media_actions.get(action)
        if not service: return response.async_set_error("invalid_action", f"不支持的操作: {action}")
        
        try:
            entity_id = target.get("entity_id")
            if isinstance(entity_id, list) and entity_id: entity_id = entity_id[0]
            
            if entity_id:
                if not hasattr(self.hass, '_last_media_player'): self.hass._last_media_player = {}
                self.hass._last_media_player = {'entity_id': entity_id}
                
            tool_params = {"domain": "media_player", "service": service, "service_data": {}}
            
            if entity_id:
                tool_params["target"] = {"entity_id": [entity_id] if isinstance(entity_id, str) else entity_id}
            elif area_id := target.get("area_id"):
                tool_params["target"] = {"area_id": [area_id] if isinstance(area_id, str) else area_id}
            
            if action == "shuffle": tool_params["service_data"]["shuffle"] = True
            elif action == "repeat": tool_params["service_data"]["repeat"] = "all"
            
            LOGGER.info("媒体控制工具调用: %s", json.dumps(tool_params, ensure_ascii=False))
            
            await self.hass.services.async_call(
                tool_params["domain"], tool_params["service"],
                tool_params.get("service_data", {}), target=tool_params.get("target"),
                blocking=True
            )
            
            action_text = {"media_play": "播放", "media_pause": "暂停", "media_stop": "停止",
                         "media_next_track": "切换到下一曲", "media_previous_track": "切换到上一曲",
                         "shuffle_set": "设置随机播放", "repeat_set": "设置列表循环"}.get(service, service)
            
            target_desc = self._get_target_desc(target)
            if entity_id:
                state = self.hass.states.get(entity_id)
                if state:
                    state_info = ""
                    if state.state != "unknown":
                        state_info = f"，当前状态：{state.state}"
                    response.async_set_speech(f"已{action_text}{target_desc}{state_info}。我会记住这个播放器，下次可以直接控制。")
                    return response
            
            response.async_set_speech(f"已{action_text}{target_desc}")
            return response
            
        except Exception as err:
            LOGGER.error("媒体控制失败: %s", str(err))
            return response.async_set_error("control_error", f"控制操作失败: {str(err)}")

    def _get_target_desc(self, target: dict) -> str:
        """获取目标设备描述"""
        entity_id = "entity_id" in target and target["entity_id"]
        entity_id = entity_id and isinstance(entity_id, list) and entity_id and entity_id[0] or entity_id
        area_id = "area_id" in target and target["area_id"]
        area_id = area_id and isinstance(area_id, list) and area_id and area_id[0] or area_id
        
        if entity_id and self.hass.states.get(entity_id):
            return f" {self.hass.states.get(entity_id).attributes.get('friendly_name', entity_id)}"
        elif area_id and self._area_reg.async_get_area(area_id):
            return f" {self._area_reg.async_get_area(area_id).name}区域"
        return ""

    async def _build_service_request(self, query: str, area: str = None, name: str = None) -> dict:
        clean_query = self._clean_query(query)
        shuffle = "随机" in query.lower() or "shuffle" in query.lower()
        
        playlist_match = re.search(r'播放列表\s*(\d+)', clean_query)
        if playlist_match:
            playlist_id = playlist_match.group(1)
            return await self._build_playlist_request(playlist_id, name, area, shuffle)
        
        try:
            result = await async_search_song(clean_query)
            LOGGER.info("网易云音乐搜索结果: %s", result)
            
            if not result.get("success", False):
                artist_song_match = re.search(r'([^\s]+)(?:\s+)([^\s]+)', clean_query)
                artist_of_song_match = re.search(r'([^的]+)的(.+)', clean_query)
                
                artist = None
                song_name = None
                
                if artist_song_match:
                    artist = artist_song_match.group(1).strip()
                    song_name = artist_song_match.group(2).strip()
                elif artist_of_song_match:
                    artist = artist_of_song_match.group(1).strip()
                    song_name = artist_of_song_match.group(2).strip()
                
                if artist and song_name:
                    search_query = f"{artist} {song_name}"
                    result = await async_search_song(search_query)
                    LOGGER.info("网易云音乐搜索结果(歌手+歌名): %s", result)
            
            if result.get("success") and "url" in result:
                target = self._build_target(name, area)
                if "error" in target:
                    return target

                song_info = result.get("song_info", {})
                
                song_title = song_info.get("name", "未知歌曲")
                song_artist = song_info.get("artist", "未知歌手")
                song_album = song_info.get("album", "未知专辑")
                song_cover = song_info.get("cover", "")
                song_duration = song_info.get("duration", 0)  
                
                encoded_url = f"{result['url']}#INFO#%{urllib.parse.quote(song_title)}#%{urllib.parse.quote(song_artist)}#%{urllib.parse.quote(song_album)}#%{urllib.parse.quote(song_cover)}#{song_duration}#/{song_title}-{song_artist}"
                
                LOGGER.info(f"歌曲元数据: 标题={song_title}, 歌手={song_artist}, 专辑={song_album}, 封面={song_cover}, 持续时间={song_duration}秒")
                
                service_request = {
                    "action": "media_player.play_media",
                    "target": target,
                    "data": {
                        "media_content_id": encoded_url,
                        "media_content_type": "music"
                    }
                }

                if shuffle:
                    service_request["shuffle"] = True

                return service_request

            return {"error": f"未找到音乐: {clean_query}"}
        except Exception as e:
            LOGGER.exception("使用网易云API搜索失败: %s", str(e))
            return {"error": f"搜索音乐失败: {str(e)}"}

    async def _build_playlist_request(self, playlist_id: str, name: str = None, area: str = None, shuffle: bool = False) -> dict:

        try:
            playlist_result = await async_get_playlist_songs(playlist_id)
            
            if not playlist_result.get("success", False):
                return {"error": playlist_result.get("message", "获取播放列表失败")}
                
            songs = playlist_result.get("songs", [])
            if not songs:
                return {"error": "播放列表中没有歌曲"}
                
            if shuffle:
                random.shuffle(songs)
                
            first_song = songs[0]
            song_result = await async_search_song(f"{first_song['name']} {first_song['artist']}")
            
            if not song_result.get("success", False):
                return {"error": "无法播放播放列表中的歌曲"}
                
            target = self._build_target(name, area)
            if "error" in target:
                return target
                
            if not hasattr(self.hass, '_playlist_info'):
                self.hass._playlist_info = {}
                
            self.hass._playlist_info = {
                'playlist_id': playlist_id,
                'playlist_name': playlist_result.get("playlist_name", "未知播放列表"),
                'songs': songs,
                'current_index': 0,
                'shuffle': shuffle,
                'target': target
            }
            
            song_info = song_result.get("song_info", {})
            song_title = song_info.get("name", first_song['name'])
            song_artist = song_info.get("artist", first_song['artist'])
            song_album = song_info.get("album", first_song['album'])
            song_cover = song_info.get("cover", first_song['cover'])
            song_duration = song_info.get("duration", 0)  
            
            encoded_url = f"{song_result['url']}#INFO#%{urllib.parse.quote(song_title)}#%{urllib.parse.quote(song_artist)}#%{urllib.parse.quote(song_album)}#%{urllib.parse.quote(song_cover)}#{song_duration}#PLAYLIST#{playlist_id}"
            
            self._register_playlist_listener()
            
            return {
                "action": "media_player.play_media",
                "target": target,
                "data": {
                    "media_content_id": encoded_url,
                    "media_content_type": "music"
                },
                "shuffle": shuffle,
                "playlist": True,
                "playlist_name": playlist_result.get("playlist_name", "未知播放列表")
            }
            
        except Exception as e:
            LOGGER.exception("处理播放列表请求失败: %s", str(e))
            return {"error": f"播放列表处理失败: {str(e)}"}
            
    def _register_playlist_listener(self):

        if hasattr(self.hass, '_playlist_listener') and self.hass._playlist_listener:
            self.hass._playlist_listener()
            
        self.hass._playlist_listener = self.hass.bus.async_listen('state_changed', self._handle_media_state_change)
        
    async def _handle_media_state_change(self, event):
        if not hasattr(self.hass, '_playlist_info') or not self.hass._playlist_info:
            return
            
        entity_id = event.data.get('entity_id')
        target = self.hass._playlist_info.get('target', {})
        target_entity_id = target.get('entity_id')
        
        if entity_id != target_entity_id:
            return
            
        new_state = event.data.get('new_state')
        if not new_state:
            return
            
        if new_state.state == 'idle' and self.hass._playlist_info:
            await self._play_next_song()
            
    async def _play_next_song(self):
        if not hasattr(self.hass, '_playlist_info') or not self.hass._playlist_info:
            return
            
        playlist_info = self.hass._playlist_info
        songs = playlist_info.get('songs', [])
        current_index = playlist_info.get('current_index', 0)
        
        next_index = current_index + 1
        if next_index >= len(songs):
            next_index = 0  
            
        if next_index == 0 and not playlist_info.get('shuffle', False):
            pass 
            
        self.hass._playlist_info['current_index'] = next_index
        
        next_song = songs[next_index]
        song_result = await async_search_song(f"{next_song['name']} {next_song['artist']}")
        
        if not song_result.get("success", False):
            return await self._play_next_song()
            
        song_info = song_result.get("song_info", {})
        song_title = song_info.get("name", next_song['name'])
        song_artist = song_info.get("artist", next_song['artist'])
        song_album = song_info.get("album", next_song['album'])
        song_cover = song_info.get("cover", next_song['cover'])
        song_duration = song_info.get("duration", 0)  
        
        encoded_url = f"{song_result['url']}#INFO#%{urllib.parse.quote(song_title)}#%{urllib.parse.quote(song_artist)}#%{urllib.parse.quote(song_album)}#%{urllib.parse.quote(song_cover)}#{song_duration}#PLAYLIST#{playlist_info['playlist_id']}"
        
        await self.hass.services.async_call(
            "media_player", "play_media",
            {
                "entity_id": playlist_info['target'].get('entity_id'),
                "media_content_id": encoded_url,
                "media_content_type": "music"
            },
            blocking=True
        )

    def _build_target(self, name: str = None, area: str = None) -> dict:
        target = {}
        if name and isinstance(name, str):
            target_entity = self._find_player_by_name(name)
            if target_entity:
                target = {"entity_id": target_entity}
        elif area and isinstance(area, str):
            area_id = self._find_area_by_name(area)
            if area_id:
                target = {"area_id": area_id}
                
        if not target:
            default_players = [state.entity_id for state in self.hass.states.async_all() 
                              if state.domain == "media_player"]
            if default_players:
                target = {"entity_id": default_players[0]}
            else:
                return {"error": "未找到可用的音乐播放器"}
                
        return target

    async def _handle_service_call(self, service_request: dict, response: intent.IntentResponse) -> intent.IntentResponse:
        try:
            action = service_request.get("action", "media_player.play_media")
            domain, service = action.split(".", 1) if "." in action else ("media_player", "play_media")
            data = service_request.get("data", {})
            target = service_request.get("target", {})
            
            target["entity_id"] = "entity_id" in target and isinstance(target["entity_id"], str) and [target["entity_id"]] or target.get("entity_id")
            target["area_id"] = "area_id" in target and isinstance(target["area_id"], str) and [target["area_id"]] or target.get("area_id")
            
            await self.hass.services.async_call(domain, service, data, target=target)
            service_request.get("shuffle", False) and target and await self.hass.services.async_call("media_player", "shuffle_set", {"shuffle": True}, target=target)
            
            response_text = self._build_response_text(service_request)
            response.async_set_speech(response_text)
            return response
            
        except Exception as err:
            LOGGER.error("服务调用失败: %s", str(err))
            response.async_set_error("service_call_error", f"服务调用失败: {str(err)}")
            return response

    def _clean_query(self, query: str) -> str:
        return not query and "" or re.sub(r'\b(随机|shuffle|播放|play|音乐|歌曲|歌|music|song)\b', '', query, flags=re.IGNORECASE).strip()
        
    def _find_player_by_name(self, name: str) -> str:
        if not name or not isinstance(name, str):
            return None
            
        for state in self.hass.states.async_all():
            if state.domain == "media_player":
                friendly_name = state.attributes.get("friendly_name", "")
                if friendly_name and name.lower() in friendly_name.lower():
                    return state.entity_id
        
        for entity in self._entity_reg.entities.values():
            if entity.domain == "media_player" and entity.entity_id in self.hass.states.async_entity_ids("media_player"):
                if entity.name and name.lower() in entity.name.lower():
                    return entity.entity_id
        
        for state in self.hass.states.async_all():
            if state.domain == "media_player" and name.lower() in state.entity_id.lower():
                return state.entity_id
            
        return None

    def _find_area_by_name(self, area_name: str) -> str:
        return not area_name and None or next((area_id for area_id, area in self._area_reg.areas.items() 
            if area_name.lower() in area.name.lower() and next((True for state in self.hass.states.async_all() 
                if state.domain == "media_player" and state.attributes.get("integration") == "media_player" 
                and (entity := self._entity_reg.async_get_entity_id(state.domain, state.entity_id.split(".")[0], state.object_id)) 
                and entity and entity.area_id == area_id), False)), None)
        
    def _get_slot_value(self, slot_data):
        return not slot_data and None or isinstance(slot_data, dict) and slot_data.get('value') or hasattr(slot_data, 'value') and getattr(slot_data, 'value') or str(slot_data)

    def _build_response_text(self, service_request: dict) -> str:
        data = service_request.get("data", {})
        target = service_request.get("target", {})
        
        target_desc = ""
        entity_id = "entity_id" in target and target["entity_id"]
        entity_id = entity_id and isinstance(entity_id, list) and entity_id and entity_id[0] or entity_id
        area_id = "area_id" in target and target["area_id"]
        area_id = area_id and isinstance(area_id, list) and area_id and area_id[0] or area_id
        
        target_desc = entity_id and self.hass.states.get(entity_id) and f" 在{self.hass.states.get(entity_id).attributes.get('friendly_name', entity_id)}上" or area_id and self._area_reg.async_get_area(area_id) and f" 在{self._area_reg.async_get_area(area_id).name}区域" or ""
        
        return f"正在{service_request.get('shuffle') and '随机' or ''}播放{data.get('artist') and f' {data.get('artist')}的' or ''}{data.get('album') and f' {data.get('album')}' or ''}{data.get('media_type') and data.get('media_type') != 'track' and f' ({data.get('media_type')})' or ''}{target_desc}"

class ZhipuAIImageGenIntent(intent.IntentHandler):    
    intent_type = INTENT_IMAGE_GEN
    slot_schema = {vol.Required("prompt"): str}

    def __init__(self, hass: HomeAssistant): super().__init__(); self.hass = hass

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        prompt = self.get_slot_value(slots.get("prompt"))
        response = intent.IntentResponse(intent_obj)
        try:
            result = await self.hass.services.async_call("zhipuai", "image_gen", 
                {"model": "cogview-3-flash", "size": "1024x1024", "prompt": prompt}, blocking=True, return_response=True)
            if result and result.get("success") and (original_url := result.get("original_url")):
                response.response_type = intent.IntentResponseType.ACTION_DONE
                response.async_set_speech(original_url)
            else:
                response.response_type = intent.IntentResponseType.ERROR
                response.async_set_error("generation_failed", "图片生成失败")
        except Exception as e:
            response.response_type = intent.IntentResponseType.ERROR
            response.async_set_error("service_call_error", f"调用服务失败: {str(e)}")
        return response

    def get_slot_value(self, slot_data): return None if not slot_data else slot_data.get("value")

def extract_intent_info(user_input: str, hass: HomeAssistant) -> Optional[Dict[str, Any]]:
    if re.match(r'^\d+\.?\d*$', user_input.strip()) or re.match(r'^[\w]+\.\d+$', user_input.strip()):
        return None
        
    entity_match = re.search(r'([a-zA-Z][\w_]+\.[\w_]+)', user_input)
    
    if not entity_match:
        return None
        
    entity_id = entity_match.group(1)
    domain = entity_id.split('.')[0]
    
    if domain == 'sensor':
        state = hass.states.get(entity_id)
        if state:
            return {
                'domain': domain,
                'action': 'get_state',
                'data': {
                    'entity_id': entity_id,
                    'state': state.state
                }
            }
        return None
    
    all_domains = set(domain for entity_id in hass.states.async_entity_ids() for domain in [entity_id.split(".")[0]])
    if domain not in all_domains:
        return None
    
    intent_mappings = {
        r'切换|toggle': 'toggle',
        r'停止|暂停|stop|pause': 'stop',
        r'继续|resume': 'start',
        r'设置|调整|set|adjust': 'set',
    }
    
    special_domains = {
        'cover': {'need_stop': True, 'need_position': True},  
        'lock': {'need_sync': True}, 
        'door': {'need_sync': True},  
        'garage_door': {'need_sync': True},  
    }
    
    action = next((action for pattern, action in intent_mappings.items() 
                  if re.search(pattern, user_input)), 'turn_on')
    
    is_all = "所有" in user_input or "全部" in user_input
    
    if is_all and domain in special_domains:
        action = 'all_' + action
        intent_data = {
            'domain': domain,
            'action': action,
            'data': {'entity_id': entity_id},
            'special_handling': special_domains[domain]
        }
    else:
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
                    {"success": True, "message": f"已设置 {friendly_name} 亮度{int(data['brightness'] * 100 / 255)}%"} if domain == "light" and service == "turn_on" and "brightness" in data else
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
