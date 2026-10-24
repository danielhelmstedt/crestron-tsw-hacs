"""Switch platform for Crestron TSW panels."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CrestronEntity
from .const import DOMAIN, ENTITIES_TO_EXPOSE


async def async_setup_entry(
    hass, config_entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Crestron switches."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []
    for entity in ENTITIES_TO_EXPOSE:
        if entity["type"] == "ssh_switch":
            if coordinator.username and coordinator.password:
                entities.append(
                    CrestronCameraStreamSwitch(
                        coordinator,
                        config_entry,
                        entity["name"],
                        entity.get("icon"),
                        entity.get("device_class"),
                    )
                )
            continue
        if entity["type"] != "switch":
            continue
        entity_name = entity["name"]
        crestron_switch = CrestronSwitch(
            coordinator,
            entity_name,
            entity["value_path"],
            entity_name.lower().replace(" ", "_"),
            config_entry,
            icon=entity.get("icon"),
            device_class=entity.get("device_class"),
        )
        if entity.get("requires_tsw_x70"):
            model = str(crestron_switch.device_info.get("model", "")).upper()
            if not model.startswith("TSW-") or not model.endswith("70"):
                continue
        entities.append(crestron_switch)

    async_add_entities(entities)


class CrestronSwitch(CrestronEntity, SwitchEntity):
    """Representation of a CresNext boolean property."""

    @property
    def is_on(self) -> bool | None:
        """Return the current property value."""
        value = self._extract_value()
        return value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the property on."""
        await self._async_set_value(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the property off."""
        await self._async_set_value(False)

    async def _async_set_value(self, state: bool) -> None:
        payload = {}
        current_level = payload
        for key in self.value_path[:-1]:
            current_level[key] = {}
            current_level = current_level[key]
        current_level[self.value_path[-1]] = state
        await self.coordinator.async_post_api("/Device", payload)


class CrestronCameraStreamSwitch(CrestronEntity, SwitchEntity):
    """Control the panel's RTSP camera stream over SSH."""

    def __init__(self, coordinator, config_entry, name, icon, device_class) -> None:
        """Initialize the camera stream switch."""
        super().__init__(
            coordinator,
            name,
            ["camera_stream_is_on"],
            f"{config_entry.entry_id}_camera_rtsp_stream",
            config_entry,
            icon=icon,
            device_class=device_class,
        )
        self._attr_unique_id = f"{config_entry.entry_id}_camera_rtsp_stream"

    @property
    def available(self) -> bool:
        """Return whether the coordinator is available and SSH returned state."""
        return (
            self.coordinator.last_update_success
            and "camera_stream_is_on" in self.coordinator.data
        )

    @property
    def is_on(self) -> bool | None:
        """Return the current RTSP stream state."""
        return self.coordinator.data.get("camera_stream_is_on")

    async def async_turn_on(self, **kwargs) -> None:
        """Enable the panel RTSP stream."""
        await self._async_set_stream(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable the panel RTSP stream."""
        await self._async_set_stream(False)

    async def _async_set_stream(self, enabled: bool) -> None:
        await self.coordinator.async_set_camera_stream(enabled)
        updated_data = self.coordinator.data.copy()
        updated_data["camera_stream_is_on"] = enabled
        self.coordinator.async_set_updated_data(updated_data)
