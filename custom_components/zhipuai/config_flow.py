from __future__ import annotations

from typing import Any
from types import MappingProxyType

import voluptuous as vol
import aiohttp
import json

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

from . import LOGGER
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
)

RECOMMENDED_CHAT_MODEL = "GLM-4-Flash"

ZHIPUAI_MODELS = [
    "GLM-4-Plus",
    "GLM-4V-Plus",
    "GLM-4-0520",
    "GLM-4-Long",
    "GLM-4-AirX",
    "GLM-4-Air",
    "GLM-4-FlashX",
    "GLM-4-Flash",
    "GLM-4V",
    "GLM-4-AllTools",
    "GLM-4",
]

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_API_KEY): cv.string,
    }
)

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

ERROR_COOLDOWN_TOO_SMALL = "cooldown_too_small"
ERROR_COOLDOWN_TOO_LARGE = "cooldown_too_large"
ERROR_INVALID_OPTION = "invalid_option"

class ZhipuAIConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 0

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors = {}

        if user_input is not None:
            try:
                await self._validate_api_key(user_input[CONF_API_KEY])
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                    options=RECOMMENDED_OPTIONS,
                )
            except UnauthorizedError as e:
                errors["base"] = "unauthorized"
                LOGGER.error("无效的API密钥: %s", str(e))
            except ModelNotFound as e:
                errors["base"] = "model_not_found"
                LOGGER.error("模型未找到: %s", str(e))
            except Exception as e:
                errors["base"] = "unknown"
                LOGGER.exception("发生意外异常: %s", str(e))

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
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
                        raise UnauthorizedError("未经授权的访问")
                    else:
                        response_json = await response.json()
                        error = response_json.get("error", {})
                        error_message = error.get("message", "未知错误")
                        if "model not found" in error_message.lower():
                            raise ModelNotFound(f"模型未找到: {RECOMMENDED_CHAT_MODEL}")
                        else:
                            raise InvalidAPIKey(f"API请求失败: {error_message}")
            except aiohttp.ClientError as e:
                raise InvalidAPIKey(f"无法连接到智谱AI API: {str(e)}")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> ZhipuAIOptionsFlow:
        return ZhipuAIOptionsFlow(config_entry)

class ZhipuAIOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            try:
                LOGGER.debug("Received user input for options: %s", user_input)
                
                cooldown_period = user_input.get(CONF_COOLDOWN_PERIOD)
                if cooldown_period is not None:
                    cooldown_period = float(cooldown_period)
                    if cooldown_period < 0:
                        errors[CONF_COOLDOWN_PERIOD] = ERROR_COOLDOWN_TOO_SMALL
                    elif cooldown_period > 10:
                        errors[CONF_COOLDOWN_PERIOD] = ERROR_COOLDOWN_TOO_LARGE

                if not errors:
                    LOGGER.debug("更新选项: %s", user_input)
                    new_options = self.config_entry.options.copy()
                    new_options.update(user_input)
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        options=new_options
                    )
                    LOGGER.info("Successfully updated options for entry: %s", self.config_entry.entry_id)
                    return self.async_create_entry(title="", data=new_options)
            except vol.Invalid as ex:
                LOGGER.error("Validation error: %s", ex)
                errors["base"] = ERROR_INVALID_OPTION
            except ValueError as ex:
                LOGGER.error("Value error: %s", ex)
                errors["base"] = ERROR_INVALID_OPTION
            except Exception as ex:
                LOGGER.exception("意外错误更新选项: %s", ex)
                errors["base"] = "unknown"
        
        LOGGER.debug("Showing options form with errors: %s", errors)
        schema = zhipuai_config_option_schema(self.hass, self.config_entry.options)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

def zhipuai_config_option_schema(
    hass: HomeAssistant,
    options: dict[str, Any] | MappingProxyType[str, Any],
) -> dict:
    hass_apis: list[SelectOptionDict] = [
        SelectOptionDict(
            label="No",
            value="none",
        )
    ]
    hass_apis.extend(
        SelectOptionDict(
            label=api.name,
            value=api.id,
        )
        for api in llm.async_get_apis(hass)
    )

    schema = {
        vol.Optional(
            CONF_PROMPT,
            description={
                "suggested_value": options.get(
                    CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT
                )
            },
        ): TemplateSelector(),
        vol.Optional(
            CONF_LLM_HASS_API,
            description={"suggested_value": options.get(CONF_LLM_HASS_API)},
            default="none",
        ): SelectSelector(SelectSelectorConfig(options=hass_apis)),
        vol.Required(
            CONF_RECOMMENDED, default=options.get(CONF_RECOMMENDED, False)
        ): bool,
        vol.Optional(
            CONF_MAX_HISTORY_MESSAGES,
            description={"suggested_value": options.get(CONF_MAX_HISTORY_MESSAGES)},
            default=RECOMMENDED_MAX_HISTORY_MESSAGES,
        ): int,
        vol.Optional(
            CONF_CHAT_MODEL,
            description={"suggested_value": options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL)},
            default=RECOMMENDED_CHAT_MODEL,
        ): SelectSelector(SelectSelectorConfig(options=ZHIPUAI_MODELS)),
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