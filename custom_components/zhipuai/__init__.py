from __future__ import annotations
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import DOMAIN, LOGGER
from .service_caller import get_service_caller

PLATFORMS: list[Platform] = [Platform.CONVERSATION]

class ZhipuAIConfigEntry:
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self.config_entry = config_entry
        self.api_key = config_entry.data[CONF_API_KEY]
        self.options = config_entry.options
        self._unsub_options_update_listener = None
        self._cleanup_callbacks = []
        self.service_caller = get_service_caller(hass)

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
    hass.data.setdefault(DOMAIN, {})
    try:
        zhipuai_entry = ZhipuAIConfigEntry(hass, entry)
        await zhipuai_entry.async_setup()
        hass.data[DOMAIN][entry.entry_id] = zhipuai_entry
        LOGGER.info("成功设置, 条目 ID: %s", entry.entry_id)
    except Exception as ex:
        LOGGER.error("设置 AI 时出错: %s", ex)
        raise ConfigEntryNotReady from ex

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    zhipuai_entry = hass.data[DOMAIN].get(entry.entry_id)
    if zhipuai_entry is None:
        return True

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await zhipuai_entry.async_unload()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        LOGGER.info("已卸载 AI 条目，ID: %s", entry.entry_id)

    return unload_ok
