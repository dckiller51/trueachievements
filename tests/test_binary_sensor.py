"""Test the TrueAchievements authentication status binary sensor."""

from __future__ import annotations

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from .common import get_coordinator, get_entity_id
from .conftest import CSV_URL, SetupIntegration


async def test_auth_status_is_off_when_the_download_works(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """The problem sensor is off while the cookie is accepted."""
    await setup_integration(mock_config_entry)

    entity_id = get_entity_id(hass, "binary_sensor", "auth_status")
    state = hass.states.get(entity_id)

    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes["device_class"] == "problem"
    assert state.attributes["last_update"]


async def test_auth_status_is_on_when_the_cookie_is_refused(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """The problem sensor turns on when the server denies access."""
    aioclient_mock.get(CSV_URL, status=401)
    await setup_integration(mock_config_entry)

    state = hass.states.get(get_entity_id(hass, "binary_sensor", "auth_status"))

    assert state is not None
    assert state.state == STATE_ON


async def test_auth_status_is_a_diagnostic_entity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """The sensor is categorised as diagnostic."""
    await setup_integration(mock_config_entry)

    entity_id = get_entity_id(hass, "binary_sensor", "auth_status")
    entry = er.async_get(hass).async_get(entity_id)

    assert entry is not None
    assert entry.entity_category is EntityCategory.DIAGNOSTIC


async def test_auth_status_stays_available_when_an_update_fails(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """Even if the coordinator update failed, the problem state remains visible."""
    await setup_integration(mock_config_entry)
    entity_id = get_entity_id(hass, "binary_sensor", "auth_status")
    coordinator = get_coordinator(hass, mock_config_entry)

    coordinator.last_update_success = False
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state != STATE_UNAVAILABLE
    # The statistics sensors, on the contrary, become unavailable.
    gamerscore = get_entity_id(hass, "sensor", "gamerscore")
    assert hass.states.get(gamerscore).state == STATE_UNAVAILABLE
