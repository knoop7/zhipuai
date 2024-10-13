import aiohttp
import json
import asyncio
import time
from typing import Any, Literal, TypedDict
from voluptuous_openapi import convert
import voluptuous as vol
from aiohttp import TCPConnector
from homeassistant.components import assist_pipeline, conversation
from homeassistant.components.conversation import trace
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, TemplateError
from homeassistant.helpers import device_registry as dr, intent, llm, template, entity_registry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
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
)

ZHIPUAI_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

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

    async def async_process(self, user_input: conversation.ConversationInput) -> conversation.ConversationResult:
        current_time = time.time()
        if current_time - self.last_request_time < self.cooldown_period:
            await asyncio.sleep(self.cooldown_period - (current_time - self.last_request_time))
        self.last_request_time = time.time()

        options = self.entry.options
        intent_response = intent.IntentResponse(language=user_input.language)
        llm_api: llm.APIInstance | None = None
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

        if options.get(CONF_LLM_HASS_API) and options[CONF_LLM_HASS_API] != "none":
            try:
                llm_api = await llm.async_get_api(self.hass, options[CONF_LLM_HASS_API], llm_context)
                tools = [_format_tool(tool, llm_api.custom_serializer) for tool in llm_api.tools][:8]  
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
            intent_response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, f"抱歉，我的模板有问题： {err}")
            return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)

        if llm_api:
            prompt_parts.append(llm_api.api_prompt)

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
            {"messages": messages, "tools": llm_api.tools if llm_api else None},
        )

        api_key = self.entry.data[CONF_API_KEY]
        try:
            connector = TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                for _iteration in range(self.max_tool_iterations):
                    try:
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

                        headers = {
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        }

                        async with session.post(ZHIPUAI_URL, json=payload, headers=headers) as response:
                            if response.status != 200:
                                raise HomeAssistantError(f"AI 返回状态 {response.status}")
                            result = await response.json()
                    except Exception as err:
                        raise HomeAssistantError(f"与 AI 通信时出错: {err}")

                    LOGGER.debug("AI 响应: %s", result)
                    response = result["choices"][0]["message"]

                    if "HassTurn" in response.get("content", "您好，请再试一次哦～"):
                        continue  

                    messages.append(response)
                    tool_calls = response.get("tool_calls")

                    if not tool_calls or not llm_api:
                        break

                    for tool_call in tool_calls:
                        try:
                            tool_input = llm.ToolInput(
                                tool_name=tool_call["function"]["name"],
                                tool_args=json.loads(tool_call["function"]["arguments"]),
                            )
                            tool_response = await llm_api.async_call_tool(tool_input)
                            messages.append(
                                ChatCompletionMessageParam(
                                    role="tool",
                                    tool_call_id=tool_call["id"],
                                    content=json.dumps(tool_response),
                                )
                            )
                        except Exception as e:
                            LOGGER.error("工具调用失败: %s", e)

        except Exception as err:
            LOGGER.error("处理 AI 请求时出错: %s", err)
            intent_response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, f"处理请求时出错: {err}")
            return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)

        self.history[conversation_id] = messages
        intent_response.async_set_speech(response.get("content"))
        return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)

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
    entity = ZhipuAIConversationEntity(config_entry)
    async_add_entities([entity])
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = entity

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, ["conversation"]):
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok