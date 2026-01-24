"""Sensor platform for TrueAchievements."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ATTR_GAMERSCORE,
    ATTR_TA_SCORE,
    ATTR_COMPLETION_PCT,
    ATTR_TOTAL_GAMES,
    ATTR_COMPLETED_GAMES,
    ATTR_TOTAL_ACHIEVEMENTS,
    CONF_NOW_PLAYING_ENTITY,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from .coordinator import TrueAchievementsCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class TrueAchievementsSensorDescription(SensorEntityDescription):
    """Description for TrueAchievements sensors."""
    value_fn: Callable[[dict[str, Any]], Any]


# Numeric sensors definition
SENSOR_TYPES: tuple[TrueAchievementsSensorDescription, ...] = (
    TrueAchievementsSensorDescription(
        key=ATTR_GAMERSCORE,
        translation_key=ATTR_GAMERSCORE,
        icon="mdi:alpha-g-circle",
        native_unit_of_measurement="G",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.get(ATTR_GAMERSCORE),
    ),
    TrueAchievementsSensorDescription(
        key=ATTR_TA_SCORE,
        translation_key=ATTR_TA_SCORE,
        icon="mdi:star-circle",
        native_unit_of_measurement="TA",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.get(ATTR_TA_SCORE),
    ),
    TrueAchievementsSensorDescription(
        key=ATTR_TOTAL_GAMES,
        translation_key=ATTR_TOTAL_GAMES,
        icon="mdi:controller",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(ATTR_TOTAL_GAMES),
    ),
    TrueAchievementsSensorDescription(
        key=ATTR_TOTAL_ACHIEVEMENTS,
        translation_key=ATTR_TOTAL_ACHIEVEMENTS,
        icon="mdi:trophy-variant",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data.get(ATTR_TOTAL_ACHIEVEMENTS),
    ),
    TrueAchievementsSensorDescription(
        key=ATTR_COMPLETED_GAMES,
        translation_key=ATTR_COMPLETED_GAMES,
        icon="mdi:trophy",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(ATTR_COMPLETED_GAMES),
    ),
    TrueAchievementsSensorDescription(
        key=ATTR_COMPLETION_PCT,
        translation_key=ATTR_COMPLETION_PCT,
        icon="mdi:percent",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get(ATTR_COMPLETION_PCT),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the TrueAchievements sensor platform."""
    coordinator: TrueAchievementsCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []

    for description in SENSOR_TYPES:
        entities.append(TrueAchievementsSensor(coordinator, description))

    now_playing_source = entry.options.get(
        CONF_NOW_PLAYING_ENTITY,
        entry.data.get(CONF_NOW_PLAYING_ENTITY)
    )

    if now_playing_source:
        _LOGGER.debug("Xbox entity found: %s. Adding Now Playing sensor.", now_playing_source)
        entities.append(TANowPlayingSensor(coordinator))
    else:
        _LOGGER.info("No Xbox entity selected. Now Playing sensor will not be created.")

    async_add_entities(entities)


class TrueAchievementsSensor(CoordinatorEntity["TrueAchievementsCoordinator"], SensorEntity):
    """General TrueAchievements sensor representation."""

    entity_description: TrueAchievementsSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TrueAchievementsCoordinator,
        description: TrueAchievementsSensorDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"ta_{coordinator.gamer_id}_{description.key}"
        self._attr_translation_key = description.translation_key

        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.gamer_id)},
            "name": f"TrueAchievements ({coordinator.gamer_tag})",
        }

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)


class TANowPlayingSensor(CoordinatorEntity["TrueAchievementsCoordinator"], SensorEntity):
    """Now Playing sensor with game image and platform details."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TrueAchievementsCoordinator) -> None:
        """Initialize the Now Playing sensor."""
        super().__init__(coordinator)
        self._attr_translation_key = "now_playing"
        self._attr_unique_id = f"ta_{coordinator.gamer_id}_now_playing"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.gamer_id)},
            "name": f"TrueAchievements ({coordinator.gamer_tag})",
        }

    @property
    def entity_picture(self) -> str | None:
        """Fetch the game image from the linked Xbox entity."""
        game_info = self.coordinator.get_game_info_local()
        if game_info and isinstance(game_info, dict):
            return str(game_info.get("image")) if game_info.get("image") else None
        return None

    @property
    def icon(self) -> str | None:
        """Fallback icon if no entity picture is available."""
        if self.entity_picture:
            return None
        return "mdi:microsoft-xbox-controller"

    @property
    def native_value(self) -> str:
        """Return the game name or 'offline_status'."""
        val = self.coordinator.data.get("current_game_name")
        return str(val) if val else "offline_status"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return details like Platform, Achievements, URL, and last update."""
        details = self.coordinator.data.get("current_game_details")

        attrs = {}
        if isinstance(details, dict):
            attrs.update(details)

        attrs["last_update"] = self.coordinator.data.get("last_update")
        return attrs
