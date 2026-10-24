"""Number Component."""

import logging

from homeassistant.components.number import NumberEntity

from . import CrestronEntity
from .const import DOMAIN, ENTITIES_TO_EXPOSE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Crestron Number platform."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = [
        CrestronNumber(
            coordinator,
            entity["name"],
            entity["value_path"],
            entity["native_min_value"],
            entity["native_max_value"],
            entity["name"].replace(" ", "_").lower(),
            config_entry,
            entity.get("icon"),
            entity.get("device_class"),
            entity.get("native_unit_of_measurement"),
        )
        for entity in ENTITIES_TO_EXPOSE
        if entity["type"] == "number"
    ]
    async_add_entities(entities)


class CrestronNumber(CrestronEntity, NumberEntity):
    """Representation of a Crestron Number entity."""

    def __init__(
        self,
        coordinator,
        name,
        value_path,
        native_min_value,
        native_max_value,
        entity_id,
        config_entry,
        icon,
        device_class,
        native_unit_of_measurement,
    ):
        """Initialize the CrestronNumber entity."""
        super().__init__(
            coordinator,
            name,
            value_path,
            entity_id,
            config_entry,
            icon=icon,
            device_class=device_class,
        )
        self._attr_name = name
        self._entity_id = entity_id
        self._value_path = value_path

        # Assign the min and max values specific to CrestronNumber
        self._attr_native_min_value = native_min_value
        self._attr_native_max_value = native_max_value
        if native_unit_of_measurement is not None:
            self._attr_native_unit_of_measurement = native_unit_of_measurement

    @property
    def unique_id(self):
        """Return a unique ID for the entity."""
        return f"{self._entity_id}_{self._attr_name}"

    @property
    def name(self):
        """Return the name of the entity."""
        return self._attr_name

    @property
    def native_value(self):
        """Docstring."""
        extracted_value = self._extract_value()
        return float(extracted_value) if extracted_value is not None else None

    @property
    def native_min_value(self):
        """Docstring."""
        return self._attr_native_min_value

    @property
    def native_max_value(self):
        """Docstring."""
        return self._attr_native_max_value

    async def async_set_native_value(self, native_value: float) -> None:
        """Docstring."""
        payload = self._create_payload(native_value)
        _LOGGER.debug(
            "Setting native_value for %s to %s", self._attr_name, native_value
        )
        response_data = await self.coordinator.async_post_api("/Device", payload)
        _LOGGER.debug("Set native_value response: %s", response_data)

    def _create_payload(self, native_value: float):
        payload = {}
        current_native_value = payload
        for key in self.value_path:
            current_native_value[key] = {}
            previous_native_value = current_native_value
            current_native_value = current_native_value[key]
        previous_native_value[self.value_path[-1]] = native_value
        return payload
