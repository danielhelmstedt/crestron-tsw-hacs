"""Text entities for Crestron application URLs."""

from collections.abc import Iterator
import logging

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CrestronEntity
from .const import DOMAIN, ENTITIES_TO_EXPOSE

_LOGGER = logging.getLogger(__name__)


def _find_url_paths(
    value: dict, prefix: tuple[str, ...] = ()
) -> Iterator[tuple[str, ...]]:
    """Find string URL fields within an application settings object."""
    for key, child in value.items():
        path = (*prefix, key)
        if "url" in key.casefold() and isinstance(child, str):
            yield path
        elif isinstance(child, dict):
            yield from _find_url_paths(child, path)


async def async_setup_entry(
    hass, config_entry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the application URL text entity."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entity = next(entity for entity in ENTITIES_TO_EXPOSE if entity["type"] == "text")
    async_add_entities(
        [
            CrestronApplicationUrl(
                coordinator,
                entity["name"],
                "application_url",
                config_entry,
                entity.get("icon"),
            )
        ]
    )


class CrestronApplicationUrl(CrestronEntity, TextEntity):
    """Edit the URL field belonging to the currently selected application."""

    _attr_mode = TextMode.TEXT
    _attr_native_min = 0
    _attr_native_max = 250

    def __init__(self, coordinator, name, unique_id, config_entry, icon) -> None:
        """Initialize the application URL entity."""
        super().__init__(coordinator, name, [], unique_id, config_entry, icon=icon)
        self._attr_unique_id = unique_id

    def _find_url_path(self) -> tuple[str, ...] | None:
        """Find the URL field for the panel's active application mode."""
        applications = self.coordinator.data.get("Device", {}).get(
            "ThirdPartyApplications", {}
        )
        if not isinstance(applications, dict):
            return None

        mode = applications.get("Mode")
        if not isinstance(mode, str):
            return None
        normalized_mode = "".join(
            character for character in mode.casefold() if character.isalnum()
        )

        candidates = []
        for branch, settings in applications.items():
            if branch in {"Mode", "ApplicationsModeSupported"} or not isinstance(
                settings, dict
            ):
                continue
            candidates.extend((branch, *path) for path in _find_url_paths(settings))

        matching = [
            path
            for path in candidates
            if "".join(
                character for character in path[0].casefold() if character.isalnum()
            )
            in normalized_mode
            or normalized_mode
            in "".join(
                character for character in path[0].casefold() if character.isalnum()
            )
        ]
        if matching:
            return matching[0]
        if len(candidates) == 1:
            return candidates[0]
        return None

    @property
    def available(self) -> bool:
        """Return whether the selected application exposes a URL field."""
        return super().available and self._find_url_path() is not None

    @property
    def native_value(self) -> str | None:
        """Return the current URL value, if available."""
        path = self._find_url_path()
        if path is None:
            return None
        value = self.coordinator.data.get("Device", {}).get(
            "ThirdPartyApplications", {}
        )
        for key in path:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value if isinstance(value, str) else None

    async def async_set_value(self, value: str) -> None:
        """Update the active application's URL field."""
        path = self._find_url_path()
        if path is None:
            raise HomeAssistantError("The selected application has no URL field")

        settings = {}
        current = settings
        for key in path[:-1]:
            current[key] = {}
            current = current[key]
        current[path[-1]] = value
        payload = {"Device": {"ThirdPartyApplications": settings}}

        await self.coordinator.async_post_api("/Device/ThirdPartyApplications", payload)
