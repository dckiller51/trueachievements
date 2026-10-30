"""Test the sensor of the games that are no longer completed at 100%."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.core import Event, HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.trueachievements.const import (
    CONF_FILE_ONLY,
    CONF_NOTIFY_COMPLETION_LOST,
    EVENT_COMPLETION_LOST,
)

from .common import get_coordinator, get_entity_id
from .conftest import MakeEntry, Notifications, SetupIntegration
from .const import BASE, build_csv, game_row

FORZA_URL = f"{BASE}/Forza/achievements"


def forza(won: int, total: int) -> list[str]:
    """Return the Forza Horizon 5 row with the given progress."""
    return game_row(
        "Forza Horizon 5",
        "Xbox One",
        won=won,
        total=total,
        gs=won * 10,
        gs_max=total * 10,
        url=FORZA_URL,
    )


def gears(won: int, total: int) -> list[str]:
    """Return a Gears 5 row without URL (key built from name and platform)."""
    return game_row("Gears 5", "Xbox One", won=won, total=total)


async def refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Re-read the CSV file."""
    await get_coordinator(hass, entry).async_refresh()
    await hass.async_block_till_done()


async def test_lost_completion_is_reported_then_cleared(
    hass: HomeAssistant,
    make_entry: MakeEntry,
    setup_integration: SetupIntegration,
    games_file: Path,
) -> None:
    """A game back below 100% is listed, then removed once completed again."""
    events: list[Event[dict[str, Any]]] = []
    hass.bus.async_listen(EVENT_COMPLETION_LOST, events.append)
    games_file.write_bytes(build_csv([forza(120, 120), gears(100, 100)]))
    entry = await setup_integration(make_entry(data={CONF_FILE_ONLY: True}))
    entity_id = get_entity_id(hass, "sensor", "lost_completions")

    assert hass.states.get(entity_id).state == "0"
    assert hass.states.get(entity_id).attributes["games"] == []

    # New DLC achievements for both games
    games_file.write_bytes(build_csv([forza(120, 135), gears(100, 110)]))
    await refresh(hass, entry)

    state = hass.states.get(entity_id)
    assert state.state == "2"
    assert state.attributes["game_names"] == ["Forza Horizon 5", "Gears 5"]
    assert state.attributes["games"][0] == {
        "name": "Forza Horizon 5",
        "platform": "Xbox One",
        "achievements": "120 / 135",
        "missing_achievements": 15,
        "gamerscore": "1200 G / 1350 G",
        "game_url": FORZA_URL,
    }
    assert [event.data["name"] for event in events] == ["Forza Horizon 5", "Gears 5"]

    # Progress on Forza: still listed, but no new event
    games_file.write_bytes(build_csv([forza(130, 135), gears(100, 110)]))
    await refresh(hass, entry)
    assert hass.states.get(entity_id).attributes["games"][0]["achievements"] == (
        "130 / 135"
    )
    assert len(events) == 2

    # Forza completed again
    games_file.write_bytes(build_csv([forza(135, 135), gears(100, 110)]))
    await refresh(hass, entry)
    assert hass.states.get(entity_id).state == "1"
    assert hass.states.get(entity_id).attributes["game_names"] == ["Gears 5"]


async def test_games_never_completed_are_not_reported(
    hass: HomeAssistant,
    make_entry: MakeEntry,
    setup_integration: SetupIntegration,
    games_file: Path,
) -> None:
    """Only the games seen at 100% can be reported."""
    games_file.write_bytes(build_csv([forza(50, 120)]))
    entry = await setup_integration(make_entry(data={CONF_FILE_ONLY: True}))

    games_file.write_bytes(build_csv([forza(50, 135)]))
    await refresh(hass, entry)

    assert hass.states.get(get_entity_id(hass, "sensor", "lost_completions")).state == (
        "0"
    )


async def test_completed_games_are_remembered_across_restarts(
    hass: HomeAssistant,
    make_entry: MakeEntry,
    setup_integration: SetupIntegration,
    games_file: Path,
) -> None:
    """The completed games are stored, so a loss is seen after a reload."""
    games_file.write_bytes(build_csv([forza(120, 120)]))
    entry = await setup_integration(make_entry(data={CONF_FILE_ONLY: True}))
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    games_file.write_bytes(build_csv([forza(120, 135)]))
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(get_entity_id(hass, "sensor", "lost_completions"))
    assert state.state == "1"
    assert state.attributes["game_names"] == ["Forza Horizon 5"]


async def test_lost_completion_notification_is_created_then_dismissed(
    hass: HomeAssistant,
    make_entry: MakeEntry,
    setup_integration: SetupIntegration,
    games_file: Path,
    notifications: Notifications,
) -> None:
    """One notification per lost game, dismissed once it is completed again."""
    games_file.write_bytes(build_csv([forza(120, 120)]))
    entry = await setup_integration(make_entry(data={CONF_FILE_ONLY: True}))

    games_file.write_bytes(build_csv([forza(120, 135)]))
    await refresh(hass, entry)
    await refresh(hass, entry)

    assert len(notifications.create) == 1
    data = notifications.create[0].data
    assert (
        data["notification_id"]
        == "ta_lost_https_www_trueachievements_com_game_forza_achievements"
    )
    assert "Forza Horizon 5" in data["message"]
    assert "120 / 135" in data["message"]
    assert "15 missing" in data["message"]
    assert FORZA_URL in data["message"]

    games_file.write_bytes(build_csv([forza(135, 135)]))
    await refresh(hass, entry)

    assert len(notifications.dismiss) == 1
    assert notifications.dismiss[0].data["notification_id"] == data["notification_id"]


async def test_lost_completion_notification_follows_the_language(
    hass: HomeAssistant,
    make_entry: MakeEntry,
    setup_integration: SetupIntegration,
    games_file: Path,
    notifications: Notifications,
) -> None:
    """The notification text comes from the translation files."""
    hass.config.language = "fr"
    games_file.write_bytes(build_csv([forza(120, 120)]))
    entry = await setup_integration(make_entry(data={CONF_FILE_ONLY: True}))

    games_file.write_bytes(build_csv([forza(120, 135)]))
    await refresh(hass, entry)

    data = notifications.create[0].data
    assert data["title"] == "TrueAchievements : nouveaux succès"
    assert "n'est plus terminé à 100 %" in data["message"]


async def test_lost_completion_notification_can_be_disabled(
    hass: HomeAssistant,
    make_entry: MakeEntry,
    setup_integration: SetupIntegration,
    games_file: Path,
    notifications: Notifications,
) -> None:
    """No notification when the option is off; the sensor still lists the game."""
    games_file.write_bytes(build_csv([forza(120, 120)]))
    entry = await setup_integration(
        make_entry(data={CONF_FILE_ONLY: True, CONF_NOTIFY_COMPLETION_LOST: False})
    )

    games_file.write_bytes(build_csv([forza(120, 135)]))
    await refresh(hass, entry)

    assert notifications.create == []
    state = hass.states.get(get_entity_id(hass, "sensor", "lost_completions"))
    assert state.state == "1"


async def test_broken_notification_text_falls_back_to_the_default(
    hass: HomeAssistant,
    make_entry: MakeEntry,
    setup_integration: SetupIntegration,
    games_file: Path,
    notifications: Notifications,
) -> None:
    """A translation with an unknown placeholder gives the English text."""
    games_file.write_bytes(build_csv([forza(120, 120)]))
    entry = await setup_integration(make_entry(data={CONF_FILE_ONLY: True}))
    coordinator = get_coordinator(hass, entry)

    games_file.write_bytes(build_csv([forza(120, 135)]))
    original = coordinator._load_notify_translations
    coordinator._load_notify_translations = lambda: {  # type: ignore[method-assign]
        **original(),
        "completion_lost_message": "{unknown}",
    }
    await refresh(hass, entry)

    assert "is no longer completed at 100%" in notifications.create[0].data["message"]


async def test_event_is_not_fired_again_after_a_restart(
    hass: HomeAssistant,
    make_entry: MakeEntry,
    setup_integration: SetupIntegration,
    games_file: Path,
    notifications: Notifications,
) -> None:
    """A loss already reported does not fire the event again after a reload.

    The notification is created again, as notifications do not survive a restart.
    """
    events: list[Event[dict[str, Any]]] = []
    hass.bus.async_listen(EVENT_COMPLETION_LOST, events.append)
    games_file.write_bytes(build_csv([forza(120, 120)]))
    entry = await setup_integration(make_entry(data={CONF_FILE_ONLY: True}))
    games_file.write_bytes(build_csv([forza(120, 135)]))
    await refresh(hass, entry)

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert len(events) == 1
    assert len(notifications.create) == 2
