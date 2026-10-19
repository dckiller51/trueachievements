"""Test the TrueAchievements coordinator: download, CSV parsing, mapping, alerts."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.trueachievements.const import (
    CONF_EXCLUDED_APPS,
    CONF_FILE_ONLY,
    CONF_GAMERTOKEN,
    CONF_NOTIFY_AUTH_ERROR,
    CONF_NOTIFY_MAPPING,
    CONF_USER_AGENT,
    DEFAULT_USER_AGENT,
)
from custom_components.trueachievements.coordinator import (
    describe_response,
    merge_cookie,
    parse_cookie,
)

from .common import get_coordinator, get_entity_id, set_now_playing
from .conftest import CSV_URL, MakeEntry, Notifications, SetupIntegration
from .const import (
    COOKIE,
    GAMERTAG,
    TOTAL_GAMERSCORE,
    XBOX_ENTITY,
    build_csv,
    game_row,
)

BASE_COOKIE = "ASP.NET_SessionId=abc; GamerID=8071; cf_clearance=OLD; GamerToken=tok_1; HashKey=hk"


# --------------------------------------------------------------------------- #
# Cookie helpers
# --------------------------------------------------------------------------- #
def test_parse_cookie_keeps_the_order_and_ignores_garbage() -> None:
    """Cookie strings are split in name/value pairs."""
    assert parse_cookie(" A=1; B=x=y;; junk; C= ") == {"A": "1", "B": "x=y", "C": ""}


def test_merge_cookie_only_replaces_the_cookies_already_present() -> None:
    """Renewed cookies replace the old ones; unknown or empty ones are ignored."""
    merged = merge_cookie(
        "A=1; B=2; C=3", {"B": "new", "Z": "anonymous", "C": "", "A": "1"}
    )
    assert merged == "A=1; B=new; C=3"


def test_describe_response_never_contains_cookie_values() -> None:
    """Only header names/values and the names of the cookies are summarised."""
    text = describe_response(
        {"server": "cloudflare", "content-length": "0"}, ["A", "B"]
    )
    assert text == "server=cloudflare, content-length=0, set-cookie=A,B"
    assert describe_response({}, []) == "no useful header"


# --------------------------------------------------------------------------- #
# CSV download
# --------------------------------------------------------------------------- #
async def test_download_writes_the_csv_and_sends_the_expected_headers(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    games_file: Path,
) -> None:
    """The export is downloaded with the cookie and the default User-Agent."""
    await setup_integration(mock_config_entry)

    assert games_file.read_bytes() == build_csv()
    assert mock_csv_download.call_count == 1
    method, url, _, headers = mock_csv_download.mock_calls[0]
    assert method == "GET"
    assert str(url) == CSV_URL
    assert headers["Cookie"] == COOKIE
    assert headers["User-Agent"] == DEFAULT_USER_AGENT
    assert headers["Referer"].endswith(f"/gamer/{GAMERTAG}")
    coordinator = get_coordinator(hass, mock_config_entry)
    assert coordinator.auth_failed is False
    assert coordinator.last_valid_update != "Unknown"


async def test_download_uses_the_user_agent_from_the_options(
    hass: HomeAssistant,
    make_entry: MakeEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """The configured browser User-Agent is sent, with whitespace normalised."""
    entry = make_entry(options={CONF_USER_AGENT: "  Mozilla/5.0\n (Test Browser) "})
    await setup_integration(entry)

    headers = mock_csv_download.mock_calls[0][3]
    assert headers["Cookie"] == COOKIE
    assert headers["User-Agent"] == "Mozilla/5.0 (Test Browser)"


async def test_options_override_the_cookie_of_the_entry_data(
    hass: HomeAssistant,
    make_entry: MakeEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """The cookie saved in the options takes precedence over the initial one."""
    entry = make_entry(options={CONF_GAMERTOKEN: "GamerToken=from-options"})
    await setup_integration(entry)

    assert mock_csv_download.mock_calls[0][3]["Cookie"] == "GamerToken=from-options"


@pytest.mark.parametrize("status", [401, 403])
async def test_access_denied_flags_the_authentication_and_notifies(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    notifications: Notifications,
    caplog: pytest.LogCaptureFixture,
    games_file: Path,
    status: int,
) -> None:
    """A 401/403 marks the cookie as expired and creates a persistent notification."""
    aioclient_mock.get(CSV_URL, status=status)
    await setup_integration(mock_config_entry)

    assert get_coordinator(hass, mock_config_entry).auth_failed is True
    assert not games_file.exists()
    assert f"Access denied by server (Error {status})" in caplog.text
    assert len(notifications.create) == 1
    call = notifications.create[0]
    assert call.data["notification_id"] == "ta_access_error"
    assert GAMERTAG in call.data["message"]
    assert call.data["title"] == "TrueAchievements: Access Error"


@pytest.mark.parametrize(
    "content",
    [
        b"<html><title>Just a moment...</title></html>",  # Cloudflare challenge
        b"x" * 2000,  # big enough, but not a TrueAchievements export
        b"",
    ],
)
async def test_unexpected_content_is_treated_as_an_expired_cookie(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    notifications: Notifications,
    caplog: pytest.LogCaptureFixture,
    games_file: Path,
    content: bytes,
) -> None:
    """A 200 answer that is not the CSV export counts as an expired cookie."""
    aioclient_mock.get(CSV_URL, content=content)
    await setup_integration(mock_config_entry)

    assert get_coordinator(hass, mock_config_entry).auth_failed is True
    assert not games_file.exists()
    assert "empty or malformed" in caplog.text
    assert len(notifications.create) == 1


async def test_auth_error_notification_can_be_disabled(
    hass: HomeAssistant,
    make_entry: MakeEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    notifications: Notifications,
) -> None:
    """With the toggle off, the failure is flagged but nothing is notified."""
    aioclient_mock.get(CSV_URL, status=403)
    entry = make_entry(data={CONF_NOTIFY_AUTH_ERROR: False})
    await setup_integration(entry)

    assert get_coordinator(hass, entry).auth_failed is True
    assert notifications.create == []


async def test_other_http_errors_do_not_flag_the_authentication(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    notifications: Notifications,
) -> None:
    """A server error is not an authentication problem."""
    aioclient_mock.get(CSV_URL, status=500)
    await setup_integration(mock_config_entry)

    assert get_coordinator(hass, mock_config_entry).auth_failed is False
    assert notifications.create == []


async def test_network_error_is_logged_and_does_not_break_the_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A network failure is logged; the integration still loads."""
    aioclient_mock.get(CSV_URL, exc=TimeoutError("boom"))
    await setup_integration(mock_config_entry)

    assert mock_config_entry.state.value == "loaded"
    assert "Network error during update: boom" in caplog.text
    assert get_coordinator(hass, mock_config_entry).auth_failed is False


async def test_recent_csv_is_not_downloaded_again(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    games_file: Path,
) -> None:
    """The one-hour safety lock reuses a CSV that was downloaded recently."""
    games_file.write_bytes(build_csv())

    await setup_integration(mock_config_entry)

    assert mock_csv_download.call_count == 0
    gamerscore = get_entity_id(hass, "sensor", "gamerscore")
    assert hass.states.get(gamerscore).state == str(TOTAL_GAMERSCORE)


async def test_old_csv_is_downloaded_again(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    games_file: Path,
) -> None:
    """A CSV older than one hour is replaced by a fresh download."""
    games_file.write_bytes(b"stale")
    two_hours_ago = time.time() - 2 * 3600
    os.utime(games_file, (two_hours_ago, two_hours_ago))

    await setup_integration(mock_config_entry)

    assert mock_csv_download.call_count == 1
    assert games_file.read_bytes() == build_csv()


async def test_downloads_stop_after_an_authentication_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """Once refused, the integration waits for new credentials instead of retrying."""
    aioclient_mock.get(CSV_URL, status=403)
    await setup_integration(mock_config_entry)
    coordinator = get_coordinator(hass, mock_config_entry)
    assert aioclient_mock.call_count == 1

    await coordinator.async_refresh()

    assert aioclient_mock.call_count == 1


async def test_reloading_with_new_credentials_downloads_again(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    notifications: Notifications,
) -> None:
    """Saving a fresh cookie reloads the entry and the download works."""
    aioclient_mock.get(CSV_URL, status=403)
    await setup_integration(mock_config_entry)
    assert get_coordinator(hass, mock_config_entry).auth_failed is True

    aioclient_mock.clear_requests()
    aioclient_mock.get(CSV_URL, content=build_csv())
    hass.config_entries.async_update_entry(
        mock_config_entry, options={CONF_GAMERTOKEN: "GamerToken=FRESH"}
    )
    await hass.async_block_till_done()

    assert aioclient_mock.call_count == 1
    assert aioclient_mock.mock_calls[0][3]["Cookie"] == "GamerToken=FRESH"
    assert get_coordinator(hass, mock_config_entry).auth_failed is False
    binary = get_entity_id(hass, "binary_sensor", "auth_status")
    assert hass.states.get(binary).state == "off"


# --------------------------------------------------------------------------- #
# CSV parsing
# --------------------------------------------------------------------------- #
async def test_excluded_apps_are_left_out_of_the_statistics(
    hass: HomeAssistant,
    make_entry: MakeEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """Names listed in the excluded apps option do not count in the totals."""
    entry = make_entry(data={CONF_EXCLUDED_APPS: " GEARS , , netflix"})
    await setup_integration(entry)

    def state(key: str) -> str:
        return hass.states.get(get_entity_id(hass, "sensor", key)).state

    assert state("gamerscore") == "3300"
    assert state("ta_score") == "7100"
    assert state("total_games") == "4"
    assert state("total_achievements") == "200"
    assert state("completion_percentage") == "59.0"


async def test_completion_is_zero_when_no_game_has_progress(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """Without any unlocked achievement, nothing is divided by zero."""
    rows = [game_row("Untouched Game", "Xbox One", total=50, gs_max=1000)]
    aioclient_mock.get(CSV_URL, content=build_csv(rows))
    await setup_integration(mock_config_entry)

    assert hass.states.get(get_entity_id(hass, "sensor", "total_games")).state == "0"
    pct = hass.states.get(get_entity_id(hass, "sensor", "completion_percentage"))
    assert pct.state == "0"


async def test_csv_numbers_are_parsed_tolerantly(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """Thousands separators are accepted and garbage values count as zero."""
    rows = [
        [
            "Big Game",
            "Xbox One",
            "5",
            "10",
            "1,234 G",
            "n/a",
            "9 999",
            "",
            "",
            "",
            "",
            "",
            "",
        ],
        ["Nameless", "Xbox One", "1", "1", "1", "1", "1", "1", "", "", "", "", ""],
    ]
    rows[1][0] = ""  # a row without a name is skipped
    aioclient_mock.get(CSV_URL, content=build_csv(rows))
    await setup_integration(mock_config_entry)

    assert hass.states.get(get_entity_id(hass, "sensor", "gamerscore")).state == "1234"
    assert hass.states.get(get_entity_id(hass, "sensor", "ta_score")).state == "9999"
    assert hass.states.get(get_entity_id(hass, "sensor", "total_games")).state == "1"


async def test_unreadable_csv_is_logged_and_gives_empty_statistics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    games_file: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A corrupted local CSV does not break the integration."""
    games_file.write_bytes(b"\x80\x81\x82" * 400)

    await setup_integration(mock_config_entry)

    assert "Error reading CSV" in caplog.text
    assert hass.states.get(get_entity_id(hass, "sensor", "gamerscore")).state == "0"


# --------------------------------------------------------------------------- #
# Matching the game being played
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("game", "platform", "achievements"),
    [
        # The row of the same platform wins over the first row with that name...
        ("Sea of Thieves", "Windows", "20 / 50"),
        ("Sea of Thieves", "Xbox One", "10 / 50"),
        # ...and a different platform label falls back to the name only.
        ("Forza Horizon 5", "Xbox Series X|S", "120 / 120"),
        ("Sea of Thieves", "Xbox Series X|S", "10 / 50"),
        # Without platform information, the first row with that name is used.
        ("Gears 5", None, "10 / 100"),
    ],
)
async def test_current_game_matching(
    hass: HomeAssistant,
    mock_config_entry_xbox: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    notifications: Notifications,
    game: str,
    platform: str | None,
    achievements: str,
) -> None:
    """Platform-specific rows are preferred, with a name-only fallback."""
    set_now_playing(hass, game, platform=platform)
    await setup_integration(mock_config_entry_xbox)

    state = hass.states.get(get_entity_id(hass, "sensor", "now_playing"))
    assert state.state == game
    assert state.attributes["achievements"] == achievements
    assert notifications.create == []


async def test_publisher_defaults_to_unknown(
    hass: HomeAssistant,
    mock_config_entry_xbox: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """The publisher is read from either attribute name, or reported as Unknown."""
    hass.states.async_set(XBOX_ENTITY, "Gears 5", {"Publisher": "Xbox Game Studios"})
    await setup_integration(mock_config_entry_xbox)
    state = hass.states.get(get_entity_id(hass, "sensor", "now_playing"))
    assert state.attributes["publisher"] == "Xbox Game Studios"

    set_now_playing(hass, "Gears 5", publisher=None)
    await hass.async_block_till_done()
    state = hass.states.get(get_entity_id(hass, "sensor", "now_playing"))
    assert state.attributes["publisher"] == "Unknown"


@pytest.mark.parametrize(
    "state", ["unavailable", "unknown", "idle", "Xbox 360 Dashboard"]
)
async def test_no_game_is_reported_for_inactive_states(
    hass: HomeAssistant,
    mock_config_entry_xbox: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    notifications: Notifications,
    state: str,
) -> None:
    """Idle consoles and the dashboard are not games."""
    hass.states.async_set(XBOX_ENTITY, state)
    await setup_integration(mock_config_entry_xbox)

    coordinator = get_coordinator(hass, mock_config_entry_xbox)
    assert coordinator.get_game_info_local() is None
    assert hass.states.get(get_entity_id(hass, "sensor", "now_playing")).state == (
        "offline_status"
    )
    assert notifications.create == []


async def test_no_game_without_a_tracked_entity(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """Without an Xbox entity configured, there is no current game."""
    await setup_integration(mock_config_entry)

    assert get_coordinator(hass, mock_config_entry).get_game_info_local() is None


async def test_no_game_when_the_tracked_entity_is_missing(
    hass: HomeAssistant,
    mock_config_entry_xbox: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """A configured entity that does not exist (yet) is handled gracefully."""
    await setup_integration(mock_config_entry_xbox)

    assert get_coordinator(hass, mock_config_entry_xbox).get_game_info_local() is None


async def test_walkthrough_and_url_fallbacks(
    hass: HomeAssistant,
    mock_config_entry_xbox: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """Rows without a walkthrough or a game URL get explicit placeholder values."""
    rows = [game_row("Plain Game", "Xbox One", won=1, total=2, gs=10, gs_max=20)]
    aioclient_mock.get(CSV_URL, content=build_csv(rows))
    set_now_playing(hass, "Plain Game")
    await setup_integration(mock_config_entry_xbox)

    attributes = hass.states.get(
        get_entity_id(hass, "sensor", "now_playing")
    ).attributes
    assert attributes["walkthrough_url"] == "not_available"
    assert attributes["game_url"] == "N/A"


# --------------------------------------------------------------------------- #
# Mapping
# --------------------------------------------------------------------------- #
async def test_bundled_mapping_is_used_without_a_user_file(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """The mapping shipped with the integration is the fallback."""
    await setup_integration(mock_config_entry)

    mapping = get_coordinator(hass, mock_config_entry).game_mapping

    assert mapping
    assert all(key == key.lower().strip() for key in mapping)


async def test_user_mapping_replaces_the_bundled_one(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    mapping_file: Path,
) -> None:
    """The user's mapping file wins over the bundled one, with normalised keys."""
    mapping_file.write_text(json.dumps({" Alias ": "Halo Infinite"}), encoding="utf-8")

    await setup_integration(mock_config_entry)

    assert get_coordinator(hass, mock_config_entry).game_mapping == {
        "alias": "Halo Infinite"
    }


@pytest.mark.parametrize("content", ["{not json", json.dumps(["a", "list"])])
async def test_invalid_user_mapping_is_ignored(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    mapping_file: Path,
    caplog: pytest.LogCaptureFixture,
    content: str,
) -> None:
    """A broken user mapping does not prevent the integration from working."""
    mapping_file.write_text(content, encoding="utf-8")

    await setup_integration(mock_config_entry)

    assert get_coordinator(hass, mock_config_entry).game_mapping == {}
    if content.startswith("{"):
        assert "Failed to load mapping file" in caplog.text


@pytest.mark.parametrize(
    ("name", "publisher", "platform", "expected"),
    [
        ("Plain", "x", "y", "Target"),  # a simple alias
        ("Rare Game", "rare", "windows", "By Combo"),  # "publisher|platform"
        ("Rare Game", "rare", "xbox one", "By Publisher"),
        ("Rare Game", "other", "windows", "By Platform"),
        ("Rare Game", "other", "xbox one", "Fallback"),  # the "unknown" entry
        ("Lonely Game", "other", "xbox one", "Lonely Game"),  # no entry matches
        ("Not Mapped", "x", "y", "Not Mapped"),
    ],
)
async def test_mapped_name_resolution(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    name: str,
    publisher: str,
    platform: str,
    expected: str,
) -> None:
    """Aliases can depend on the publisher and on the platform."""
    await setup_integration(mock_config_entry)
    coordinator = get_coordinator(hass, mock_config_entry)
    coordinator.game_mapping = {
        "plain": "Target",
        "rare game": {
            "Rare|Windows": "By Combo",
            "rare": "By Publisher",
            "windows": "By Platform",
            "unknown": "Fallback",
        },
        "lonely game": {"somebody": "else"},
    }

    resolved = coordinator._resolve_mapped_name(name, publisher, platform)

    assert resolved == expected


# --------------------------------------------------------------------------- #
# "Game not matching" notifications
# --------------------------------------------------------------------------- #
async def test_unmatched_game_creates_one_notification(
    hass: HomeAssistant,
    mock_config_entry_xbox: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    notifications: Notifications,
) -> None:
    """An unknown game is reported once, with instructions to fix the mapping."""
    set_now_playing(hass, "Brand New Game", platform="Xbox Series X|S")
    await setup_integration(mock_config_entry_xbox)

    assert len(notifications.create) == 1
    call = notifications.create[0]
    assert call.data["notification_id"] == "ta_fix_Brand_New_Game"
    assert call.data["title"] == "TrueAchievements: Action Required"
    assert "Brand New Game" in call.data["message"]
    assert "mapping.json" in call.data["message"]

    # Refreshing again does not repeat the notification.
    await get_coordinator(hass, mock_config_entry_xbox).async_refresh()
    await hass.async_block_till_done()
    assert len(notifications.create) == 1


async def test_unmatched_game_notification_can_be_disabled(
    hass: HomeAssistant,
    make_entry: MakeEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    notifications: Notifications,
) -> None:
    """With the toggle off, unknown games are silently ignored."""
    set_now_playing(hass, "Brand New Game")
    entry = make_entry(
        data={"now_playing_entity": XBOX_ENTITY, CONF_NOTIFY_MAPPING: False}
    )
    await setup_integration(entry)

    assert notifications.create == []


async def test_translated_notifications_follow_the_language(
    hass: HomeAssistant,
    mock_config_entry_xbox: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    notifications: Notifications,
) -> None:
    """Notification texts use the language of Home Assistant."""
    aioclient_mock.get(CSV_URL, status=403)
    hass.config.language = "fr"
    await setup_integration(mock_config_entry_xbox)

    assert notifications.create[0].data["title"] == "TrueAchievements : erreur d'accès"
    assert "a expiré" in notifications.create[0].data["message"]


async def test_translations_fall_back_to_english(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
) -> None:
    """An unsupported language uses the English texts."""
    hass.config.language = "xx"
    await setup_integration(mock_config_entry)
    coordinator = get_coordinator(hass, mock_config_entry)

    texts = await hass.async_add_executor_job(coordinator._load_notify_translations)

    assert texts["auth_error_title"] == "TrueAchievements: Access Error"


async def test_broken_translation_files_give_no_texts(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    tmp_path: Path,
) -> None:
    """Unreadable or incomplete translation files fall back to built-in texts."""
    await setup_integration(mock_config_entry)
    coordinator = get_coordinator(hass, mock_config_entry)
    translations = tmp_path / "translations"
    translations.mkdir()
    coordinator.translations_dir = translations

    # No file at all.
    assert (
        await hass.async_add_executor_job(coordinator._load_notify_translations) == {}
    )
    # Invalid JSON, then a file without the "common" section.
    (translations / "en.json").write_text("{broken", encoding="utf-8")
    assert (
        await hass.async_add_executor_job(coordinator._load_notify_translations) == {}
    )
    (translations / "en.json").write_text(json.dumps({"config": {}}), encoding="utf-8")
    assert (
        await hass.async_add_executor_job(coordinator._load_notify_translations) == {}
    )


@pytest.mark.parametrize(
    "texts",
    [{}, {"auth_error_message": "{not_a_known_key}"}],
)
async def test_auth_error_message_falls_back_to_the_default_text(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    notifications: Notifications,
    texts: dict[str, str],
) -> None:
    """A missing or invalid translation still produces a readable message."""
    await setup_integration(mock_config_entry)
    coordinator = get_coordinator(hass, mock_config_entry)

    coordinator.notify_translations = texts
    coordinator._send_error_notification()
    await hass.async_block_till_done()

    assert notifications.create[0].data["message"] == (
        f"The cookie for **{GAMERTAG}** has expired."
    )


@pytest.mark.parametrize("texts", [{}, {"mapping_message": "{not_a_known_key}"}])
async def test_mapping_message_falls_back_to_the_default_text(
    hass: HomeAssistant,
    mock_config_entry_xbox: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    notifications: Notifications,
    texts: dict[str, str],
) -> None:
    """A missing or invalid translation still produces a readable message."""
    set_now_playing(hass, "Brand New Game")
    await setup_integration(mock_config_entry_xbox)
    coordinator = get_coordinator(hass, mock_config_entry_xbox)
    notifications.create.clear()
    coordinator._notified_games.clear()

    coordinator.notify_translations = texts
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert "Brand New Game" in notifications.create[0].data["message"]
    assert "mapping.json" in notifications.create[0].data["message"]


async def test_reload_mapping_logs_the_number_of_entries(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_csv_download: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    mapping_file: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Reloading the mapping reports how many entries were read."""
    await setup_integration(mock_config_entry)
    mapping_file.write_text(json.dumps({"a": "A", "b": "B"}), encoding="utf-8")

    with caplog.at_level(logging.INFO):
        await get_coordinator(hass, mock_config_entry).async_reload_mapping()

    assert "Mapping reloaded: 2 entries" in caplog.text


# --------------------------------------------------------------------------- #
# Cookies renewed by the server
# --------------------------------------------------------------------------- #
async def test_renewed_cookies_are_stored_and_reused(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A cookie renewed by the server replaces the old one for the next download."""
    aioclient_mock.get(
        CSV_URL,
        content=build_csv(),
        cookies={"GamerToken": "renewed"},
    )
    with caplog.at_level(logging.INFO):
        await setup_integration(mock_config_entry)

    assert "renewed: GamerToken" in caplog.text
    assert "renewed" not in COOKIE
    coordinator = get_coordinator(hass, mock_config_entry)
    assert "GamerToken=renewed" in coordinator._session_cookie
    assert COOKIE not in caplog.text

    # Same cookie sent back by the server: nothing new to store.
    caplog.clear()
    await coordinator._remember_renewed_cookies({"GamerToken": "renewed"}, "test")
    assert "renewed: none" in caplog.text

    # A new coordinator (restart) starts from the stored cookie...
    coordinator._session_loaded = False
    coordinator._session_cookie = ""
    await coordinator._load_session_cookie()
    assert "GamerToken=renewed" in coordinator._session_cookie

    # ...unless the user entered a new cookie.
    coordinator.gamer_token = "GamerToken=brand-new"
    await coordinator._load_session_cookie()
    assert coordinator._session_cookie == ""


async def test_file_only_mode_never_downloads(
    hass: HomeAssistant,
    make_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    setup_integration: SetupIntegration,
    games_file: Path,
) -> None:
    """In local file mode nothing is requested: the CSV is only read."""
    games_file.write_bytes(build_csv())
    old = time.time() - 7200
    os.utime(games_file, (old, old))
    entry = make_entry(options={CONF_FILE_ONLY: True, CONF_GAMERTOKEN: ""})
    await setup_integration(entry)

    assert aioclient_mock.call_count == 0
    coordinator = get_coordinator(hass, entry)
    assert coordinator.file_only is True
    assert coordinator.auth_failed is False
    assert coordinator.data["total_games"] > 0
