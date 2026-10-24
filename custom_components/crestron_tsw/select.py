"""Select the application mode for a Crestron TSW panel."""

import aiohttp

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CrestronEntity
from .const import DOMAIN, ENTITIES_TO_EXPOSE


async def async_setup_entry(
    hass, config_entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the application mode selector."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entity = next(entity for entity in ENTITIES_TO_EXPOSE if entity["type"] == "select")
    async_add_entities(
        [
            CrestronApplicationSelect(
                coordinator,
                entity["name"],
                config_entry,
                entity.get("icon"),
            )
        ],
        update_before_add=True,
    )


class CrestronApplicationSelect(CrestronEntity, SelectEntity):
    """Select one of the application modes supported by the panel."""

    def __init__(self, coordinator, name, config_entry, icon) -> None:
        """Initialize the application mode selector."""
        super().__init__(
            coordinator,
            name,
            ["Device", "ThirdPartyApplications", "Mode"],
            "application_mode",
            config_entry,
            icon=icon,
        )

    @property
    def options(self) -> list[str]:
        """Return application modes supported by this panel."""
        value = self.coordinator.data
        for key in (
            "Device",
            "ThirdPartyApplications",
            "ApplicationsModeSupported",
        ):
            if not isinstance(value, dict):
                return []
            value = value.get(key)
        return (
            [item for item in value if isinstance(item, str)]
            if isinstance(value, list)
            else []
        )

    @property
    def current_option(self) -> str | None:
        """Return the currently selected application mode."""
        value = self._extract_value()
        return value if isinstance(value, str) else None

    async def async_select_option(self, option: str) -> None:
        """Set the selected application mode."""
        payload = {"Device": {"ThirdPartyApplications": {"Mode": option}}}
        try:
            await self.coordinator.async_post_api(
                "/Device/ThirdPartyApplications", payload
            )
        except aiohttp.ClientError as err:
            raise HomeAssistantError("Failed to update application mode") from err
