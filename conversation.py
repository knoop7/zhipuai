from __future__ import annotations
import json
import asyncio
import time
import re
from datetime import datetime, timedelta
from typing import Any, Literal, TypedDict, Dict, List, Optional
from voluptuous_openapi import convert
from homeassistant.components import assist_pipeline, conversation
from homeassistant.components.conversation import trace
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, MATCH_ALL, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, Context
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr, intent, llm, template, entity_registry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.util import ulid
from home_assistant_intents import get_languages
from .ai_request import send_ai_request
from .intents import IntentHandler, extract_intent_info
from .const import (
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_PROMPT,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    CONF_MAX_HISTORY_MESSAGES, 
    DOMAIN,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_MAX_HISTORY_MESSAGES,  
    RECOMMENDED_TOP_P,
    CONF_MAX_TOOL_ITERATIONS,
    CONF_COOLDOWN_PERIOD,
    DEFAULT_MAX_TOOL_ITERATIONS,
    DEFAULT_COOLDOWN_PERIOD,
    LOGGER,
    CONF_HISTORY_ANALYSIS,
    CONF_HISTORY_ENTITIES,
    CONF_HISTORY_DAYS,
    DEFAULT_HISTORY_DAYS,
    CONF_WEB_SEARCH,
    DEFAULT_WEB_SEARCH,
    CONF_HISTORY_INTERVAL,
    DEFAULT_HISTORY_INTERVAL,
)


class ChatCompletionMessageParam(TypedDict, total=False):
    role: str
    content: str | None
    name: str | None
    tool_calls: list["ChatCompletionMessageToolCallParam"] | None

class Function(TypedDict, total=False):
    name: str
    arguments: str

class ChatCompletionMessageToolCallParam(TypedDict):
    id: str
    type: str
    function: Function

class ChatCompletionToolParam(TypedDict):
    type: str
    function: dict[str, Any]

_FILTER_PATTERNS = [
    re.compile(r'```[\s\S]*?```'),
    re.compile(r'{[\s\S]*?}'),
    re.compile(r'(?m)^(import|from|def|class)\s+.*$')
]

def _format_tool(tool: llm.Tool, custom_serializer: Any | None) -> ChatCompletionToolParam:
    tool_spec = {
        "name": tool.name,
        "parameters": convert(tool.parameters, custom_serializer=custom_serializer),
    }
    if tool.description:
        tool_spec["description"] = tool.description
    return ChatCompletionToolParam(type="function", function=tool_spec)

def is_service_call(user_input: str) -> bool:
    patterns = {
        "control": ["让", "请", "帮我", "麻烦", "把", "将", "计时", "要", "想", "希望", "需要", "能否", "能不能", "可不可以", "可以", "帮忙", "给我", "替我", "为我", "我要", "我想", "我希望"],
        "action": {
            "turn_on": ["打开", "开启", "启动", "激活", "运行", "执行"],
            "turn_off": ["关闭", "关掉", "停止"],
            "toggle": ["切换"],
            "press": ["按", "按下", "点击"],
            "select": ["选择", "下一个", "上一个", "第一个", "最后一个"],
            "trigger": ["触发", "调用"],
            "media": ["暂停", "继续播放", "播放", "停止", "下一首", "下一曲", "下一个", "切歌", "换歌","上一首", "上一曲", "上一个", "返回上一首", "音量"],
            "climate": ["制冷", "制热", "风速", "模式", "调温", "调到", "设置", 
                      "空调", "冷气", "暖气", "冷风", "暖风", "自动模式", "除湿", "送风",
                      "高档", "低档", "高速", "低速", "自动高", "自动低", "强劲", "自动"]
        }
    }
    
    has_pattern = bool(user_input and (
        any(k in user_input for k in patterns["control"]) or 
        any(k in user_input for action in patterns["action"].values() for k in (action if isinstance(action, list) else []))
    ))
    
    has_climate = (
        "空调" in user_input and (
            bool(re.search(r"\d+", user_input)) or  
            any(k in user_input for k in patterns["action"]["climate"])  
        )
    )
    
    has_entity = bool(re.search(r"([\w_]+\.[\w_]+)", user_input))
    
    return has_pattern or has_climate or has_entity

def extract_service_info(user_input: str, hass: HomeAssistant) -> Optional[Dict[str, Any]]:
    def find_entity(domain: str, text: str) -> Optional[str]:
        text = text.lower()
        return next((entity_id for entity_id in hass.states.async_entity_ids(domain) 
                    if text in entity_id.split(".")[1].lower() or 
                    text in hass.states.get(entity_id).attributes.get("friendly_name", "").lower() or
                    entity_id.split(".")[1].lower() in text or
                    hass.states.get(entity_id).attributes.get("friendly_name", "").lower() in text), None)

    def clean_text(text: str, patterns: List[str]) -> str:
        control_words = ["让", "请", "帮我", "麻烦", "把", "将"]
        return "".join(char for char in text if not any(word in char for word in patterns + control_words)).strip()

    if not is_service_call(user_input):
        return None

    media_patterns = {"暂停": "media_pause", "继续播放": "media_play", "播放": "media_play", "停止": "media_stop",
                     "下一首": "media_next_track", "下一曲": "media_next_track", "下一个": "media_next_track",
                     "切歌": "media_next_track", "换歌": "media_next_track", "上一首": "media_previous_track",
                     "上一曲": "media_previous_track", "上一个": "media_previous_track",
                     "返回上一首": "media_previous_track", "音量": "volume_set"}
    
    if entity_id := find_entity("media_player", user_input):
        for pattern, service in media_patterns.items():
            if pattern in user_input.lower():
                return ({"domain": "media_player", "service": service, "data": {"entity_id": entity_id, "volume_level": int(re.search(r'(\d+)', user_input).group(1)) / 100}} 
                        if service == "volume_set" and re.search(r'(\d+)', user_input) else 
                        {"domain": "media_player", "service": service, "data": {"entity_id": entity_id}})

    if any(p in user_input for p in ["按", "按下", "点击"]):
        return {"domain": "button", "service": "press", "data": {"entity_id": (re.search(r'(button\.\w+)', user_input).group(1) if re.search(r'(button\.\w+)', user_input) else 
                find_entity("button", clean_text(user_input, ["按", "按下", "点击"])))}} if (re.search(r'(button\.\w+)', user_input) or 
                find_entity("button", clean_text(user_input, ["按", "按下", "点击"]))) else None

    select_patterns = {"下一个": ("select_next", True), "上一个": ("select_previous", True),
                      "第一个": ("select_first", False), "最后一个": ("select_last", False),
                      "选择": ("select_option", False)}
    
    if entity_id := find_entity("select", user_input):
        return {"domain": "select", "service": select_patterns.get(next((k for k in select_patterns.keys() if k in user_input), "选择"))[0],
                "data": {"entity_id": entity_id, "cycle": select_patterns.get(next((k for k in select_patterns.keys() if k in user_input), "选择"))[1]}} if any(p in user_input for p in select_patterns.keys()) else None

    if any(p in user_input for p in ["触发", "调用", "执行", "运行", "启动"]):
        name = clean_text(user_input, ["触发", "调用", "执行", "运行", "启动", "脚本", "自动化", "场景"])
        return next(({"domain": domain, "service": service, "data": {"entity_id": entity_id}}
                    for domain, service in [("script", "turn_on"), ("automation", "trigger"), ("scene", "turn_on")]
                    if (entity_id := find_entity(domain, name))), None)

    climate_patterns = {"温度": "set_temperature", "制冷": "set_hvac_mode", "制热": "set_hvac_mode",
                       "风速": "set_fan_mode", "模式": "set_hvac_mode", "湿度": "set_humidity",
                       "调温": "set_temperature", "调到": "set_temperature", "设置": "set_hvac_mode",
                       "度": "set_temperature"}

    if entity_id := find_entity("climate", user_input):
        temperature_match = re.search(r'(\d+)(?:\s*度)?', user_input)
        if temperature_match and ("温度" in user_input or "调温" in user_input or "调到" in user_input or "度" in user_input):
            temperature = int(temperature_match.group(1))
            current_temp = hass.states.get(entity_id).attributes.get('current_temperature')
            hvac_mode = "cool" if current_temp > temperature else "heat" if current_temp is not None else None
            return {"domain": "climate", "service": "set_temperature", 
                    "data": {"entity_id": entity_id, "temperature": temperature, "hvac_mode": hvac_mode}} if hvac_mode else {"domain": "climate", "service": "set_temperature", 
                    "data": {"entity_id": entity_id, "temperature": temperature}}

        for pattern, service in climate_patterns.items():
            if pattern in user_input.lower():
                if service == "set_temperature":
                    temperature_match = re.search(r'(\d+)', user_input)
                    if temperature_match:
                        temperature = int(temperature_match.group(1))
                        current_temp = hass.states.get(entity_id).attributes.get('current_temperature')
                        hvac_mode = "cool" if current_temp > temperature else "heat" if current_temp is not None else None
                        return {"domain": "climate", "service": service, 
                                "data": {"entity_id": entity_id, "temperature": temperature, "hvac_mode": hvac_mode}} if hvac_mode else {"domain": "climate", "service": service, 
                                "data": {"entity_id": entity_id, "temperature": temperature}}
                elif service == "set_hvac_mode":
                    hvac_mode_map = {"制冷": "cool", "制热": "heat", "自动": "auto", "除湿": "dry",
                                   "送风": "fan_only", "关闭": "off", "停止": "off"}
                    return {"domain": "climate", "service": service, 
                            "data": {"entity_id": entity_id, "hvac_mode": next((mode for cn, mode in hvac_mode_map.items() if cn in user_input), "auto")}}
                elif service == "set_fan_mode":
                    fan_mode_map = {"高档": "on_high", "高速": "on_high", "强劲": "on_high",
                                  "低档": "on_low", "低速": "on_low", "自动高": "auto_high",
                                  "自动高档": "auto_high", "自动低": "auto_low", "自动低档": "auto_low",
                                  "关闭": "off", "停止": "off"}
                    return {"domain": "climate", "service": service, 
                            "data": {"entity_id": entity_id, "fan_mode": next((mode for cn, mode in fan_mode_map.items() if cn in user_input), "auto_low")}}
                elif service == "set_humidity":
                    humidity_match = re.search(r'(\d+)', user_input)
                    return {"domain": "climate", "service": service, 
                            "data": {"entity_id": entity_id, "humidity": int(humidity_match.group(1))}} if humidity_match else None

    return None

class ZhipuAIConversationEntity(conversation.ConversationEntity, conversation.AbstractConversationAgent):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_response = ""

    def __init__(self, entry: ConfigEntry, hass: HomeAssistant) -> None:
        self.entry = entry
        self.hass = hass
        self.history: dict[str, list[ChatCompletionMessageParam]] = {}
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="智谱清言",
            model="ChatGLM Pro",
            entry_type=dr.DeviceEntryType.SERVICE,
        )
        if self.entry.options.get(CONF_LLM_HASS_API) and self.entry.options.get(CONF_LLM_HASS_API) != "none":
            self._attr_supported_features = conversation.ConversationEntityFeature.CONTROL
        self.last_request_time = 0
        self.max_tool_iterations = min(entry.options.get(CONF_MAX_TOOL_ITERATIONS, DEFAULT_MAX_TOOL_ITERATIONS), 5)
        self.cooldown_period = entry.options.get(CONF_COOLDOWN_PERIOD, DEFAULT_COOLDOWN_PERIOD)
        self.llm_api = None
        self.intent_handler = IntentHandler(hass)
        self.entity_registry = er.async_get(hass)
        self.device_registry = dr.async_get(hass)
        self.service_call_attempts = 0
        self._attr_native_value = "就绪"
        self._attr_extra_state_attributes = {"response": ""}

    @property
    def supported_languages(self) -> list[str]:
        return list(dict.fromkeys(languages + ["zh-cn", "zh-tw", "zh-hk", "en"])) if (languages := get_languages()) and "zh" in languages else languages

    @property
    def state_attributes(self):
        attributes = super().state_attributes or {}
        attributes["entity"] = "ZHIPU.AI"
        if self._attr_response:
            attributes["response"] = self._attr_response
        return attributes

    def _filter_response_content(self, content: str) -> str:
        for pattern in _FILTER_PATTERNS:
            content = pattern.sub('', content)
        if not content.strip():
            return "抱歉，暂不支持该操作。如果问题持续，可能需要调整指令。"
        return content.strip()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        assist_pipeline.async_migrate_engine(self.hass, "conversation", self.entry.entry_id, self.entity_id)
        conversation.async_set_agent(self.hass, self.entry, self)
        self.entry.async_on_unload(self.entry.add_update_listener(self._async_entry_update_listener))

    async def async_will_remove_from_hass(self) -> None:
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    async def async_process(self, user_input: conversation.ConversationInput) -> conversation.ConversationResult:
        if user_input.context and user_input.context.id and user_input.context.id.startswith(f"{DOMAIN}_service_call"):
            return None
            
        current_time = time.time()
        if current_time - self.last_request_time < self.cooldown_period:
            await asyncio.sleep(self.cooldown_period - (current_time - self.last_request_time))
        self.last_request_time = time.time()

        intent_response = intent.IntentResponse(language=user_input.language)
        
        if is_service_call(user_input.text):
            service_info = extract_service_info(user_input.text, self.hass)
            if service_info:
                result = await self.intent_handler.call_service(
                    service_info["domain"],
                    service_info["service"],
                    service_info["data"]
                )
                if result["success"]:
                    intent_response.async_set_speech(result["message"])
                else:
                    intent_response.async_set_error(
                        intent.IntentResponseErrorCode.NO_VALID_TARGETS,
                        result["message"]
                    )
                return conversation.ConversationResult(
                    response=intent_response,
                    conversation_id=user_input.conversation_id
                )
                
        options = self.entry.options
        tools: list[ChatCompletionToolParam] | None = None
        user_name: str | None = None
        llm_context = llm.LLMContext(
            platform=DOMAIN,
            context=user_input.context,
            user_prompt=user_input.text,
            language=user_input.language,
            assistant=conversation.DOMAIN,
            device_id=user_input.device_id,
        )

        try:
            if options.get(CONF_LLM_HASS_API) and options[CONF_LLM_HASS_API] != "none":
                self.llm_api = await llm.async_get_api(self.hass, options[CONF_LLM_HASS_API], llm_context)
                tools = [_format_tool(tool, self.llm_api.custom_serializer) for tool in self.llm_api.tools][:8]
                
                if not options.get(CONF_WEB_SEARCH, DEFAULT_WEB_SEARCH):
                    if any(term in user_input.text.lower() for term in ["联网", "查询", "网页", "search"]):
                        intent_response.async_set_speech("联网搜索功能已关闭，请在配置中开启后再试。")
                        return conversation.ConversationResult(
                            response=intent_response,
                            conversation_id=user_input.conversation_id
                        )
                    tools = [tool for tool in tools if tool["function"]["name"] != "web_search"]
        except HomeAssistantError as err:
            intent_response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, f"获取 LLM API 时出错，将继续使用基本功能。")

        intent_info = extract_intent_info(user_input.text, self.hass)
        if intent_info:
            result = await self.intent_handler.handle_intent(intent_info)
            if result["success"]:
                intent_response.async_set_speech(result["message"])
            else:
                intent_response.async_set_error(
                    intent.IntentResponseErrorCode.NO_VALID_TARGETS,
                    result["message"]
                )
            return conversation.ConversationResult(
                response=intent_response,
                conversation_id=user_input.conversation_id
            )

        if user_input.conversation_id is None:
            conversation_id = ulid.ulid_now()
            messages = []
        elif user_input.conversation_id in self.history:
            conversation_id = user_input.conversation_id
            messages = self.history[conversation_id]
        else:
            conversation_id = user_input.conversation_id
            messages = []

        max_history_messages = options.get(CONF_MAX_HISTORY_MESSAGES, RECOMMENDED_MAX_HISTORY_MESSAGES)
        use_history = len(messages) < max_history_messages

        if user_input.context and user_input.context.user_id and (user := await self.hass.auth.async_get_user(user_input.context.user_id)):
            user_name = user.name
        try:
            er = entity_registry.async_get(self.hass)
            entities_dict = {entity_id: er.async_get(entity_id) 
                           for entity_id in self.hass.states.async_entity_ids()}
            exposed_entities = [
                entity for entity_id, entity in entities_dict.items()
                if entity and not entity.hidden
            ]

            prompt_parts = [
                template.Template(
                    llm.BASE_PROMPT + options.get(CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT),
                    self.hass,
                ).async_render(
                    {
                        "ha_name": self.hass.config.location_name,
                        "user_name": user_name,
                        "llm_context": llm_context,
                        "exposed_entities": exposed_entities,
                    },
                    parse_result=False,
                )
            ]

            if self.entry.options.get(CONF_HISTORY_ANALYSIS):
                entities = self.entry.options.get(CONF_HISTORY_ENTITIES, [])
                days = self.entry.options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS)
                
                if entities:
                    try:
                        end_time = datetime.now()
                        start_time = end_time - timedelta(days=days)
                        
                        history_text = []
                        history_text.append(f"\n以下是询问者所关注的实体的历史数据分析（{days}天内）：")
                        
                        instance = get_instance(self.hass)
                        history_data = await instance.async_add_executor_job(
                            get_significant_states,
                            self.hass,
                            start_time,
                            end_time,
                            entities,
                            None,
                            True,
                            True
                        )

                        for entity_id in entities:
                            state = self.hass.states.get(entity_id)
                            if state is None or entity_id not in history_data or not history_data[entity_id]:
                                history_text.append(f"\n{entity_id} (当前状态):")
                                history_text.append(
                                    f"- {state.state if state else 'unknown'} ({state.last_updated.astimezone().strftime('%m-%d %H:%M:%S') if state else 'unknown'})"
                                )
                            else:
                                states = history_data[entity_id]
                                history_text.append(f"\n{entity_id} (历史状态变化):")
                                last_state_text = None
                                last_time = None
                                for state in states:
                                    if state.state == "unavailable":
                                        continue
                                        
                                    current_time = state.last_updated.astimezone()
                                    interval_minutes = self.entry.options.get(CONF_HISTORY_INTERVAL, DEFAULT_HISTORY_INTERVAL)
                                    if last_time and (current_time - last_time).total_seconds() < interval_minutes * 60:
                                        continue
                                        
                                    state_text = f"- {state.state} ({current_time.strftime('%m-%d %H:%M:%S')})"
                                    if state_text != last_state_text:
                                        history_text.append(state_text)
                                        last_state_text = state_text
                                        last_time = current_time
                                if len(history_text) > 1:
                                    prompt_parts.append("\n".join(history_text))
                            
                    except Exception as err:
                        LOGGER.warning(f"获取历史数据时出错: {err}")

        except template.TemplateError as err:
            content_message = f"抱歉，Jinja2 模板解析出错，请检查配置模板，有实体信息配置导致获取失败： {err}"
            filtered_content = self._filter_response_content(content_message)
            intent_response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, filtered_content)
            return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)

        if self.llm_api:
            prompt_parts.append(self.llm_api.api_prompt)

        prompt = "\n".join(prompt_parts)
        LOGGER.info("提示部件： %s", prompt_parts)

        messages = [
            ChatCompletionMessageParam(role="system", content=prompt),
            *(messages if use_history else []),
            ChatCompletionMessageParam(role="user", content=user_input.text),
        ]
        if len(messages) > max_history_messages + 1:
            messages = [messages[0]] + messages[-(max_history_messages):]

        api_key = self.entry.data[CONF_API_KEY]
        try:
            for iteration in range(self.max_tool_iterations):
                payload = {
                    "model": options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL),
                    "messages": messages,  
                    "max_tokens": min(options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS), 4096),
                    "top_p": options.get(CONF_TOP_P, RECOMMENDED_TOP_P),
                    "temperature": options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE),
                    "request_id": conversation_id,
                }
                if tools:
                    payload["tools"] = tools


                result = await send_ai_request(api_key, payload, options)
                response = result["choices"][0]["message"]

                messages.append(response)
                self._attr_response = response.get("content", "")

                tool_calls = response.get("tool_calls")

                if not tool_calls:
                    break

                tool_call_failed = False
                for tool_call in tool_calls:
                    try:
                        tool_input = llm.ToolInput(
                            tool_name=tool_call["function"]["name"],
                            tool_args=json.loads(tool_call["function"]["arguments"]),
                        )

                        tool_response = await self._handle_tool_call(tool_input, user_input.text)

                        if isinstance(tool_response, dict) and "error" in tool_response:
                            raise Exception(tool_response["error"])

                        formatted_response = json.dumps(tool_response)
                        messages.append(
                            ChatCompletionMessageParam(
                                role="tool",
                                tool_call_id=tool_call["id"],
                                content=formatted_response,
                            )
                        )
                    except Exception as e:
                        content_message = f"操作执行失败: {str(e)}"
                        messages.append(
                            ChatCompletionMessageParam(
                                role="tool",
                                tool_call_id=tool_call["id"],
                                content=content_message,
                            )
                        )
                        tool_call_failed = True

                if tool_call_failed and self.service_call_attempts >= 3:
                    return await self._fallback_to_hass_llm(user_input, conversation_id)


            final_content = response.get("content", "").strip()
            
            if is_service_call(user_input.text):
                service_info = extract_service_info(final_content, self.hass)
                if service_info:
                    try:
                        await self.hass.services.async_call(
                            service_info["domain"],
                            service_info["service"],
                            service_info["data"],
                            blocking=True
                        )
                        message = f"成功执行{service_info['domain']}：{service_info['data']['entity_id']}"
                        intent_response.response_text = message
                        return conversation.ConversationResult(
                            response=intent_response,
                            conversation_id=conversation_id
                        )
                    except Exception as e:
                        intent_response.async_set_error(
                            intent.IntentResponseErrorCode.UNKNOWN,
                            f"执行服务失败：{str(e)}"
                        )
                        return conversation.ConversationResult(
                            response=intent_response,
                            conversation_id=conversation_id
                        )

            filtered_content = self._filter_response_content(final_content)

            self.history[conversation_id] = messages
            intent_response.async_set_speech(filtered_content)
            self._attr_extra_state_attributes["response"] = filtered_content
            return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)

        except Exception as err:
            return await self._fallback_to_hass_llm(user_input, conversation_id)

    async def _handle_tool_call(self, tool_input: llm.ToolInput, user_input: str) -> Dict[str, Any]:
        try:
            if self.llm_api and hasattr(self.llm_api, "async_call_tool"):
                try:
                    result = await self.llm_api.async_call_tool(tool_input)
                    if isinstance(result, dict):
                        if "error" not in result:
                            return result
                        else:
                            LOGGER.warning("LLM API调用返回错误: %s", result["error"])
                            return {"error": str(result["error"])}
                except AttributeError as e:
                    LOGGER.warning("LLM API调用参数错误: %s", str(e))
                    return {"error": "工具调用参数错误"}
                except Exception as e:
                    LOGGER.warning("LLM API调用失败: %s", str(e))
                    return {"error": f"工具调用失败: {str(e)}"}
            
            if is_service_call(user_input):
                service_info = extract_service_info(user_input, self.hass)
                if service_info:
                    result = await self.intent_handler.call_service(
                        service_info["domain"],
                        service_info["service"],
                        service_info["data"]
                    )
                    return result
                else:
                    return {"error": "无法解析服务调用信息"}
                
            return {"error": "无法处理该工具调用"}
            
        except Exception as e:
            return {"error": f"处理工具调用时发生错误: {str(e)}"}

    async def _fallback_to_hass_llm(self, user_input: conversation.ConversationInput, conversation_id: str) -> conversation.ConversationResult:
        try:
            agent = await conversation.async_get_agent(self.hass)
            result = await agent.async_process(user_input)
            return result
        except Exception as err:
            error_msg = "很抱歉，我现在无法正确处理您的请求，请稍后再试"
            
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                error_msg
            )
            return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)

    @staticmethod
    async def _async_entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
        entity = hass.data[DOMAIN].get(entry.entry_id)
        if entity:
            entity.entry = entry

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entity = ZhipuAIConversationEntity(config_entry, hass)
    async_add_entities([entity])
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = entity

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, ["conversation"]):
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok