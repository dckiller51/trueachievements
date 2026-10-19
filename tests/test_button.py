"""Test the TrueAchievements "Reload game mapping" button."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from .common import get_coordinator, get_entity_id, set_now_playing
from .conftest import Notifications, SetupIntegration


async def test_button_is_a_configuration_entity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """The button is listed in the configuration section of the device."""
    await setup_integration(mock_config_entry)

    entity_id = get_entity_id(hass, "button", "reload_mapping")
    entry = er.async_get(hass).async_get(entity_id)

    assert entry is not None
    assert entry.entity_category is EntityCategory.CONFIG


async def test_button_reloads_the_user_mapping(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    mapping_file: Path,
) -> None:
    """Pressing the button picks up the edits made to the mapping file."""
    await setup_integration(mock_config_entry)
    coordinator = get_coordinator(hass, mock_config_entry)
    assert "my alias" not in coordinator.game_mapping

    mapping_file.write_text(json.dumps({"My Alias": "Halo Infinite"}), encoding="utf-8")
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: get_entity_id(hass, "button", "reload_mapping")},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert coordinator.game_mapping == {"my alias": "Halo Infinite"}


async def test_button_fixes_a_game_that_did_not_match(
    hass: HomeAssistant,
    mock_config_entry_xbox: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    mapping_file: Path,
    notifications: Notifications,
) -> None:
    """After adding a mapping entry and pressing the button, the game matches."""
    set_now_playing(hass, "My Alias", platform="Xbox Series X|S")
    await setup_integration(mock_config_entry_xbox)
    now_playing = get_entity_id(hass, "sensor", "now_playing")
    assert len(notifications.create) == 1
    assert hass.states.get(now_playing).attributes.get("achievements") is None

    mapping_file.write_text(json.dumps({"my alias": "Halo Infinite"}), encoding="utf-8")
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: get_entity_id(hass, "button", "reload_mapping")},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.states.get(now_playing).attributes["achievements"] == "50 / 119"
    assert len(notifications.dismiss) == 1
    assert notifications.dismiss[0].data["notification_id"] == "ta_fix_My_Alias"
