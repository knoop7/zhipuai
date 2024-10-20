import json
import asyncio
import time
import re
from datetime import datetime
from typing import Any, Literal, TypedDict, Awaitable
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
from .service_caller import ServiceCaller

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

def is_service_call(user_input: str) -> bool:
    patterns = [
        r"调用服务\s+(.+)",
        r"执行服务\s+(.+)",
        r"使用服务\s+(.+)"
    ]
    return any(re.search(pattern, user_input) for pattern in patterns)

def extract_service_info(user_input: str):
    match = re.search(r"(调用|执行|使用)服务\s+(\w+)\.(\w+)(?:\s+(.+))?", user_input)
    if match:
        domain, service = match.group(2), match.group(3)
        params = match.group(4) if match.group(4) else ""
        return {"domain": domain, "service": service, "params": params}
    return None

class ZhipuAIConversationEntity(conversation.ConversationEntity, conversation.AbstractConversationAgent):
    _attr_has_entity_name = True
    _attr_name = None

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
        if self.entry.options.get(CONF_LLM_HASS_API):
            self._attr_supported_features = conversation.ConversationEntityFeature.CONTROL
        self.last_request_time = 0
        self.max_tool_iterations = min(entry.options.get(CONF_MAX_TOOL_ITERATIONS, DEFAULT_MAX_TOOL_ITERATIONS), 5)
        self.cooldown_period = entry.options.get(CONF_COOLDOWN_PERIOD, DEFAULT_COOLDOWN_PERIOD)
        self.llm_api = None
        self.service_caller = ServiceCaller(hass)

    def _filter_response_content(self, content: str) -> str:
        content = re.sub(r'```[\s\S]*?```', '', content)
        content = re.sub(r'{[\s\S]*?}', '', content)
        content = re.sub(r'(?m)^(import|from|def|class)\s+.*$', '', content)
        if not content.strip():
            return "抱歉，暂不支持该操作。如果问题持续，可能需要调整指令。"
        return content.strip()

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return MATCH_ALL

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        assist_pipeline.async_migrate_engine(self.hass, "conversation", self.entry.entry_id, self.entity_id)
        conversation.async_set_agent(self.hass, self.entry, self)
        self.entry.async_on_unload(self.entry.add_update_listener(self._async_entry_update_listener))

    async def async_will_remove_from_hass(self) -> None:
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    async def async_process(self, user_input: conversation.ConversationInput) -> Awaitable[conversation.ConversationResult]:
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
        except template.TemplateError as err:
            LOGGER.error("渲染提示时出错: %s", err)
            content_message = f"抱歉，我的模板有问题： {err}"
            filtered_content = self._filter_response_content(content_message)
            intent_response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, filtered_content)
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
                        content_message = f"操作执行失败: {str(e)}"
                        messages.append(
                            ChatCompletionMessageParam(
                                role="tool",
                                tool_call_id=tool_call["id"],
                                content=content_message,
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
            
            if is_service_call(user_input):
                service_info = extract_service_info(user_input)
                if service_info:
                    result = await self.service_caller.handle_service_call(service_info)
                    if isinstance(result, dict) and "content" in result:
                        return {"content": f"执行服务时出错: {result['content']}"}
                    return result
                else:
                    return {"content": "无法解析服务调用信息，请提供更详细的服务名称和参数。"}
            
            if intent_name.startswith("hass"):
                method_name = f"_handle_{intent_name[4:]}_intent"
                if hasattr(self, method_name):
                    try:
                        result = await getattr(self, method_name)(tool_input)
                        if isinstance(result, dict) and "content" in result:
                            return {"content": f"处理意图时出错: {result['content']}"}
                        return result
                    except HomeAssistantError as ha_error:
                        content_message = str(ha_error)
                        if "Domain not supported" in content_message:
                            return {"content": f"不支持的设备类型: {content_message.split(':')[-1].strip()}"}
                        elif "MatchFailedError" in content_message:
                            return {"content": "未找到匹配的设备。请检查设备名称是否正确，或尝试使用更具体的名称。"}
                        else:
                            return {"content": f"处理意图时出错: {content_message}"}
            
            if self.llm_api:
                result = await self.llm_api.async_call_tool(tool_input)
                if isinstance(result, dict) and "content" in result:
                    return {"content": f"LLM API 调用出错: {result['content']}"}
                return result
            else:
                return {"content": "无法处理该工具调用，LLM API 未初始化"}
        
        except Exception as e:
            content_message = f"处理工具调用时发生错误: {str(e)}"
            LOGGER.error(content_message)
            return {"content": content_message}

    async def _handle_turn_intent(self, tool_input: llm.ToolInput):
        return await self.llm_api.async_call_tool(tool_input)

    async def _handle_get_state_intent(self, tool_input: llm.ToolInput):
        return await self.llm_api.async_call_tool(tool_input)

    async def _handle_set_position_intent(self, tool_input: llm.ToolInput):
        return await self.llm_api.async_call_tool(tool_input)

    async def _handle_light_set_intent(self, tool_input: llm.ToolInput):
        return await self.llm_api.async_call_tool(tool_input)

    async def _handle_climate_get_temperature_intent(self, tool_input: llm.ToolInput):
        return await self.llm_api.async_call_tool(tool_input)

    async def _handle_climate_intent(self, tool_input: llm.ToolInput):
        return await self.llm_api.async_call_tool(tool_input)

    async def _handle_shopping_list_add_item_intent(self, tool_input: llm.ToolInput):
        return await self.llm_api.async_call_tool(tool_input)

    async def _handle_get_weather_intent(self, tool_input: llm.ToolInput):
        return await self.llm_api.async_call_tool(tool_input)

    async def _handle_list_add_item_intent(self, tool_input: llm.ToolInput):
        return await self.llm_api.async_call_tool(tool_input)

    async def _handle_vacuum_intent(self, tool_input: llm.ToolInput):
        return await self.llm_api.async_call_tool(tool_input)

    async def _handle_media_intent(self, tool_input: llm.ToolInput):
        return await self.llm_api.async_call_tool(tool_input)

    async def _handle_set_volume_intent(self, tool_input: llm.ToolInput):
        return await self.llm_api.async_call_tool(tool_input)

    async def _handle_timer_intent(self, tool_input: llm.ToolInput):
        return await self.llm_api.async_call_tool(tool_input)

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
    entity = ZhipuAIConversationEntity(config_entry, hass)
    async_add_entities([entity])
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = entity

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, ["conversation"]):
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
