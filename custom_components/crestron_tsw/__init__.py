"""Crestron TSW-Series integration for Home Assistant."""

import logging

import aiohttp

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import (
    async_create_clientsession,
    async_get_clientsession,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_USE_WEBSOCKET, DOMAIN, PLATFORMS
from .coordinator import CrestronDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Crestron TSW-Series Panel from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    username = config_entry.data.get(CONF_USERNAME)
    session = (
        async_create_clientsession(
            hass,
            verify_ssl=False,
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        )
        if username
        else async_get_clientsession(hass)
    )
    coordinator = CrestronDataUpdateCoordinator(
        hass,
        config_entry.data[CONF_HOST],
        config_entry.title,
        session,
        username,
        config_entry.data.get(CONF_PASSWORD),
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][config_entry.entry_id] = coordinator
    coordinator.async_start_illumination_poll()
    if config_entry.data.get(CONF_USE_WEBSOCKET, True):
        coordinator.async_start_websocket()
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(config_entry.entry_id)
        await coordinator.async_close()
    return unload_ok


class CrestronEntity(CoordinatorEntity):
    """Representation of a Crestron entity."""

    def __init__(
        self,
        coordinator: CrestronDataUpdateCoordinator,
        name: str,
        value_path: list,
        entity_id: str,
        config_entry: config_entries.ConfigEntry,
        *,
        icon: str | None = None,
        device_class=None,
    ):
        """Initialize the Crestron entity."""
        super().__init__(coordinator)
        self._attr_name = name
        self.value_path = value_path
        self._entity_id = entity_id
        self._attr_unique_id = f"{entity_id}_" + "_".join(value_path)
        if icon is not None:
            self._attr_icon = icon
        if device_class is not None:
            self._attr_device_class = device_class
        device_info = self.coordinator.data.get("Device", {}).get("DeviceInfo", {})
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self.coordinator.data.get("SerialNumber", ""))},
            "name": device_info.get("Name"),
            "manufacturer": device_info.get("Manufacturer"),
            "model": device_info.get("Model"),
            "serial_number": device_info.get("SerialNumber"),
            "sw_version": device_info.get("DeviceVersion"),
            "connections": {("mac", device_info.get("MacAddress"))},
        }

    @property
    def device_info(self):
        """Return device information about this entity."""
        return self._attr_device_info

    @property
    def available(self):
        """Return if the entity is available."""
        return self.coordinator.last_update_success

    def _extract_value(self):
        """Extract value from the API response."""
        value = self.coordinator.data
        if value is None:
            return None
        for key in self.value_path:
            value = value.get(key)
            if value is None:
                return None
        return value
