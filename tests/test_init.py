"""Test the setup and unload of the TrueAchievements integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.trueachievements import async_unload_entry
from custom_components.trueachievements.const import CONF_EXCLUDED_APPS, DOMAIN

from .common import get_entity_id
from .conftest import SetupIntegration


async def test_setup_and_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """The entry loads, creates its entities, then unloads cleanly."""
    await setup_integration(mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.entry_id in hass.data[DOMAIN]
    assert hass.states.get(get_entity_id(hass, "sensor", "gamerscore")) is not None

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    assert mock_config_entry.entry_id not in hass.data[DOMAIN]


async def test_unload_entry_keeps_data_when_platforms_fail(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """If the platforms cannot be unloaded, the coordinator is kept."""
    await setup_integration(mock_config_entry)

    with patch.object(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False)
    ):
        assert await async_unload_entry(hass, mock_config_entry) is False

    assert mock_config_entry.entry_id in hass.data[DOMAIN]


async def test_options_update_reloads_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """Changing the options reloads the entry and applies the new settings."""
    await setup_integration(mock_config_entry)
    gamerscore = get_entity_id(hass, "sensor", "gamerscore")
    assert hass.states.get(gamerscore).state == "3500"

    # "Gears 5" (200 G) is now excluded from the statistics.
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_EXCLUDED_APPS: "gears"}
    )
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(gamerscore).state == "3300"
