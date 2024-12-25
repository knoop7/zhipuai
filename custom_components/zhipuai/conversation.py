import json
import asyncio
import time
import re
from typing import Any, Literal, TypedDict, Dict, Optional
from voluptuous_openapi import convert
import voluptuous as vol
from homeassistant.components import assist_pipeline, conversation
from homeassistant.components.conversation import trace
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, MATCH_ALL, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr, intent, llm, template, entity_registry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.exceptions import HomeAssistantError
from .ai_request import send_ai_request
from homeassistant.util import ulid
from rapidfuzz import fuzz
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

def is_service_call(user_input: str) -> bool:
    if not user_input:
        return False
    keywords = ["调用", "执行", "脚本", "自动化"]
    return any(user_input.startswith(keyword) for keyword in keywords)

def extract_service_info(user_input: str, hass: HomeAssistant) -> Dict[str, Any]:
    if not is_service_call(user_input):
        return None
        
    for keyword in ["调用", "执行", "脚本", "自动化"]:
        if user_input.startswith(keyword):
            name = user_input.replace(keyword, "").strip()
            break
    
    for entity_id in hass.states.async_entity_ids("automation"):
        state = hass.states.get(entity_id)
        if not state:
            continue
        friendly_name = state.attributes.get("friendly_name", "")
        if friendly_name and name == friendly_name:
            return {
                "domain": "automation",
                "service": "trigger",
                "data": {"entity_id": entity_id}
            }
    
    for entity_id in hass.states.async_entity_ids("script"):
        state = hass.states.get(entity_id)
        if not state:
            continue
        friendly_name = state.attributes.get("friendly_name", "")
        if friendly_name and name == friendly_name:
            return {
                "domain": "script",
                "service": "turn_on",
                "data": {"entity_id": entity_id}
            }
    
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
        self.entity_registry = er.async_get(hass)
        self.device_registry = dr.async_get(hass)
        self.service_call_attempts = 0

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
            intent_response.async_set_error(intent.IntentResponseErrorCode.UNKNOWN, f"获取 LLM API 时出错，将继续使用基本功能：{err}")

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
                        return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)
                    except Exception as e:
                        intent_response.async_set_error(
                            conversation.IntentResponseErrorCode.UNKNOWN,
                            f"执行服务失败：{str(e)}"
                        )
                        return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)

            filtered_content = self._filter_response_content(final_content)

            self.history[conversation_id] = messages
            intent_response.async_set_speech(filtered_content)
            return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)

        except Exception as err:
            return await self._fallback_to_hass_llm(user_input, conversation_id)

    async def _handle_tool_call(self, tool_input: llm.ToolInput, user_input: str) -> Dict[str, Any]:
        try:
            if is_service_call(user_input):
                service_info = extract_service_info(user_input, self.hass)
                if service_info:
                    entity_id = service_info["data"]["entity_id"]
                    
                    
                    if entity_id not in self.hass.states.async_entity_ids():
                        return {"error": f"找不到实体: {entity_id}"}
                    
                    
                    state = self.hass.states.get(entity_id)
                    if not state:
                        return {"error": f"实体不可用: {entity_id}"}
                    
                    
                    supported_features = state.attributes.get("supported_features", 0)
                    
                    
                    domain = service_info["domain"]
                    service = service_info["service"]
                    
                    if domain == "fan":
                        if service == "set_percentage" and not (supported_features & 1):  
                            return {"error": f"风扇 {entity_id} 不支持调速功能"}
                    elif domain == "cover":
                        if service == "close" and not (supported_features & 2):  
                            return {"error": f"窗帘/门 {entity_id} 不支持关闭功能"}
                        elif service == "set_position" and not (supported_features & 4):  
                            return {"error": f"窗帘/门 {entity_id} 不支持设置位置"}
                    
                    try:
                        
                        self.hass.services.call(
                            domain,
                            service,
                            service_info["data"],
                            blocking=False,
                            target={"entity_id": entity_id}
                        )
                        return {
                            "success": True,
                            "message": f"已发送 {domain}.{service} 命令到 {entity_id}"
                        }
                    except Exception as e:
                        error_msg = str(e)
                        if "does not support this service" in error_msg:
                            return {"error": f"实体 {entity_id} 不支持该操作"}
                        elif "not currently available" in error_msg:
                            return {"error": f"实体 {entity_id} 当前不可用"}
                        else:
                            return {"error": f"执行服务失败：{error_msg}"}
                else:
                    return {"error": "无法解析服务调用信息"}
            
            if self.llm_api and hasattr(self.llm_api, "async_call_tool"):
                try:
                    result = await self.llm_api.async_call_tool(tool_input)
                    if isinstance(result, dict) and "error" in result:
                        return {"error": f"LLM API调用出错: {result['error']}"}
                    return result
                except Exception as e:
                    return {"error": f"LLM API调用失败: {str(e)}"}
            return {"error": "无法处理该工具调用"}
        
        except Exception as e:
            return {"error": f"处理工具调用时发生错误: {str(e)}"}

    def _handle_home_assistant_error(self, error: HomeAssistantError) -> Dict[str, str]:
        content_message = str(error)
        if "Domain not supported" in content_message:
            return {"error": f"不支持的设备类型: {content_message.split(':')[-1].strip()}"}
        elif "MatchFailedError" in content_message:
            return {"error": "未找到匹配的设备。请检查设备名称是否正确，或尝试使用更具体的名称。"}
        elif "not currently available" in content_message:
            return {"error": "设备当前不可用，请检查设备是否在线或已配置。"}
        elif "does not support this service" in content_message:
            return {"error": "设备不支持该操作，请检查设备支持的功能。"}
        else:
            return {"error": f"处理意图时出错: {content_message}"}

    async def _extract_entity(self, domain: str, name: Optional[str] = None) -> Optional[str]:
        entities = self.entity_registry.entities
        if name and isinstance(name, str):
            best_match = None
            highest_ratio = 0
            for entity_id, entity in entities.items():
                if entity.domain == domain:
                    ratio = fuzz.ratio(name.lower(), entity.name.lower())
                    if ratio > highest_ratio:
                        highest_ratio = ratio
                        best_match = entity_id
            if best_match and highest_ratio > 85: 
                return best_match
        for entity_id, entity in entities.items():
            if entity.domain == domain:
                return entity_id
        return None


    async def _fallback_to_hass_llm(self, user_input: conversation.ConversationInput, conversation_id: str) -> conversation.ConversationResult:
        try:
            agent = await conversation.async_get_agent(self.hass)
            result = await agent.async_process(user_input)
            return result
        except Exception as err:
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"很抱歉，我现在无法正确处理您的请求。请稍后再试。错误: {err}"
            )
            return conversation.ConversationResult(response=intent_response, conversation_id=conversation_id)

    async def _validate_service_for_entity(self, domain: str, service: str, entity_id: str) -> bool:
        
        try:
            service_details = self.hass.services.async_services().get(domain, {}).get(service)
            if not service_details:
                return False
            
            entity = self.hass.states.get(entity_id)
            if not entity:
                return False

            return True
        except Exception as e:
            return False

    async def _handle_turn_intent(self, tool_input: llm.ToolInput) -> Dict[str, Any]:
        try:
            entity_id = await self._extract_entity(tool_input.tool_args["domain"], tool_input.tool_args.get("name"))
            if not entity_id:
                return {"error": f"未找到匹配的 {tool_input.tool_args['domain']} 设备"}
            
            state = tool_input.tool_args["state"]
            service = f"turn_{state}"
            
            if not await self._validate_service_for_entity(tool_input.tool_args["domain"], service, entity_id):
                return {"error": f"实体 {entity_id} 不支持 {service} 服务"}
            
            await self.hass.services.async_call(
                tool_input.tool_args["domain"], service, {ATTR_ENTITY_ID: entity_id}
            )
            return {"success": True, "message": f"已将 {entity_id} 设置为 {state}"}
        except Exception as e:
            return {"error": f"执行 turn 意图时出错: {str(e)}"}

    async def _handle_get_state_intent(self, tool_input: llm.ToolInput) -> Dict[str, Any]:
        try:
            entity_id = await self._extract_entity(tool_input.tool_args["domain"], tool_input.tool_args.get("name"))
            if not entity_id:
                return {"error": f"未找到匹配的 {tool_input.tool_args['domain']} 设备"}
            
            state = self.hass.states.get(entity_id)
            if state:
                return {"success": True, "state": state.state, "attributes": state.attributes}
            else:
                return {"error": f"无法获取 {entity_id} 的状态"}
        except Exception as e:
            return {"error": f"执行 get_state 意图时出错: {str(e)}"}

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
