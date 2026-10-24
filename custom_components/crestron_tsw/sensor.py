"""Sensor platform for Crestron TSW panels."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CrestronEntity
from .const import DOMAIN, ENTITIES_TO_EXPOSE


async def async_setup_entry(
    hass, config_entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Crestron sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []
    for entity in ENTITIES_TO_EXPOSE:
        if entity["type"] != "sensor":
            continue
        if entity.get("requires_ssh") and not (
            coordinator.username and coordinator.password
        ):
            continue
        entity_name = entity["name"]
        entities.append(
            CrestronSensor(
                coordinator,
                entity_name,
                entity["value_path"],
                f"{entity_name.lower().replace(' ', '_')}",
                config_entry,
                entity.get("device_class"),
                entity.get("native_unit_of_measurement"),
                entity.get("state_class"),
                entity.get("icon"),
            )
        )
    async_add_entities(entities, update_before_add=True)


class CrestronSensor(CrestronEntity, SensorEntity):
    """Represenation of a Crestron Sensor entity."""

    def __init__(
        self,
        coordinator,
        name,
        value_path,
        entity_id,
        config_entry,
        device_class: SensorDeviceClass | None = None,
        native_unit_of_measurement: str | None = None,
        state_class: SensorStateClass | None = None,
        icon: str | None = None,
    ):
        """Initialize a Crestron sensor."""
        super().__init__(coordinator, name, value_path, entity_id, config_entry)
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = native_unit_of_measurement
        self._attr_state_class = state_class
        if icon is not None:
            self._attr_icon = icon

    @property
    def native_value(self):
        """Return the current sensor value."""
        value = self._extract_value()
        if value is None:
            return None
        return (
            int(value)
            if self._attr_device_class is SensorDeviceClass.ILLUMINANCE
            else value
        )
