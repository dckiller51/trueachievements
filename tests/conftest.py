"""Fixtures for the TrueAchievements tests."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.trueachievements.const import (
    CONF_EXCLUDED_APPS,
    CONF_GAMER_ID,
    CONF_GAMERTAG,
    CONF_GAMERTOKEN,
    CONF_GAMES_FILE,
    CONF_MAPPING_FILE,
    CONF_NOTIFY_AUTH_ERROR,
    CONF_NOTIFY_MAPPING,
    CONF_NOW_PLAYING_ENTITY,
    DOMAIN,
    URL_EXPORT_COLLECTION,
)

from .const import COOKIE, GAMER_ID, GAMERTAG, XBOX_ENTITY, build_csv

CSV_URL = URL_EXPORT_COLLECTION.format(GAMER_ID)

SetupIntegration = Callable[[MockConfigEntry], Coroutine[Any, Any, MockConfigEntry]]
MakeEntry = Callable[..., MockConfigEntry]


@dataclass
class Notifications:
    """Persistent notification service calls recorded during a test."""

    create: list[ServiceCall]
    dismiss: list[ServiceCall]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow Home Assistant to load the custom integration in every test."""


@pytest.fixture
def games_file(tmp_path: Path) -> Path:
    """Return the path of the CSV file used by the integration."""
    return tmp_path / "games.csv"


@pytest.fixture
def mapping_file(tmp_path: Path) -> Path:
    """Return the path of the (initially absent) user mapping file."""
    return tmp_path / "mapping.json"


@pytest.fixture
def entry_data(games_file: Path, mapping_file: Path) -> dict[str, Any]:
    """Return the config entry data, pointing at temporary files."""
    return {
        CONF_GAMERTAG: GAMERTAG,
        CONF_GAMER_ID: GAMER_ID,
        CONF_GAMERTOKEN: COOKIE,
        CONF_GAMES_FILE: str(games_file),
        CONF_MAPPING_FILE: str(mapping_file),
        CONF_EXCLUDED_APPS: "",
        CONF_NOTIFY_MAPPING: True,
        CONF_NOTIFY_AUTH_ERROR: True,
    }


@pytest.fixture
def make_entry(entry_data: dict[str, Any]) -> MakeEntry:
    """Return a factory building config entries with data/options overrides."""

    def _make(
        *, data: dict[str, Any] | None = None, options: dict[str, Any] | None = None
    ) -> MockConfigEntry:
        return MockConfigEntry(
            domain=DOMAIN,
            title=f"TA ({GAMERTAG})",
            data={**entry_data, **(data or {})},
            options=options or {},
        )

    return _make


@pytest.fixture
def mock_config_entry(make_entry: MakeEntry) -> MockConfigEntry:
    """Return a config entry without a Now Playing entity."""
    return make_entry()


@pytest.fixture
def mock_config_entry_xbox(make_entry: MakeEntry) -> MockConfigEntry:
    """Return a config entry tracking an Xbox Now Playing entity."""
    return make_entry(data={CONF_NOW_PLAYING_ENTITY: XBOX_ENTITY})


@pytest.fixture
def mock_csv_download(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Serve a valid CSV export for the download URL."""
    aioclient_mock.get(CSV_URL, content=build_csv())
    return aioclient_mock


@pytest.fixture
def setup_integration(hass: HomeAssistant) -> SetupIntegration:
    """Return a helper that adds a config entry and sets it up."""

    async def _setup(entry: MockConfigEntry) -> MockConfigEntry:
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    return _setup


@pytest.fixture
async def notifications(hass: HomeAssistant) -> Notifications:
    """Record the persistent notifications created or dismissed by the integration."""
    assert await async_setup_component(hass, "persistent_notification", {})
    return Notifications(
        create=async_mock_service(hass, "persistent_notification", "create"),
        dismiss=async_mock_service(hass, "persistent_notification", "dismiss"),
    )
