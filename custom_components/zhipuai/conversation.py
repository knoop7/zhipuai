import json
import asyncio
import time
import re
from datetime import datetime
from typing import Any, Literal, TypedDict
from voluptuous_openapi import convert
import voluptuous as vol
from homeassistant.components import assist_pipeline, conversation
from homeassistant.components.conversation import trace
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr, intent, llm, template, entity_registry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.color import RGBColor
from .ai_request import send_ai_request
from homeassistant.util import ulid
from .const import (
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_PROMPT,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    CONF_MAX_HISTORY_MESSAGES, 
    DOMAIN,
    LOGGER,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_MAX_HISTORY_MESSAGES,  
    RECOMMENDED_TOP_P,
    CONF_MAX_TOOL_ITERATIONS,
    CONF_COOLDOWN_PERIOD,
    DEFAULT_MAX_TOOL_ITERATIONS,
    DEFAULT_COOLDOWN_PERIOD,
    ZHIPUAI_URL,
)
from .service_caller import get_service_caller

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

def _format_tool(tool: llm.Tool, custom_serializer: Any | None) -> ChatCompletionToolParam:
    tool_spec = {
        "name": tool.name,
        "parameters": convert(tool.parameters, custom_serializer=custom_serializer),
    }
    if tool.description:
        tool_spec["description"] = tool.description
    return ChatCompletionToolParam(type="function", function=tool_spec)

def feature_check(feature_name):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            if hasattr(self, feature_name):
                return func(self, *args, **kwargs)
            else:
                LOGGER.info(f"功能 '{feature_name}' 不可用，跳过")
                return None
        return wrapper
    return decorator

class ZhipuAIConversationEntity(conversation.ConversationEntity, conversation.AbstractConversationAgent):
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry
        self.history: dict[str, list[ChatCompletionMessageParam]] = {}
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="智谱清言",
            model="ChatGLM Pro",
            entry_type=dr.DeviceEntryType.SERVICE,
        )
        if self.entry.options.get(CONF_LLM_HASS_API):
            self._attr_supported_features = conversation.ConversationEntityFeature.CONTROL
        self.last_request_time = 0
        self.max_tool_iterations = min(entry.options.get(CONF_MAX_TOOL_ITERATIONS, DEFAULT_MAX_TOOL_ITERATIONS), 5)
        self.cooldown_period = entry.options.get(CONF_COOLDOWN_PERIOD, DEFAULT_COOLDOWN_PERIOD)
        self.llm_api = None
        self.service_caller = None

    def _filter_response_content(self, content: str) -> str:
        content = re.sub(r'```[\s\S]*?```', '', content)
        content = re.sub(r'{[\s\S]*?}', '', content)
        content = re.sub(r'(?m)^(import|from|def|class)\s+.*$', '', content)
        if not content.strip():
            return "抱歉，我的回复似乎出现了问题。请再尝试一次，如果问题持续，可能需要调整指令。"
        return content.strip()

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return MATCH_ALL

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        assist_pipeline.async_migrate_engine(self.hass, "conversation", self.entry.entry_id, self.entity_id)
        conversation.async_set_agent(self.hass, self.entry, self)
        self.entry.async_on_unload(self.entry.add_update_listener(self._async_entry_update_listener))
        self.service_caller = get_service_caller(self.hass)

    async def async_will_remove_from_hass(self) -> None:
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    async def async_process(self, user_input: conversation.ConversationInput) -> conversation.ConversationResult:
        current_time = time.time()
        if current_time - self.last_request_time < self.cooldown_period:
            await asyncio.sleep(self.cooldown_period - (current_time - self.last_request_time))
        self.last_request_time = time.time()

        options = self.entry.options
        intent_response = intent.IntentResponse(language=user_input.language)
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
        except HomeAssistantError as err:
            LOGGER.warning("获取 LLM API 时出错，将继续使用基本功能：%s", err)

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
            exposed_entities = [
                er.async_get(entity_id) for entity_id in self.hass.states.async_entity_ids()
                if er.async_get(entity_id) and not er.async_get(entity_id).hidden
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
        except TemplateError as err:
            LOGGER.error("渲染提示时出错: %s", err)
            error_message = f"抱歉，我的模板有问题： {err}"
            filtered_error = self._filter_response_content(error_message)
            intent_response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, filtered_error)
            return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)

        if self.llm_api:
            prompt_parts.append(self.llm_api.api_prompt)

        prompt = "\n".join(prompt_parts)

        messages = [
            ChatCompletionMessageParam(role="system", content=prompt),
            *(messages if use_history else []),
            ChatCompletionMessageParam(role="user", content=user_input.text),
        ]
        if len(messages) > max_history_messages + 1:
            messages = [messages[0]] + messages[-(max_history_messages):]

        LOGGER.debug("提示: %s", messages)
        LOGGER.debug("工具: %s", tools)
        trace.async_conversation_trace_append(
            trace.ConversationTraceEventType.AGENT_DETAIL,
            {"messages": messages, "tools": self.llm_api.tools if self.llm_api else None},
        )

        api_key = self.entry.data[CONF_API_KEY]
        try:
            for iteration in range(self.max_tool_iterations):
                payload = {
                    "model": options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL),
                    "messages": messages[-10:],
                    "max_tokens": min(options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS), 1000),
                    "top_p": options.get(CONF_TOP_P, RECOMMENDED_TOP_P),
                    "temperature": options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE),
                    "request_id": conversation_id,
                }
                if tools:
                    payload["tools"] = tools

                result = await send_ai_request(api_key, payload)

                LOGGER.debug("AI 响应: %s", result)
                response = result["choices"][0]["message"]

                messages.append(response)
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

                        formatted_response = json.dumps(tool_response)
                        messages.append(
                            ChatCompletionMessageParam(
                                role="tool",
                                tool_call_id=tool_call["id"],
                                content=formatted_response,
                            )
                        )
                    except Exception as e:
                        LOGGER.error("工具调用失败: %s", e)
                        error_message = f"操作执行失败: {str(e)}"
                        messages.append(
                            ChatCompletionMessageParam(
                                role="tool",
                                tool_call_id=tool_call["id"],
                                content=error_message,
                            )
                        )
                        tool_call_failed = True

                if tool_call_failed and iteration == self.max_tool_iterations - 1:
                    LOGGER.warning("多次工具调用失败，切换到内部 Home Assistant LLM")
                    return await self._fallback_to_hass_llm(user_input, conversation_id)

            final_content = response.get("content", "")
            filtered_content = self._filter_response_content(final_content)

            self.history[conversation_id] = messages
            intent_response.async_set_speech(filtered_content)
            return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)

        except Exception as err:
            LOGGER.error("处理 AI 请求时出错: %s", err)
            return await self._fallback_to_hass_llm(user_input, conversation_id)

    async def _fallback_to_hass_llm(self, user_input: conversation.ConversationInput, conversation_id: str) -> conversation.ConversationResult:
        LOGGER.info("切换到内部 Home Assistant LLM 进行处理")
        try:
            agent = await conversation.async_get_agent(self.hass)
            result = await agent.async_process(user_input)
            return result
        except Exception as err:
            LOGGER.error("内部 LLM 处理失败: %s", err)
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"很抱歉，我现在无法正确处理您的请求。请稍后再试。错误: {err}"
            )
            return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)

    async def _extract_entity(self, domain, name=None):
        try:
            entity_reg = er.async_get(self.hass)
            entities = entity_reg.entities
            if name and isinstance(name, str):
                for entity_id, entity in entities.items():
                    if entity.domain == domain and name.lower() in entity.name.lower():
                        return entity_id
            for entity_id, entity in entities.items():
                if entity.domain == domain:
                    return entity_id
        except Exception:
            pass
        return None

    async def _handle_tool_call(self, tool_input: llm.ToolInput, user_input: str):
        try:
            intent_name = tool_input.tool_name.lower()
            if any(keyword in user_input.lower() for keyword in ["调用", "服务", "动作执行", "执行服务", "使用服务"]):

                first_result = await self.service_caller.handle_service_call(tool_input)
                LOGGER.debug("第一次服务调用结果: %s", first_result)
                
                second_result = await self.service_caller.handle_service_call(tool_input)
                LOGGER.debug("第二次服务调用结果: %s", second_result)
                
                # 返回第二次调用的结果
                return second_result
            
            if intent_name.startswith("hass"):
                method_name = f"_handle_{intent_name[4:]}_intent"
                if hasattr(self, method_name):
                    return await getattr(self, method_name)(tool_input)
            return await self.llm_api.async_call_tool(tool_input)
        except Exception:
            return {"error": "处理工具调用时发生错误"}

    @feature_check('turn_intent')
    async def _handle_turn_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            domain = tool_input.tool_args.get('domain')
            if domain and isinstance(domain, str):
                entity_id = await self._extract_entity(domain, entity_name)
                if entity_id:
                    tool_input.tool_args[ATTR_ENTITY_ID] = entity_id
            return await self.llm_api.async_call_tool(tool_input)
        except Exception:
            pass
        return None

    @feature_check('get_state_intent')
    async def _handle_get_state_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            domain = tool_input.tool_args.get('domain')
            device_class = tool_input.tool_args.get('device_class')
            
            entity_id = await self._extract_entity(domain, entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的设备: 名称 '{entity_name}', 区域 '{area}', 域 '{domain}', 设备类 '{device_class}'"}

            state = self.hass.states.get(entity_id)
            if not state:
                return {"error": f"无法获取设备 {entity_id} 的状态"}

            return {
                "entity_id": entity_id,
                "state": state.state,
                "attributes": state.attributes
            }
        except Exception as e:
            return {"error": f"获取设备状态时发生错误: {str(e)}"}

    @feature_check('set_position_intent')
    async def _handle_set_position_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            position = tool_input.tool_args.get('position')
            
            if position is None or not (0 <= position <= 100):
                return {"error": "位置必须是0到100之间的数值"}

            entity_id = await self._extract_entity('cover', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的遮挡物: 名称 '{entity_name}', 区域 '{area}'"}

            await self.hass.services.async_call(
                'cover', 'set_cover_position',
                {ATTR_ENTITY_ID: entity_id, 'position': position},
                blocking=True
            )
            
            return {"success": f"已将 {entity_id} 的位置设置为 {position}%"}
        except Exception as e:
            return {"error": f"设置遮挡物位置时发生错误: {str(e)}"}

    @feature_check('light_set_intent')
    async def _handle_light_set_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            brightness = tool_input.tool_args.get('brightness')
            color = tool_input.tool_args.get('color')
            
            entity_id = await self._extract_entity('light', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的灯: 名称 '{entity_name}', 区域 '{area}'"}

            service_data = {ATTR_ENTITY_ID: entity_id}
            
            if brightness is not None:
                if not (0 <= brightness <= 100):
                    return {"error": "亮度必须是0到100之间的数值"}
                service_data['brightness_pct'] = brightness
            
            if color:
                service_data['rgb_color'] = color

            await self.hass.services.async_call(
                'light', 'turn_on',
                service_data,
                blocking=True
            )
            
            return {"success": f"已更新 {entity_id} 的设置"}
        except Exception as e:
            return {"error": f"设置灯光时发生错误: {str(e)}"}

    @feature_check('climate_get_temperature_intent')
    async def _handle_climate_get_temperature_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            
            entity_id = await self._extract_entity('climate', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的空调设备: 名称 '{entity_name}', 区域 '{area}'"}

            state = self.hass.states.get(entity_id)
            if not state:
                return {"error": f"无法获取设备 {entity_id} 的状态"}

            attributes = state.attributes
            response = {
                "entity_id": entity_id,
                "name": entity_name,
                "area": area,
                "friendly_name": attributes.get('friendly_name'),
                "state": state.state,
                "current_temperature": attributes.get('current_temperature'),
                "target_temperature": attributes.get('temperature'),
                "hvac_mode": state.state,
                "hvac_action": attributes.get('hvac_action'),
                "unit_of_measurement": attributes.get('unit_of_measurement', '°C')
            }

            optional_attrs = [
                'target_temp_high', 'target_temp_low', 'current_humidity', 'humidity',
                'fan_mode', 'swing_mode', 'min_temp', 'max_temp', 'min_humidity', 'max_humidity',
                'hvac_modes', 'fan_modes', 'swing_modes', 'supported_features'
            ]
            for attr in optional_attrs:
                if attr in attributes:
                    response[attr] = attributes[attr]

            return {k: v for k, v in response.items() if v is not None}
        except Exception as e:
            return {"error": f"获取空调温度信息时发生错误: {str(e)}"}

    @feature_check('shopping_list_add_item_intent')
    async def _handle_shopping_list_add_item_intent(self, tool_input: llm.ToolInput):
        try:
            item = tool_input.tool_args.get('item')
            if not item:
                return {"error": "未提供要添加的物品"}

            await self.hass.services.async_call(
                'shopping_list', 'add_item',
                {"name": item},
                blocking=True
            )
            
            return {"success": f"已将 '{item}' 添加到购物清单"}
        except Exception as e:
            return {"error": f"添加购物清单项目时发生错误: {str(e)}"}

    @feature_check('get_weather_intent')
    async def _handle_get_weather_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            entity_id = await self._extract_entity('weather', entity_name)
            
            if not entity_id:
                return {"error": f"无法找到指定的天气实体: '{entity_name}'"}

            state = self.hass.states.get(entity_id)
            if not state:
                return {"error": f"无法获取天气实体 {entity_id} 的状态"}

            attributes = state.attributes
            return {
                "entity_id": entity_id,
                "state": state.state,
                "temperature": attributes.get('temperature'),
                "humidity": attributes.get('humidity'),
                "pressure": attributes.get('pressure'),
                "wind_speed": attributes.get('wind_speed'),
                "wind_bearing": attributes.get('wind_bearing'),
                "forecast": attributes.get('forecast')
            }
        except Exception as e:
            return {"error": f"获取天气信息时发生错误: {str(e)}"}

    @feature_check('list_add_item_intent')
    async def _handle_list_add_item_intent(self, tool_input: llm.ToolInput):
        try:
            item = tool_input.tool_args.get('item')
            name = tool_input.tool_args.get('name')
            if not item or not name:
                return {"error": "未提供要添加的物品或清单名称"}

            await self.hass.services.async_call(
                'todo', 'add_item',
                {"item": item, "list_name": name},
                blocking=True
            )
            
            return {"success": f"已将 '{item}' 添加到清单 '{name}'"}
        except Exception as e:
            return {"error": f"添加清单项目时发生错误: {str(e)}"}

    @feature_check('vacuum_intent')
    async def _handle_vacuum_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            action = tool_input.tool_args.get('action', 'start')
            
            entity_id = await self._extract_entity('vacuum', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的吸尘器: 名称 '{entity_name}', 区域 '{area}'"}

            if action == 'start':
                service = 'start'
            elif action == 'return_to_base':
                service = 'return_to_base'
            else:
                return {"error": f"不支持的操作: {action}"}

            await self.hass.services.async_call(
                'vacuum', service,
                {ATTR_ENTITY_ID: entity_id},
                blocking=True
            )
            
            return {"success": f"已执行吸尘器操作: {action}"}
        except Exception as e:
            return {"error": f"控制吸尘器时发生错误: {str(e)}"}

    @feature_check('set_volume_intent')
    async def _handle_set_volume_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            volume_level = tool_input.tool_args.get('volume_level')
            
            if volume_level is None or not (0 <= volume_level <= 100):
                return {"error": "音量必须是0到100之间的数值"}

            entity_id = await self._extract_entity('media_player', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的媒体播放器: 名称 '{entity_name}', 区域 '{area}'"}

            await self.hass.services.async_call(
                'media_player', 'volume_set',
                {ATTR_ENTITY_ID: entity_id, 'volume_level': volume_level / 100},
                blocking=True
            )
            
            return {"success": f"已将 {entity_id} 的音量设置为 {volume_level}%"}
        except Exception as e:
            return {"error": f"设置音量时发生错误: {str(e)}"}

    @feature_check('timer_intent')
    async def _handle_timer_intent(self, tool_input: llm.ToolInput):
        try:
            action = tool_input.tool_args.get('action')
            hours = tool_input.tool_args.get('hours', 0)
            minutes = tool_input.tool_args.get('minutes', 0)
            seconds = tool_input.tool_args.get('seconds', 0)
            name = tool_input.tool_args.get('name')

            if action == 'start':
                duration = hours * 3600 + minutes * 60 + seconds
                await self.hass.services.async_call(
                    'timer', 'start',
                    {'duration': f"{duration}", 'name': name},
                    blocking=True
                )
                return {"success": f"已启动计时器 '{name}', 持续时间: {hours}小时 {minutes}分钟 {seconds}秒"}
            elif action in ['cancel', 'pause', 'finish']:
                await self.hass.services.async_call(
                    'timer', action,
                    {'name': name},
                    blocking=True
                )
                return {"success": f"已{action}计时器 '{name}'"}
            else:
                return {"error": f"不支持的计时器操作: {action}"}
        except Exception as e:
            return {"error": f"操作计时器时发生错误: {str(e)}"}


    @feature_check('climate_control_intent')
    async def _handle_climate_control_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            hvac_mode = tool_input.tool_args.get('hvac_mode')
            temperature = tool_input.tool_args.get('temperature')
            
            entity_id = await self._extract_entity('climate', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的空调设备: 名称 '{entity_name}', 区域 '{area}'"}

            state = self.hass.states.get(entity_id)
            if not state:
                return {"error": f"无法获取设备 {entity_id} 的状态"}

            service_data = {ATTR_ENTITY_ID: entity_id}

            if hvac_mode:
                if hvac_mode in [HVAC_MODE_OFF, HVAC_MODE_HEAT, HVAC_MODE_COOL, HVAC_MODE_AUTO, HVAC_MODE_DRY, HVAC_MODE_FAN_ONLY]:
                    service_data['hvac_mode'] = hvac_mode
                else:
                    return {"error": f"不支持的 HVAC 模式: {hvac_mode}"}

            if temperature is not None:
                min_temp = state.attributes.get('min_temp', 7)
                max_temp = state.attributes.get('max_temp', 35)
                if min_temp <= temperature <= max_temp:
                    service_data['temperature'] = temperature
                else:
                    return {"error": f"温度 {temperature} 超出范围 ({min_temp}-{max_temp})"}

            await self.hass.services.async_call(
                'climate', 'set_temperature',
                service_data,
                blocking=True
            )

            return {"success": f"已更新 {entity_id} 的设置"}
        except Exception as e:
            return {"error": f"控制空调时发生错误: {str(e)}"}

    @feature_check('lock_control_intent')
    async def _handle_lock_control_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            action = tool_input.tool_args.get('action')

            entity_id = await self._extract_entity('lock', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的锁: 名称 '{entity_name}', 区域 '{area}'"}

            if action == 'lock':
                service = 'lock'
            elif action == 'unlock':
                service = 'unlock'
            else:
                return {"error": f"不支持的锁操作: {action}"}

            await self.hass.services.async_call(
                'lock', service,
                {ATTR_ENTITY_ID: entity_id},
                blocking=True
            )

            return {"success": f"已{action} {entity_id}"}
        except Exception as e:
            return {"error": f"控制锁时发生错误: {str(e)}"}

    @feature_check('blinds_control_intent')
    async def _handle_blinds_control_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            action = tool_input.tool_args.get('action')
            position = tool_input.tool_args.get('position')

            entity_id = await self._extract_entity('cover', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的百叶窗: 名称 '{entity_name}', 区域 '{area}'"}

            if action in ['open', 'close']:
                service = f'{action}_cover'
                await self.hass.services.async_call(
                    'cover', service,
                    {ATTR_ENTITY_ID: entity_id},
                    blocking=True
                )
            elif action == 'set_position' and position is not None:
                if 0 <= position <= 100:
                    await self.hass.services.async_call(
                        'cover', 'set_cover_position',
                        {ATTR_ENTITY_ID: entity_id, 'position': position},
                        blocking=True
                    )
                else:
                    return {"error": "位置必须是0到100之间的数值"}
            else:
                return {"error": f"不支持的百叶窗操作: {action}"}

            return {"success": f"已执行百叶窗操作: {action}"}
        except Exception as e:
            return {"error": f"控制百叶窗时发生错误: {str(e)}"}

    @feature_check('garage_door_control_intent')
    async def _handle_garage_door_control_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            action = tool_input.tool_args.get('action')

            entity_id = await self._extract_entity('cover', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的车库门: 名称 '{entity_name}', 区域 '{area}'"}

            if action == 'open':
                service = 'open_cover'
            elif action == 'close':
                service = 'close_cover'
            else:
                return {"error": f"不支持的车库门操作: {action}"}

            await self.hass.services.async_call(
                'cover', service,
                {ATTR_ENTITY_ID: entity_id},
                blocking=True
            )

            return {"success": f"已{action}车库门 {entity_id}"}
        except Exception as e:
            return {"error": f"控制车库门时发生错误: {str(e)}"}

    @feature_check('irrigation_control_intent')
    async def _handle_irrigation_control_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            action = tool_input.tool_args.get('action')

            entity_id = await self._extract_entity('switch', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的灌溉系统: 名称 '{entity_name}', 区域 '{area}'"}

            if action == 'turn_on':
                service = 'turn_on'
            elif action == 'turn_off':
                service = 'turn_off'
            else:
                return {"error": f"不支持的灌溉系统操作: {action}"}

            await self.hass.services.async_call(
                'switch', service,
                {ATTR_ENTITY_ID: entity_id},
                blocking=True
            )

            return {"success": f"已{action}灌溉系统 {entity_id}"}
        except Exception as e:
            return {"error": f"控制灌溉系统时发生错误: {str(e)}"}

    @feature_check('security_system_control_intent')
    async def _handle_security_system_control_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            action = tool_input.tool_args.get('action')

            entity_id = await self._extract_entity('alarm_control_panel', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的安全系统: 名称 '{entity_name}', 区域 '{area}'"}

            if action in ['arm_away', 'arm_home', 'disarm']:
                service = action
            else:
                return {"error": f"不支持的安全系统操作: {action}"}

            await self.hass.services.async_call(
                'alarm_control_panel', service,
                {ATTR_ENTITY_ID: entity_id},
                blocking=True
            )

            return {"success": f"已执行安全系统操作: {action}"}
        except Exception as e:
            return {"error": f"控制安全系统时发生错误: {str(e)}"}

    @feature_check('camera_control_intent')
    async def _handle_camera_control_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            action = tool_input.tool_args.get('action')

            entity_id = await self._extract_entity('camera', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的摄像头: 名称 '{entity_name}', 区域 '{area}'"}

            if action == 'enable':
                service = 'turn_on'
            elif action == 'disable':
                service = 'turn_off'
            elif action == 'snapshot':
                service = 'snapshot'
            else:
                return {"error": f"不支持的摄像头操作: {action}"}

            await self.hass.services.async_call(
                'camera', service,
                {ATTR_ENTITY_ID: entity_id},
                blocking=True
            )

            return {"success": f"已执行摄像头操作: {action}"}
        except Exception as e:
            return {"error": f"控制摄像头时发生错误: {str(e)}"}

    @feature_check('fan_control_intent')
    async def _handle_fan_control_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            action = tool_input.tool_args.get('action')
            speed = tool_input.tool_args.get('speed')

            entity_id = await self._extract_entity('fan', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的风扇: 名称 '{entity_name}', 区域 '{area}'"}

            service_data = {ATTR_ENTITY_ID: entity_id}

            if action == 'turn_on':
                service = 'turn_on'
                if speed:
                    service_data['percentage'] = speed
            elif action == 'turn_off':
                service = 'turn_off'
            elif action == 'set_speed':
                service = 'set_percentage'
                if speed is not None and 0 <= speed <= 100:
                    service_data['percentage'] = speed
                else:
                    return {"error": "速度必须是0到100之间的数值"}
            else:
                return {"error": f"不支持的风扇操作: {action}"}

            await self.hass.services.async_call(
                'fan', service,
                service_data,
                blocking=True
            )

            return {"success": f"已执行风扇操作: {action}"}
        except Exception as e:
            return {"error": f"控制风扇时发生错误: {str(e)}"}

    @feature_check('water_heater_control_intent')
    async def _handle_water_heater_control_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            action = tool_input.tool_args.get('action')
            temperature = tool_input.tool_args.get('temperature')

            entity_id = await self._extract_entity('water_heater', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的热水器: 名称 '{entity_name}', 区域 '{area}'"}

            state = self.hass.states.get(entity_id)
            if not state:
                return {"error": f"无法获取热水器 {entity_id} 的状态"}

            service_data = {ATTR_ENTITY_ID: entity_id}

            if action == 'turn_on':
                service = 'turn_on'
            elif action == 'turn_off':
                service = 'turn_off'
            elif action == 'set_temperature':
                service = 'set_temperature'
                if temperature is not None:
                    min_temp = state.attributes.get('min_temp', 30)
                    max_temp = state.attributes.get('max_temp', 60)
                    if min_temp <= temperature <= max_temp:
                        service_data['temperature'] = temperature
                    else:
                        return {"error": f"温度 {temperature} 超出范围 ({min_temp}-{max_temp})"}
                else:
                    return {"error": "未提供温度设置"}
            else:
                return {"error": f"不支持的热水器操作: {action}"}

            await self.hass.services.async_call(
                'water_heater', service,
                service_data,
                blocking=True
            )

            return {"success": f"已执行热水器操作: {action}"}
        except Exception as e:
            return {"error": f"控制热水器时发生错误: {str(e)}"}

    @feature_check('scene_activation_intent')
    async def _handle_scene_activation_intent(self, tool_input: llm.ToolInput):
        try:
            scene_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')

            entity_id = await self._extract_entity('scene', scene_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的场景: 名称 '{scene_name}', 区域 '{area}'"}

            await self.hass.services.async_call(
                'scene', 'turn_on',
                {ATTR_ENTITY_ID: entity_id},
                blocking=True
            )

            return {"success": f"已激活场景: {scene_name}"}
        except Exception as e:
            return {"error": f"激活场景时发生错误: {str(e)}"}

    @feature_check('media_player_control_intent')
    async def _handle_media_player_control_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            action = tool_input.tool_args.get('action')

            entity_id = await self._extract_entity('media_player', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的媒体播放器: 名称 '{entity_name}', 区域 '{area}'"}

            if action in ['play', 'pause', 'stop', 'next_track', 'previous_track']:
                service = action
            elif action == 'volume_up':
                service = 'volume_up'
            elif action == 'volume_down':
                service = 'volume_down'
            else:
                return {"error": f"不支持的媒体播放器操作: {action}"}

            await self.hass.services.async_call(
                'media_player', service,
                {ATTR_ENTITY_ID: entity_id},
                blocking=True
            )

            return {"success": f"已执行媒体播放器操作: {action}"}
        except Exception as e:
            return {"error": f"控制媒体播放器时发生错误: {str(e)}"}

    @feature_check('script_run_intent')
    async def _handle_script_run_intent(self, tool_input: llm.ToolInput):
        try:
            script_name = tool_input.tool_args.get('name')

            script_entity = await self._extract_entity('script', script_name)
            
            if not script_entity:
                return {"error": f"无法找到指定的脚本: '{script_name}'"}

            await self.hass.services.async_call(
                'script', 'turn_on',
                {ATTR_ENTITY_ID: script_entity},
                blocking=True
            )

            return {"success": f"已运行脚本: {script_name}"}
        except Exception as e:
            return {"error": f"运行脚本时发生错误: {str(e)}"}

    @feature_check('light_color_intent')
    async def _handle_light_color_intent(self, tool_input: llm.ToolInput):
        try:
            entity_name = tool_input.tool_args.get('name')
            area = tool_input.tool_args.get('area')
            color = tool_input.tool_args.get('color')

            entity_id = await self._extract_entity('light', entity_name, area)
            
            if not entity_id:
                return {"error": f"无法找到指定的灯: 名称 '{entity_name}', 区域 '{area}'"}

            if not color:
                return {"error": "未指定颜色"}

            color_map = {
                "red": [255, 0, 0],
                "green": [0, 255, 0],
                "blue": [0, 0, 255],
                "white": [255, 255, 255],
            }

            rgb_color = color_map.get(color.lower())
            if not rgb_color:
                return {"error": f"不支持的颜色: {color}"}

            await self.hass.services.async_call(
                'light', 'turn_on',
                {ATTR_ENTITY_ID: entity_id, 'rgb_color': rgb_color},
                blocking=True
            )

            return {"success": f"已将灯 {entity_name} 的颜色设置为 {color}"}
        except Exception as e:
            return {"error": f"设置灯光颜色时发生错误: {str(e)}"}

    @feature_check('notify_intent')
    async def _handle_notify_intent(self, tool_input: llm.ToolInput):
        try:
            message = tool_input.tool_args.get('message')
            target = tool_input.tool_args.get('target', 'all')

            if not message:
                return {"error": "未提供通知消息"}

            await self.hass.services.async_call(
                'notify', target,
                {"message": message},
                blocking=True
            )

            return {"success": f"已发送通知: '{message}' 到 {target}"}
        except Exception as e:
            return {"error": f"发送通知时发生错误: {str(e)}"}

    @feature_check('text_to_speech_intent')
    async def _handle_text_to_speech_intent(self, tool_input: llm.ToolInput):
        try:
            message = tool_input.tool_args.get('message')
            entity_id = tool_input.tool_args.get('entity_id')

            if not message:
                return {"error": "未提供要转换为语音的文本"}

            if not entity_id:
                return {"error": "未指定目标媒体播放器"}

            await self.hass.services.async_call(
                'tts', 'google_translate_say',
                {
                    "entity_id": entity_id,
                    "message": message
                },
                blocking=True
            )

            return {"success": f"已将文本 '{message}' 转换为语音并在 {entity_id} 上播放"}
        except Exception as e:
            return {"error": f"文本转语音时发生错误: {str(e)}"}


    @staticmethod
    async def _async_entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
        entity = hass.data[DOMAIN].get(entry.entry_id)
        if entity:
            entity.entry = entry
            entity.max_tool_iterations = min(entry.options.get(CONF_MAX_TOOL_ITERATIONS, DEFAULT_MAX_TOOL_ITERATIONS), 5)
            entity.cooldown_period = entry.options.get(CONF_COOLDOWN_PERIOD, DEFAULT_COOLDOWN_PERIOD)
            await entity.async_update_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    try:
        entity = ZhipuAIConversationEntity(config_entry)
        async_add_entities([entity])
        hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = entity
    except Exception as e:
        raise

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        if unload_ok := await hass.config_entries.async_unload_platforms(entry, ["conversation"]):
            hass.data[DOMAIN].pop(entry.entry_id, None)
        return unload_ok
    except Exception as e:
        return False

def _format_tool(tool: llm.Tool, custom_serializer: Any | None) -> ChatCompletionToolParam:
    try:
        tool_spec = {
            "name": tool.name,
            "parameters": convert(tool.parameters, custom_serializer=custom_serializer),
        }
        if tool.description:
            tool_spec["description"] = tool.description
        return ChatCompletionToolParam(type="function", function=tool_spec)
    except Exception as e:
        return ChatCompletionToolParam(type="function", function={"name": "error", "parameters": {}})
