"""Button platform for TrueAchievements."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import TrueAchievementsCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the TrueAchievements button platform."""
    coordinator: TrueAchievementsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TAReloadMappingButton(coordinator)])


class TAReloadMappingButton(
    CoordinatorEntity["TrueAchievementsCoordinator"], ButtonEntity
):
    """Button to reload the game mapping file."""

    _attr_has_entity_name = True
    _attr_translation_key = "reload_mapping"
    _attr_icon = "mdi:file-refresh"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: TrueAchievementsCoordinator) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._attr_unique_id = f"ta_{coordinator.gamer_id}_reload_mapping"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.gamer_id)},
            "name": f"TrueAchievements ({coordinator.gamer_tag})",
        }

    async def async_press(self) -> None:
        """Reload the mapping file and refresh the data."""
        await self.coordinator.async_reload_mapping()
