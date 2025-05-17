from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN

PROCESS_WITH_HA_SCHEMA = vol.Schema({
    vol.Required("text"): cv.string,
    vol.Optional("language", default="zh-cn"): cv.string,
    vol.Optional("fallback_agent"): cv.entity_id
})

async def async_setup(hass: HomeAssistant) -> bool:
    async def process_with_home_assistant(call: ServiceCall):
        result = await hass.services.async_call(
            "conversation",
            "process",
            {
                "text": call.data.get("text"),
                "agent_id": "conversation.home_assistant",
                "language": call.data.get("language")
            },
            blocking=True,
            return_response=True
        )
        
        if (result and isinstance(result, dict) and 
            result.get("response", {}).get("response_type") == "error"):
            fallback_agent = call.data.get("fallback_agent")
            if fallback_agent:
                result = await hass.services.async_call(
                    "conversation",
                    "process",
                    {
                        "text": call.data.get("text"),
                        "agent_id": fallback_agent,
                        "language": call.data.get("language")
                    },
                    blocking=True,
                    return_response=True
                )
        return result

    hass.services.async_register(
        DOMAIN,
        "process_with_ha",
        process_with_home_assistant,
        schema=PROCESS_WITH_HA_SCHEMA,
        supports_response=True
    )
    return True
