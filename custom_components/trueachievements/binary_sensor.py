"""Binary sensor platform for TrueAchievements."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_AUTH_STATUS,
    VERSION,
)

if TYPE_CHECKING:
    from .coordinator import TrueAchievementsCoordinator


@dataclass(frozen=True, kw_only=True)
class TABinarySensorEntityDescription(BinarySensorEntityDescription):
    """Description for TrueAchievements binary sensors."""
    is_on_fn: Callable[[TrueAchievementsCoordinator], bool]


BINARY_SENSOR_DESCRIPTIONS: tuple[TABinarySensorEntityDescription, ...] = (
    TABinarySensorEntityDescription(
        key=CONF_AUTH_STATUS,
        translation_key=CONF_AUTH_STATUS,
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda coordinator: bool(coordinator.auth_failed),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the TrueAchievements binary sensor platform."""
    coordinator: TrueAchievementsCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [TABinarySensorEntity(coordinator, desc) for desc in BINARY_SENSOR_DESCRIPTIONS]

    async_add_entities(entities)


class TABinarySensorEntity(CoordinatorEntity["TrueAchievementsCoordinator"], BinarySensorEntity):
    """Representation of a TrueAchievements binary sensor."""

    entity_description: TABinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TrueAchievementsCoordinator,
        description: TABinarySensorEntityDescription
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"ta_{coordinator.gamer_id}_{description.key}"
        self.entity_id = f"binary_sensor.ta_{coordinator.gamer_tag.lower()}_{description.key}"
        self._attr_translation_key = description.key

        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.gamer_id)},
            "name": f"TrueAchievements ({coordinator.gamer_tag})",
            "sw_version": VERSION,
        }

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self.entity_description.is_on_fn(self.coordinator)

    @property
    def available(self) -> bool:
        """Keep the sensor available even if auth fails to show the problem state."""
        return True
