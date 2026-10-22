"""Test the TrueAchievements sensors."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.trueachievements.const import DOMAIN

from .common import get_coordinator, get_entity_id, set_now_playing
from .conftest import CSV_URL, SetupIntegration
from .const import (
    COMPLETION_PCT,
    GAMER_ID,
    HALO_URL,
    HALO_WALKTHROUGH,
    TOTAL_ACHIEVEMENTS,
    TOTAL_COMPLETED,
    TOTAL_GAMERSCORE,
    TOTAL_STARTED,
    TOTAL_TA_SCORE,
    XBOX_ENTITY,
    XBOX_IMAGE_ENTITY,
)


@pytest.mark.parametrize(
    ("key", "expected", "unit"),
    [
        ("gamerscore", str(TOTAL_GAMERSCORE), "G"),
        ("ta_score", str(TOTAL_TA_SCORE), "TA"),
        ("total_games", str(TOTAL_STARTED), "games"),
        ("total_achievements", str(TOTAL_ACHIEVEMENTS), None),
        ("completed_games", str(TOTAL_COMPLETED), "games"),
        ("completion_percentage", str(COMPLETION_PCT), "%"),
    ],
)
async def test_statistics_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    key: str,
    expected: str,
    unit: str | None,
) -> None:
    """The totals are computed from the CSV, ignoring apps and unstarted games."""
    await setup_integration(mock_config_entry)

    state = hass.states.get(get_entity_id(hass, "sensor", key))

    assert state is not None
    assert state.state == expected
    assert state.attributes.get("unit_of_measurement") == unit


async def test_sensors_share_one_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    device_registry: object,
) -> None:
    """Every entity is attached to the same TrueAchievements device."""
    await setup_integration(mock_config_entry)

    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, mock_config_entry.entry_id)
    device_ids = {entry.device_id for entry in entries}

    assert len(entries) == 8
    assert len(device_ids) == 1
    assert None not in device_ids
    assert get_coordinator(hass, mock_config_entry).gamer_id == GAMER_ID
    assert hass.data[DOMAIN]


async def test_no_now_playing_sensor_without_xbox_entity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """The Now Playing sensor only exists when an Xbox entity is configured."""
    await setup_integration(mock_config_entry)

    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, f"ta_{GAMER_ID}_now_playing")
        is None
    )


async def test_now_playing_sensor_matches_the_current_game(
    hass: HomeAssistant,
    mock_config_entry_xbox: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """The Now Playing sensor exposes the statistics of the game being played."""
    set_now_playing(
        hass,
        "Halo Infinite",
        platform="Xbox Series X|S",
        picture="/local/halo.png",
    )
    await setup_integration(mock_config_entry_xbox)

    state = hass.states.get(get_entity_id(hass, "sensor", "now_playing"))

    assert state is not None
    assert state.state == "Halo Infinite"
    assert state.attributes["entity_picture"] == "/local/halo.png"
    assert "icon" not in state.attributes
    assert state.attributes["platform"] == "Xbox Series X|S"
    assert state.attributes["publisher"] == "Microsoft"
    assert state.attributes["achievements"] == "50 / 119"
    assert state.attributes["gamerscore"] == "1000 G / 2000 G"
    assert state.attributes["ta_score"] == "1500 TA / 4000 TA"
    assert state.attributes["hours_played"] == "40.5 h"
    assert state.attributes["game_completion"] == "42%"
    assert state.attributes["game_ratio"] == "1.55"
    assert state.attributes["game_url"] == HALO_URL
    assert state.attributes["walkthrough_url"] == HALO_WALKTHROUGH
    assert state.attributes["last_update"]


async def test_now_playing_picture_follows_the_image_token(
    hass: HomeAssistant,
    mock_config_entry_xbox: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """A new token on the Xbox image entity is reflected on the sensor."""
    set_now_playing(
        hass, "Halo Infinite", platform="Xbox Series X|S", picture="/api/x?token=old"
    )
    await setup_integration(mock_config_entry_xbox)
    entity_id = get_entity_id(hass, "sensor", "now_playing")
    assert hass.states.get(entity_id).attributes["entity_picture"] == (
        "/api/x?token=old"
    )

    hass.states.async_set(
        XBOX_IMAGE_ENTITY, "2026-01-01T00:05:00", {"entity_picture": "/api/x?token=new"}
    )
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).attributes["entity_picture"] == (
        "/api/x?token=new"
    )


async def test_now_playing_sensor_without_picture_uses_icon(
    hass: HomeAssistant,
    mock_config_entry_xbox: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """Without an image entity, the sensor falls back to a controller icon."""
    set_now_playing(hass, "Halo Infinite", platform="Xbox Series X|S")
    await setup_integration(mock_config_entry_xbox)

    state = hass.states.get(get_entity_id(hass, "sensor", "now_playing"))

    assert state is not None
    assert state.attributes["icon"] == "mdi:microsoft-xbox-controller"
    assert state.attributes.get("entity_picture") is None


async def test_now_playing_sensor_is_offline_when_idle(
    hass: HomeAssistant,
    mock_config_entry_xbox: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """When nothing is being played, the sensor reports the offline status."""
    hass.states.async_set(XBOX_ENTITY, "idle")
    await setup_integration(mock_config_entry_xbox)

    state = hass.states.get(get_entity_id(hass, "sensor", "now_playing"))

    assert state is not None
    assert state.state == "offline_status"


async def test_now_playing_sensor_follows_the_xbox_entity(
    hass: HomeAssistant,
    mock_config_entry_xbox: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """A change of game on the Xbox entity refreshes the sensor right away."""
    hass.states.async_set(XBOX_ENTITY, "idle")
    await setup_integration(mock_config_entry_xbox)
    entity_id = get_entity_id(hass, "sensor", "now_playing")
    assert hass.states.get(entity_id).state == "offline_status"

    set_now_playing(hass, "Forza Horizon 5", platform="Xbox One")
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "Forza Horizon 5"
    assert state.attributes["achievements"] == "120 / 120"
    # The CSV is only downloaded once: a change of game reads the local copy.
    assert mock_csv_download.call_count == 1


async def test_sensors_without_data_when_download_is_denied(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """With no CSV and a refused download, the statistics are simply unknown."""
    aioclient_mock.get(CSV_URL, status=403)
    await setup_integration(mock_config_entry)

    state = hass.states.get(get_entity_id(hass, "sensor", "gamerscore"))

    assert state is not None
    assert state.state == "unknown"
