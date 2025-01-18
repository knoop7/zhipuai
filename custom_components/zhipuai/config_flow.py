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
    CONF_COOLDOWN_PERIOD,
    DEFAULT_MAX_TOOL_ITERATIONS,
    DEFAULT_COOLDOWN_PERIOD,
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
)

ZHIPUAI_MODELS = [
    "GLM-4-Plus",
    "glm-zero-preview",
    "web-search-pro",
    "GLM-4-0520",
    "GLM-4V",
    "GLM-4-Long",
    "GLM-4-Flash",
    "GLM-4-FlashX",
    "GLM-4-9B",
    "GLM-4-Air", 
    "GLM-4-AirX",
    "GLM-4-AllTools",
    "glm-4-Air-0111",
    "GLM-4",
    "GLM-4-CodeGeex-4",
]

RECOMMENDED_CHAT_MODEL = "GLM-4-Flash"

RECOMMENDED_OPTIONS = {
    CONF_RECOMMENDED: True,
    CONF_LLM_HASS_API: llm.LLM_API_ASSIST,
    CONF_PROMPT: """您是 Home Assistant 的语音助手。
如实回答有关世界的问题。
以纯文本形式回答。保持简单明了。""",
    CONF_MAX_HISTORY_MESSAGES: RECOMMENDED_MAX_HISTORY_MESSAGES,
    CONF_CHAT_MODEL: RECOMMENDED_CHAT_MODEL,
    CONF_MAX_TOOL_ITERATIONS: DEFAULT_MAX_TOOL_ITERATIONS,
    CONF_COOLDOWN_PERIOD: DEFAULT_COOLDOWN_PERIOD,
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
                cooldown_period = user_input.get(CONF_COOLDOWN_PERIOD)
                if cooldown_period is not None:
                    cooldown_period = float(cooldown_period)
                    if cooldown_period < 0:
                        errors[CONF_COOLDOWN_PERIOD] = "cooldown_too_small"
                    elif cooldown_period > 10:
                        errors[CONF_COOLDOWN_PERIOD] = "cooldown_too_large"

                if not errors:
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

    schema = {
        vol.Optional(
            CONF_PROMPT,
            description={"suggested_value": options.get(CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT)},
        ): TemplateSelector(),
        vol.Optional(
            CONF_LLM_HASS_API,
            description={"suggested_value": options.get(CONF_LLM_HASS_API)},
            default="none",
        ): SelectSelector(SelectSelectorConfig(options=hass_apis)),
        vol.Required(
            CONF_RECOMMENDED,
            default=options.get(CONF_RECOMMENDED, False)
        ): bool,
        vol.Optional(
            CONF_CHAT_MODEL,
            description={"suggested_value": options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL)},
            default=RECOMMENDED_CHAT_MODEL,
        ): SelectSelector(SelectSelectorConfig(options=ZHIPUAI_MODELS)),
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
            CONF_COOLDOWN_PERIOD,
            description={"suggested_value": options.get(CONF_COOLDOWN_PERIOD, DEFAULT_COOLDOWN_PERIOD)},
            default=DEFAULT_COOLDOWN_PERIOD,
        ): vol.All(
            vol.Coerce(float),
            vol.Range(min=0, max=10),
            msg="冷却时间必须在0到10秒之间"
        ),
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
            default=DEFAULT_WEB_SEARCH,
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
            ): NumberSelector(NumberSelectorConfig(min=0, max=1, step=0.05)),
            vol.Optional(
                CONF_TEMPERATURE,
                description={"suggested_value": options.get(CONF_TEMPERATURE)},
                default=RECOMMENDED_TEMPERATURE,
            ): NumberSelector(NumberSelectorConfig(min=0, max=2, step=0.05)),
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