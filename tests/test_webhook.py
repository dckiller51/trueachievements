"""Test the webhook that receives the CSV export sent by another computer."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import pytest
from homeassistant.components import webhook
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.trueachievements.const import (
    CONF_FILE_ONLY,
    CONF_WEBHOOK_ID,
    MAX_UPLOAD_BYTES,
)

from .common import get_coordinator
from .conftest import MakeEntry, SetupIntegration
from .const import build_csv


@pytest.fixture
async def entry(
    hass: HomeAssistant, make_entry: MakeEntry, setup_integration: SetupIntegration
) -> MockConfigEntry:
    """Return a configured entry in local file mode."""
    await async_setup_component(hass, "webhook", {})
    return await setup_integration(
        make_entry(data={CONF_WEBHOOK_ID: "hook123"}, options={CONF_FILE_ONLY: True})
    )


async def test_webhook_id_is_created_when_missing(
    hass: HomeAssistant, make_entry: MakeEntry, setup_integration: SetupIntegration
) -> None:
    """An entry created before the webhook existed gets an id on setup."""
    entry = await setup_integration(make_entry(options={CONF_FILE_ONLY: True}))
    assert entry.data[CONF_WEBHOOK_ID]


async def test_uploaded_csv_is_stored(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
    games_file: Path,
) -> None:
    """A valid export posted to the webhook replaces the local CSV."""
    games_file.unlink(missing_ok=True)
    client = await hass_client_no_auth()
    response = await client.post(
        webhook.async_generate_path("hook123"), data=build_csv()
    )

    assert response.status == HTTPStatus.OK
    assert games_file.read_bytes() == build_csv()
    coordinator = get_coordinator(hass, entry)
    assert coordinator.last_valid_update != "Unknown"
    assert coordinator.auth_failed is False


@pytest.mark.parametrize("content", [b"", b"<html>nope</html>", b"x" * 2000])
async def test_uploaded_garbage_is_rejected(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
    games_file: Path,
    content: bytes,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Something that is not a CSV export never replaces the local file."""
    before = games_file.read_bytes() if games_file.exists() else None
    client = await hass_client_no_auth()
    response = await client.post(webhook.async_generate_path("hook123"), data=content)

    assert response.status == HTTPStatus.BAD_REQUEST
    assert (games_file.read_bytes() if games_file.exists() else None) == before
    assert "Rejected an uploaded file" in caplog.text


async def test_oversized_upload_is_rejected(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """A huge body is refused before being read."""
    client = await hass_client_no_auth()
    response = await client.post(
        webhook.async_generate_path("hook123"), data=b"x" * (MAX_UPLOAD_BYTES + 1)
    )
    assert response.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


async def test_webhook_is_removed_on_unload(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    hass_client_no_auth: ClientSessionGenerator,
) -> None:
    """The upload address stops working when the integration is unloaded."""
    await hass.config_entries.async_unload(entry.entry_id)
    client = await hass_client_no_auth()
    response = await client.post(
        webhook.async_generate_path("hook123"), data=build_csv()
    )
    # Home Assistant answers 200 and ignores unknown webhooks.
    assert response.status == HTTPStatus.OK
    assert "hook123" not in hass.data.get("webhook", {})
