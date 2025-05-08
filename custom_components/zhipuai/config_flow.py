from __future__ import annotations
from typing import Any
from types import MappingProxyType
import voluptuous as vol
import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant import exceptions
from homeassistant.const import CONF_API_KEY, CONF_NAME, CONF_LLM_HASS_API
from homeassistant.helpers import llm
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TemplateSelector,
)

from .const import (
    CONF_PROMPT,
    CONF_TEMPERATURE,
    DEFAULT_NAME,
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_RECOMMENDED,
    CONF_TOP_P,
    CONF_MAX_HISTORY_MESSAGES,
    DOMAIN,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TOP_P,
    RECOMMENDED_MAX_HISTORY_MESSAGES,
    CONF_MAX_TOOL_ITERATIONS,
    DEFAULT_MAX_TOOL_ITERATIONS,
    CONF_WEB_SEARCH,
    DEFAULT_WEB_SEARCH,
    CONF_HISTORY_ANALYSIS,
    CONF_HISTORY_ENTITIES,
    CONF_HISTORY_DAYS,
    DEFAULT_HISTORY_ANALYSIS,
    DEFAULT_HISTORY_DAYS,
    MAX_HISTORY_DAYS,
    CONF_HISTORY_INTERVAL,
    DEFAULT_HISTORY_INTERVAL,
    CONF_REQUEST_TIMEOUT,
    DEFAULT_REQUEST_TIMEOUT,
    CONF_PRESENCE_PENALTY,
    DEFAULT_PRESENCE_PENALTY,
    CONF_FREQUENCY_PENALTY,
    DEFAULT_FREQUENCY_PENALTY,
    CONF_STOP_SEQUENCES,
    DEFAULT_STOP_SEQUENCES,
    CONF_TOOL_CHOICE,
    DEFAULT_TOOL_CHOICE,
    CONF_FILTER_MARKDOWN,
    DEFAULT_FILTER_MARKDOWN,
    CONF_NOTIFY_SERVICE,
    DEFAULT_NOTIFY_SERVICE,
)


ZHIPUAI_MODELS = [
    "GLM-4-Plus",
    "GLM-4-0520",
    "GLM-4-Long",
    "glm-zero-preview",
    "GLM-Z1-Air",
    "GLM-Z1-AirX",
    "GLM-Z1-flash",
    "GLM-Z1-flashX-250414",
    "GLM-4-Flash",
    "glm-4-flash-250414",
    "glm-4-flashx-250414",
    "CharGLM-4",
    "GLM-4-Air",
    "GLM-4-AirX",
    "GLM-4-Air-250414",
    "GLM-4-AllTools",
    "GLM-4-Assistant",
    "GLM-4-CodeGeex-4"
]

RECOMMENDED_CHAT_MODEL = "glm-4-flash-250414"

RECOMMENDED_OPTIONS = {
    CONF_RECOMMENDED: True,
    CONF_LLM_HASS_API: llm.LLM_API_ASSIST,
    CONF_PROMPT: """您是 Home Assistant 的语音助手。
如实回答有关世界的问题。
以纯文本形式回答。保持简单明了。""",
    CONF_MAX_HISTORY_MESSAGES: RECOMMENDED_MAX_HISTORY_MESSAGES,
    CONF_CHAT_MODEL: RECOMMENDED_CHAT_MODEL,
    CONF_MAX_TOOL_ITERATIONS: DEFAULT_MAX_TOOL_ITERATIONS,
}

class ZhipuAIConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 0

    def __init__(self) -> None:
        self._reauth_entry: ConfigEntry | None = None
        self._reconfigure_entry: ConfigEntry | None = None

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                await self._validate_api_key(user_input[CONF_API_KEY])
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                    options=RECOMMENDED_OPTIONS,
                )
            except UnauthorizedError:
                errors["base"] = "invalid_auth"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except ModelNotFound:
                errors["base"] = "model_not_found"
            except Exception:
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=DEFAULT_NAME): cv.string,
                vol.Required(CONF_API_KEY): cv.string,
            }),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._reauth_entry = self._get_reauth_entry()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}

        if user_input is not None:
            try:
                await self._validate_api_key(user_input[CONF_API_KEY])
                assert self._reauth_entry is not None
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data_updates={CONF_API_KEY: user_input[CONF_API_KEY]},
                    reason="reauth_successful",
                )
            except UnauthorizedError:
                errors["base"] = "invalid_auth"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect" 
            except Exception:
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): cv.string,
            }),
            errors=errors,
        )

    async def async_step_reconfigure(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._reconfigure_entry = self._get_reconfigure_entry()
        return await self.async_step_reconfigure_confirm()

    async def async_step_reconfigure_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}

        if user_input is not None:
            try:
                await self._validate_api_key(user_input[CONF_API_KEY])
                assert self._reconfigure_entry is not None
                return self.async_update_reload_and_abort(
                    self._reconfigure_entry,
                    data_updates={CONF_API_KEY: user_input[CONF_API_KEY]},
                    reason="reconfigure_successful",
                )
            except UnauthorizedError:
                errors["base"] = "invalid_auth"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reconfigure_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): cv.string,
            }),
            errors=errors,
        )

    async def _validate_api_key(self, api_key: str) -> None:
        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        data = {
            "model": RECOMMENDED_CHAT_MODEL,
            "messages": [{"role": "user", "content": "你好"}]
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        return
                    elif response.status == 401:
                        raise UnauthorizedError()
                    else:
                        response_json = await response.json()
                        error = response_json.get("error", {})
                        error_message = error.get("message", "")
                        if "model not found" in error_message.lower():
                            raise ModelNotFound()
                        else:
                            raise InvalidAPIKey()
            except aiohttp.ClientError as e:
                raise

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ZhipuAIOptionsFlow:
        return ZhipuAIOptionsFlow(config_entry)


class ZhipuAIOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._data = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                self._data.update(user_input)  
                if user_input.get(CONF_HISTORY_ANALYSIS):
                    return await self.async_step_history()
                return self.async_create_entry(title="", data=self._data)
            except ValueError:
                errors["base"] = "invalid_option"

        schema = vol.Schema(zhipuai_config_option_schema(self.hass, self._config_entry.options))
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_history(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}
        current_options = self._config_entry.options
        
        if user_input is not None:
            try:
                days = user_input.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS)
                if days < 1 or days > MAX_HISTORY_DAYS:
                    errors[CONF_HISTORY_DAYS] = "invalid_days"
                if not user_input.get(CONF_HISTORY_ENTITIES):
                    errors[CONF_HISTORY_ENTITIES] = "no_entities"

                if not errors:
                    self._data.update(user_input)
                    return self.async_create_entry(title="", data=self._data)
            except ValueError:
                errors["base"] = "invalid_option"

        entities = {}
        for entity in self.hass.states.async_all():
            friendly_name = entity.attributes.get("friendly_name", entity.entity_id)
            entities[entity.entity_id] = f"{friendly_name} ({entity.entity_id})"

        return self.async_show_form(
            step_id="history",
            data_schema=vol.Schema({
                vol.Required(
                    CONF_HISTORY_ENTITIES,
                    default=current_options.get(CONF_HISTORY_ENTITIES, [])
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[{"value": k, "label": v} for k, v in entities.items()],
                        multiple=True,
                        mode="dropdown",
                        custom_value=False,
                    )
                ),
                vol.Optional(
                    CONF_HISTORY_INTERVAL,
                    default=current_options.get(CONF_HISTORY_INTERVAL, DEFAULT_HISTORY_INTERVAL),
                ): vol.Coerce(int),
                vol.Required(
                    CONF_HISTORY_DAYS,
                    default=current_options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS)
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=MAX_HISTORY_DAYS),
                ),
            }),
            errors=errors,
        )


def zhipuai_config_option_schema(
    hass: HomeAssistant,
    options: dict[str, Any] | MappingProxyType[str, Any],
) -> dict:
    hass_apis = [SelectOptionDict(label="No", value="none")]
    hass_apis.extend(
        SelectOptionDict(label=api.name, value=api.id)
        for api in llm.async_get_apis(hass)
    )

    notify_services = [SelectOptionDict(value="persistent_notification", label="全局通知 (notify.persistent_notification)")]
    
    for service_id in hass.services.async_services().get("notify", {}):
        if service_id != "persistent_notification":
            notify_services.append(SelectOptionDict(value=service_id, label=f"{service_id}"))
    
    schema = {
        vol.Optional(
            CONF_PROMPT,
            description={"suggested_value": options.get(CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT)},
        ): TemplateSelector(),
        vol.Optional(
            CONF_LLM_HASS_API,
            description={"suggested_value": options.get(CONF_LLM_HASS_API, llm.LLM_API_ASSIST)},
            default=llm.LLM_API_ASSIST,
        ): SelectSelector(SelectSelectorConfig(options=hass_apis)),
        vol.Required(
            CONF_RECOMMENDED,
            default=options.get(CONF_RECOMMENDED, False)
        ): bool,
        vol.Optional(
            CONF_CHAT_MODEL,
            description={"suggested_value": options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL)},
            default=RECOMMENDED_CHAT_MODEL,
        ): SelectSelector(SelectSelectorConfig(
            options=[
                SelectOptionDict(
                    value=model_id,
                    label=model_id
                )
                for model_id in ZHIPUAI_MODELS
            ],
            translation_key="model_descriptions"
        )),
        vol.Optional(
            CONF_FILTER_MARKDOWN,
            description={"suggested_value": options.get(CONF_FILTER_MARKDOWN, DEFAULT_FILTER_MARKDOWN)},
            default=DEFAULT_FILTER_MARKDOWN,
        ): SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value="off", label="filter_markdown.off"),
                    SelectOptionDict(value="on", label="filter_markdown.on")
                ],
                mode="dropdown",
                translation_key="filter_markdown"
            )
        ),
        vol.Optional(
            CONF_NOTIFY_SERVICE,
            description={"suggested_value": options.get(CONF_NOTIFY_SERVICE, DEFAULT_NOTIFY_SERVICE)},
            default=DEFAULT_NOTIFY_SERVICE,
        ): SelectSelector(
            SelectSelectorConfig(
                options=notify_services,
                mode="dropdown",
                translation_key="notify_service"
            )
        ),
        vol.Optional(
            CONF_MAX_HISTORY_MESSAGES,
            description={"suggested_value": options.get(CONF_MAX_HISTORY_MESSAGES)},
            default=RECOMMENDED_MAX_HISTORY_MESSAGES,
        ): int,
        vol.Optional(
            CONF_MAX_TOOL_ITERATIONS,
            description={"suggested_value": options.get(CONF_MAX_TOOL_ITERATIONS, DEFAULT_MAX_TOOL_ITERATIONS)},
            default=DEFAULT_MAX_TOOL_ITERATIONS,
        ): int,
        vol.Optional(
            CONF_REQUEST_TIMEOUT,
            description={"suggested_value": options.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT)},
            default=DEFAULT_REQUEST_TIMEOUT,
        ): vol.All(
            vol.Coerce(float),
            vol.Range(min=10, max=120),
            msg="超时时间必须在10到120秒之间"
        ),
        vol.Optional(
            CONF_WEB_SEARCH,
            default=options.get(CONF_WEB_SEARCH, DEFAULT_WEB_SEARCH),
            description={"suggested_value": options.get(CONF_WEB_SEARCH, DEFAULT_WEB_SEARCH)},
        ): bool,
        vol.Optional(
            CONF_HISTORY_ANALYSIS,
            default=options.get(CONF_HISTORY_ANALYSIS, DEFAULT_HISTORY_ANALYSIS),
            description={"suggested_value": options.get(CONF_HISTORY_ANALYSIS, DEFAULT_HISTORY_ANALYSIS)},
        ): bool,
    }

    if not options.get(CONF_RECOMMENDED, False):
        schema.update({
            vol.Optional(
                CONF_MAX_TOKENS,
                description={"suggested_value": options.get(CONF_MAX_TOKENS)},
                default=RECOMMENDED_MAX_TOKENS,
            ): int,
            vol.Optional(
                CONF_TOP_P,
                description={"suggested_value": options.get(CONF_TOP_P)},
                default=RECOMMENDED_TOP_P,
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.0,
                    max=1.0,
                    step=0.1,
                    mode="box",
                )
            ),
            vol.Optional(
                CONF_TEMPERATURE,
                description={"suggested_value": options.get(CONF_TEMPERATURE)},
                default=RECOMMENDED_TEMPERATURE,
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.0,
                    max=2.0,
                    step=0.1,
                    mode="box",
                )
            ),
            vol.Optional(
                CONF_PRESENCE_PENALTY,
                description={"suggested_value": options.get(CONF_PRESENCE_PENALTY, DEFAULT_PRESENCE_PENALTY)},
                default=DEFAULT_PRESENCE_PENALTY,
            ): NumberSelector(
                NumberSelectorConfig(
                    min=-2.0,
                    max=2.0,
                    step=0.1,
                    mode="box",
                )
            ),
            vol.Optional(
                CONF_FREQUENCY_PENALTY,
                description={"suggested_value": options.get(CONF_FREQUENCY_PENALTY, DEFAULT_FREQUENCY_PENALTY)},
                default=DEFAULT_FREQUENCY_PENALTY,
            ): NumberSelector(
                NumberSelectorConfig(
                    min=-2.0,
                    max=2.0,
                    step=0.1,
                    mode="box",
                )
            ),
            vol.Optional(
                CONF_STOP_SEQUENCES,
                description={"suggested_value": options.get(CONF_STOP_SEQUENCES, DEFAULT_STOP_SEQUENCES)},
                default=DEFAULT_STOP_SEQUENCES,
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value="\\n", label="stop_sequences.\\n"),
                        SelectOptionDict(value="。", label="stop_sequences.。"),
                        SelectOptionDict(value="！", label="stop_sequences.！"),
                        SelectOptionDict(value="？", label="stop_sequences.？"),
                        SelectOptionDict(value="；", label="stop_sequences.；"),
                        SelectOptionDict(value="：", label="stop_sequences.："),
                        SelectOptionDict(value=",", label="stop_sequences.,"),
                        SelectOptionDict(value=".", label="stop_sequences..")
                    ],
                    multiple=True,
                    mode="dropdown",
                    translation_key="stop_sequences"
                )
            ),
            vol.Optional(
                CONF_TOOL_CHOICE,
                description={"suggested_value": options.get(CONF_TOOL_CHOICE, DEFAULT_TOOL_CHOICE)},
                default=DEFAULT_TOOL_CHOICE,
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value="auto", label="tool_choice.auto"),
                        SelectOptionDict(value="none", label="tool_choice.none"),
                        SelectOptionDict(value="force", label="tool_choice.force")
                    ],
                    mode="dropdown",
                    translation_key="tool_choice"
                )
            ),
        })

    return schema

class UnknownError(exceptions.HomeAssistantError):
    pass

class UnauthorizedError(exceptions.HomeAssistantError):
    pass

class InvalidAPIKey(exceptions.HomeAssistantError):
    pass

class ModelNotFound(exceptions.HomeAssistantError):
    pass
