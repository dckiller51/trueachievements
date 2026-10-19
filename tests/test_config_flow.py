"""Test the TrueAchievements config flow."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.trueachievements.const import (
    CONF_EXCLUDED_APPS,
    CONF_FILE_ONLY,
    CONF_GAMER_ID,
    CONF_GAMERTAG,
    CONF_GAMERTOKEN,
    CONF_GAMES_FILE,
    CONF_NOTIFY_AUTH_ERROR,
    CONF_NOTIFY_MAPPING,
    CONF_NOW_PLAYING_ENTITY,
    CONF_USER_AGENT,
    CONF_WEBHOOK_ID,
    DEFAULT_GAMES_FILE,
    DOMAIN,
)

from .conftest import MakeEntry
from .const import COOKIE, GAMER_ID, GAMERTAG, XBOX_ENTITY

REQUIRED_INPUT = {
    CONF_GAMERTAG: GAMERTAG,
    CONF_GAMER_ID: GAMER_ID,
    CONF_GAMERTOKEN: COOKIE,
}


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Prevent the integration from really being set up by the flow tests."""
    with patch(
        "custom_components.trueachievements.async_setup_entry", return_value=True
    ) as mock:
        yield mock


async def test_user_form_is_shown(hass: HomeAssistant) -> None:
    """The first step shows the credentials form, including the Cloudflare fields."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    fields = {str(key) for key in result["data_schema"].schema}
    assert {
        CONF_GAMERTAG,
        CONF_GAMER_ID,
        CONF_GAMERTOKEN,
        CONF_USER_AGENT,
        CONF_FILE_ONLY,
        CONF_NOW_PLAYING_ENTITY,
        CONF_EXCLUDED_APPS,
        CONF_GAMES_FILE,
        CONF_NOTIFY_MAPPING,
        CONF_NOTIFY_AUTH_ERROR,
    } == fields


async def test_user_flow_creates_entry_with_defaults(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Only the required fields are needed; optional fields get their defaults."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], REQUIRED_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"TA ({GAMERTAG})"
    assert result["data"].pop(CONF_WEBHOOK_ID)
    assert result["data"] == {
        **REQUIRED_INPUT,
        CONF_USER_AGENT: "",
        CONF_FILE_ONLY: False,
        CONF_EXCLUDED_APPS: "",
        CONF_GAMES_FILE: DEFAULT_GAMES_FILE,
        CONF_NOTIFY_MAPPING: True,
        CONF_NOTIFY_AUTH_ERROR: True,
    }
    assert len(mock_setup_entry.mock_calls) == 1


async def test_user_flow_creates_entry_with_all_fields(
    hass: HomeAssistant, mock_setup_entry: AsyncMock
) -> None:
    """Every optional field submitted by the user is stored in the entry."""
    user_input: dict[str, Any] = {
        **REQUIRED_INPUT,
        CONF_USER_AGENT: "Mozilla/5.0 (Test)",
        CONF_FILE_ONLY: True,
        CONF_NOW_PLAYING_ENTITY: XBOX_ENTITY,
        CONF_EXCLUDED_APPS: "YouTube, Netflix",
        CONF_GAMES_FILE: "custom/games.csv",
        CONF_NOTIFY_MAPPING: False,
        CONF_NOTIFY_AUTH_ERROR: False,
    }
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"].pop(CONF_WEBHOOK_ID)
    assert result["data"] == user_input


async def test_user_flow_requires_credentials(hass: HomeAssistant) -> None:
    """The gamertag, the GamerID and the cookie are mandatory."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_GAMERTAG: GAMERTAG}
        )


async def test_options_flow_shows_form(
    hass: HomeAssistant, make_entry: MakeEntry
) -> None:
    """The options form exposes the cookie, the Cloudflare fields and the toggles."""
    entry = make_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    fields = {str(key) for key in result["data_schema"].schema}
    assert {
        CONF_GAMERTOKEN,
        CONF_USER_AGENT,
        CONF_FILE_ONLY,
        CONF_NOW_PLAYING_ENTITY,
        CONF_EXCLUDED_APPS,
        CONF_NOTIFY_MAPPING,
        CONF_NOTIFY_AUTH_ERROR,
    } == fields


async def test_options_flow_updates_cookie_fields(
    hass: HomeAssistant, make_entry: MakeEntry
) -> None:
    """Refreshing the cookie and the User-Agent is saved in the entry options."""
    entry = make_entry(data={CONF_NOW_PLAYING_ENTITY: XBOX_ENTITY})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch.object(hass.config_entries, "async_reload", AsyncMock()):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_GAMERTOKEN: "ASP.NET_SessionId=new",
                CONF_USER_AGENT: "Mozilla/5.0 (Test)",
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_GAMERTOKEN] == "ASP.NET_SessionId=new"
    assert entry.options[CONF_USER_AGENT] == "Mozilla/5.0 (Test)"
    assert entry.options[CONF_NOW_PLAYING_ENTITY] == XBOX_ENTITY


async def test_options_flow_keeps_current_values(
    hass: HomeAssistant, make_entry: MakeEntry
) -> None:
    """Submitting the pre-filled form keeps the values already configured."""
    entry = make_entry(
        data={CONF_NOW_PLAYING_ENTITY: XBOX_ENTITY, CONF_EXCLUDED_APPS: "Netflix"},
        options={
            CONF_GAMERTOKEN: "from-options",
            CONF_USER_AGENT: "UA-from-options",
            CONF_NOTIFY_MAPPING: False,
            CONF_NOTIFY_AUTH_ERROR: False,
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch.object(hass.config_entries, "async_reload", AsyncMock()):
        # The frontend sends back the pre-filled values when the form is untouched.
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_GAMERTOKEN: "from-options",
                CONF_USER_AGENT: "UA-from-options",
                CONF_EXCLUDED_APPS: "Netflix",
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_GAMERTOKEN: "from-options",
        CONF_USER_AGENT: "UA-from-options",
        CONF_FILE_ONLY: False,
        CONF_NOW_PLAYING_ENTITY: XBOX_ENTITY,
        CONF_EXCLUDED_APPS: "Netflix",
        CONF_NOTIFY_MAPPING: False,
        CONF_NOTIFY_AUTH_ERROR: False,
    }


async def test_options_flow_without_now_playing_entity(
    hass: HomeAssistant, make_entry: MakeEntry
) -> None:
    """The options form can be saved when no Xbox entity was ever selected."""
    entry = make_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch.object(hass.config_entries, "async_reload", AsyncMock()):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_USER_AGENT: "Mozilla/5.0 (Test)"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_options_flow_can_clear_optional_text_fields(
    hass: HomeAssistant, make_entry: MakeEntry
) -> None:
    """A field emptied in the form is really cleared, even if the entry data has it."""
    entry = make_entry(
        data={
            CONF_USER_AGENT: "old-agent",
            CONF_EXCLUDED_APPS: "Netflix",
        },
        options={CONF_USER_AGENT: "options-agent"},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    # The current values are only suggested: they are not forced back on submit.
    suggested = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }
    assert suggested[CONF_USER_AGENT] == "options-agent"
    assert suggested[CONF_EXCLUDED_APPS] == "Netflix"

    with patch.object(hass.config_entries, "async_reload", AsyncMock()):
        # The frontend leaves out the fields that were emptied.
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_GAMERTOKEN: "token"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_USER_AGENT] == ""
    assert result["data"][CONF_EXCLUDED_APPS] == ""
