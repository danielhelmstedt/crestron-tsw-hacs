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
    if coordinator.username and coordinator.password:
        entities.append(CrestronLightBarSensor(coordinator, config_entry))
    async_add_entities(entities, update_before_add=True)


class CrestronLightBarSensor(CrestronEntity, SensorEntity):
    """Expose confirmed USB light-bar settings for a template light."""

    def __init__(self, coordinator, config_entry) -> None:
        """Initialize the feedback sensor."""
        super().__init__(
            coordinator,
            "Light Bar Status",
            ["light_bar"],
            "light_bar",
            config_entry,
            icon="mdi:led-strip-variant",
        )
        self._attr_unique_id = f"{config_entry.entry_id}_light_bar"

    @property
    def available(self) -> bool:
        """Require a connected accessory and successful join read."""
        return (
            super().available
            and self.coordinator._light_bar_connected()
            and "light_bar" in self.coordinator.data
        )

    @property
    def native_value(self) -> str | None:
        """Return whether any enabled channel has nonzero brightness."""
        channels = self._extract_value()
        if channels is None:
            return None
        return (
            "on"
            if any(
                channel["control"] and channel["brightness"]
                for channel in channels.values()
            )
            else "off"
        )

    @property
    def extra_state_attributes(self) -> dict:
        """Expose normalized RGB, brightness, and actual channel settings."""
        channels = self._extract_value()
        if channels is None:
            return {}
        is_on = self.native_value == "on"
        levels = [
            channels[color]["brightness"]
            if not is_on or channels[color]["control"]
            else 0
            for color in ("RED", "GREEN", "BLUE")
        ]
        peak = max(levels)
        return {
            "brightness": round(peak / 100 * 255),
            "rgb_color": [
                round(level / peak * 255) if peak else 255 for level in levels
            ],
            "channels": channels,
        }


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
