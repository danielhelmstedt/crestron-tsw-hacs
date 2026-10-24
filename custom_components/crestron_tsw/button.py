"""Button Component."""

import logging

from homeassistant.components.button import ButtonEntity

from . import CrestronEntity
from .const import DOMAIN, ENTITIES_TO_EXPOSE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Crestron button platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
        CrestronButton(
            coordinator,
            entity["name"],
            entity["value_path"],
            entity["name"].replace(" ", "_").lower(),
            config_entry,
            entity.get("icon"),
        )
        for entity in ENTITIES_TO_EXPOSE
        if entity["type"] == "button"
    ]
    async_add_entities(entities)


class CrestronButton(CrestronEntity, ButtonEntity):
    """Representation of a Crestron momentary Button."""

    def __init__(self, coordinator, name, value_path, entity_id, config_entry, icon):
        """Initialize the CrestronButton entity."""
        super().__init__(
            coordinator, name, value_path, entity_id, config_entry, icon=icon
        )
        self._attr_name = name
        self._entity_id = entity_id
        self._value_path = value_path

    @property
    def unique_id(self):
        """Return a unique ID for the button entity."""
        return f"{self._entity_id}_{self._attr_name}"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Button %s pressed", self._attr_name)
        payload = self._create_payload(True)  # Momentary press
        await self.coordinator.async_post_api("/Device", payload, update_data=False)

    def _create_payload(self, state: bool):
        """Create the payload for the API request."""
        payload = {}
        current_level = payload
        for key in self.value_path[:-1]:
            current_level[key] = {}
            current_level = current_level[key]
        current_level[self.value_path[-1]] = state
        return payload
