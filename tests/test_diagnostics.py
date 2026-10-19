"""Test the TrueAchievements diagnostics."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.trueachievements.const import (
    CONF_GAMERTOKEN,
    CONF_USER_AGENT,
)

from .conftest import CSV_URL, MakeEntry, SetupIntegration
from .const import COOKIE, GAMER_ID, GAMERTAG


async def test_diagnostics_redact_the_credentials(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    make_entry: MakeEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """The cookie never appears in the downloaded report."""
    entry = make_entry(
        data={},
        options={
            CONF_GAMERTOKEN: "secret-cookie",
            CONF_USER_AGENT: "Mozilla/5.0 (Test)",
        },
    )
    await setup_integration(entry)

    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert diagnostics["entry"]["data"][CONF_GAMERTOKEN] == "***"
    assert diagnostics["entry"]["options"][CONF_GAMERTOKEN] == "***"
    # Everything else is left readable to help debugging.
    assert diagnostics["entry"]["data"]["gamertag"] == GAMERTAG
    assert diagnostics["entry"]["data"]["gamer_id"] == GAMER_ID
    assert diagnostics["entry"]["options"][CONF_USER_AGENT] == "Mozilla/5.0 (Test)"
    for secret in (COOKIE, "secret-cookie"):
        assert secret not in str(diagnostics)


async def test_diagnostics_report_the_coordinator_state(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """The report tells whether the cookie was accepted and which mapping is used."""
    await setup_integration(mock_config_entry)

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )

    coordinator = diagnostics["coordinator"]
    assert coordinator["auth_failed"] is False
    assert coordinator["mapping_entries"] > 0
    assert coordinator["games_file"].endswith("games.csv")
    assert coordinator["last_valid_update"] != "Unknown"


async def test_diagnostics_report_an_authentication_failure(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """A refused download is visible in the report."""
    aioclient_mock.get(CSV_URL, status=403)
    await setup_integration(mock_config_entry)

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )

    assert diagnostics["coordinator"]["auth_failed"] is True
