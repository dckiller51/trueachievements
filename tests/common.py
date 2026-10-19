"""Helpers shared by the TrueAchievements tests."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.trueachievements.const import DOMAIN
from custom_components.trueachievements.coordinator import TrueAchievementsCoordinator

from .const import GAMER_ID, XBOX_ENTITY, XBOX_IMAGE_ENTITY


def get_entity_id(hass: HomeAssistant, platform: str, key: str) -> str:
    """Return the entity id registered for a platform and a unique-id key."""
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"ta_{GAMER_ID}_{key}"
    )
    assert entity_id is not None, f"no {platform} entity registered for {key}"
    return entity_id


def get_coordinator(
    hass: HomeAssistant, entry: MockConfigEntry
) -> TrueAchievementsCoordinator:
    """Return the coordinator of a loaded config entry."""
    coordinator: TrueAchievementsCoordinator = hass.data[DOMAIN][entry.entry_id]
    return coordinator


def set_now_playing(
    hass: HomeAssistant,
    name: str,
    *,
    platform: str | None = "Xbox One",
    publisher: str | None = "Microsoft",
    picture: str | None = None,
) -> None:
    """Fake the Xbox Now Playing sensor (and its image entity)."""
    attributes: dict[str, str] = {}
    if platform:
        attributes["platform"] = platform
    if publisher:
        attributes["publisher"] = publisher
    hass.states.async_set(XBOX_ENTITY, name, attributes)
    if picture:
        hass.states.async_set(
            XBOX_IMAGE_ENTITY, "2026-01-01T00:00:00", {"entity_picture": picture}
        )
