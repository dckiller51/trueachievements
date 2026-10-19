"""Diagnostics support for TrueAchievements."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_GAMERTOKEN, CONF_WEBHOOK_ID, DOMAIN
from .coordinator import TrueAchievementsCoordinator

TO_REDACT = {CONF_GAMERTOKEN, CONF_WEBHOOK_ID}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: TrueAchievementsCoordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry": {
            "data": {
                k: ("***" if k in TO_REDACT else v) for k, v in entry.data.items()
            },
            "options": {
                k: ("***" if k in TO_REDACT else v) for k, v in entry.options.items()
            },
        },
        "coordinator": {
            "auth_failed": coordinator.auth_failed,
            "mapping_entries": len(coordinator.game_mapping),
            "games_file": str(coordinator.games_file),
            "last_valid_update": coordinator.last_valid_update,
        },
    }
