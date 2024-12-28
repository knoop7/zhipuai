from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import DOMAIN, LOGGER
from .intents import get_intent_handler, async_setup_intents
from .services import async_setup_services
from .web_search import async_setup_web_search
from .image_gen import async_setup_image_gen

PLATFORMS: list[Platform] = [Platform.CONVERSATION]

class ZhipuAIConfigEntry:
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self.config_entry = config_entry
        self.api_key = config_entry.data[CONF_API_KEY]
        self.options = config_entry.options
        self._unsub_options_update_listener = None
        self._cleanup_callbacks = []
        self.intent_handler = get_intent_handler(hass)

    @property
    def entry_id(self):
        return self.config_entry.entry_id

    @property
    def title(self):
        return self.config_entry.title

    async def async_setup(self) -> None:
        self._unsub_options_update_listener = self.config_entry.add_update_listener(
            self.async_options_updated
        )

    async def async_unload(self) -> None:
        if self._unsub_options_update_listener is not None:
            self._unsub_options_update_listener()
            self._unsub_options_update_listener = None
        for cleanup_callback in self._cleanup_callbacks:
            cleanup_callback()
        self._cleanup_callbacks.clear()

    def async_on_unload(self, func):
        self._cleanup_callbacks.append(func)

    @callback
    async def async_options_updated(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.options = entry.options
        async_dispatcher_send(hass, f"{DOMAIN}_options_updated", entry)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        zhipuai_entry = ZhipuAIConfigEntry(hass, entry)
        await zhipuai_entry.async_setup()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = zhipuai_entry
        
        unload_services = await async_setup_services(hass)
        zhipuai_entry.async_on_unload(unload_services)
        
        await async_setup_intents(hass)
        
        await async_setup_web_search(hass)
        await async_setup_image_gen(hass)
        
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True
        
    except Exception as ex:
        raise ConfigEntryNotReady from ex

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    try:
        zhipuai_entry = hass.data[DOMAIN].get(entry.entry_id)
        if zhipuai_entry is not None and hasattr(zhipuai_entry, 'async_unload'):
            await zhipuai_entry.async_unload()
    except Exception:
        pass
    finally:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok