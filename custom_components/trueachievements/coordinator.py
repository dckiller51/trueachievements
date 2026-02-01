"""Coordinator for the TrueAchievements integration."""

from __future__ import annotations

import csv
import logging
import os
import re
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_COMPLETED_GAMES,
    ATTR_COMPLETION_PCT,
    ATTR_GAMERSCORE,
    ATTR_TA_SCORE,
    ATTR_TOTAL_ACHIEVEMENTS,
    ATTR_TOTAL_GAMES,
    CONF_EXCLUDED_APPS,
    CONF_GAMER_ID,
    CONF_GAMERTAG,
    CONF_GAMERTOKEN,
    CONF_GAMES_FILE,
    CONF_NOW_PLAYING_ENTITY,
    DEFAULT_GAMES_FILE,
    DOMAIN,
    GAME_NAME_MAPPING,
    ISSUE_URL_MAPPING,
    URL_EXPORT_COLLECTION,
)

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


class TrueAchievementsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching data from TrueAchievements with Anti-Ban safety."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, session: ClientSession
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(minutes=30)
        )
        self.entry: ConfigEntry = entry
        self.session: ClientSession = session
        self.auth_failed: bool = False
        self.last_valid_update: str = "Unknown"
        self._notified_games: set[str] = set()

        self.gamer_id: str = ""
        self.gamer_tag: str = ""
        self.gamer_token: str = ""
        self.games_file: Path = Path("")
        self.excluded_apps: list[str] = []

        self._update_local_config()

        now_playing_eid: str | None = entry.options.get(
            CONF_NOW_PLAYING_ENTITY, entry.data.get(CONF_NOW_PLAYING_ENTITY)
        )
        if now_playing_eid:
            async_track_state_change_event(
                hass, [now_playing_eid], self._handle_state_change
            )

    def _update_local_config(self) -> None:
        """Fetch settings from data or options entries."""
        opts = self.entry.options
        dat = self.entry.data
        self.gamer_id = str(dat.get(CONF_GAMER_ID, ""))
        self.gamer_tag = str(dat.get(CONF_GAMERTAG, ""))
        self.gamer_token = str(opts.get(CONF_GAMERTOKEN, dat.get(CONF_GAMERTOKEN, "")))

        conf_path = str(dat.get(CONF_GAMES_FILE, DEFAULT_GAMES_FILE))
        self.games_file = Path(self.hass.config.path(conf_path))

        excluded_raw: str = opts.get(
            CONF_EXCLUDED_APPS, dat.get(CONF_EXCLUDED_APPS, "")
        )
        self.excluded_apps = [
            app.strip().lower() for app in excluded_raw.split(",") if app.strip()
        ]

    async def _handle_state_change(self, _event: Any) -> None:
        """Trigger a refresh when the Xbox game status changes."""
        _LOGGER.debug("Xbox game change detected, refreshing TrueAchievements data")
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from TA with 24h safety lock or use local CSV."""
        self._update_local_config()
        now = dt_util.now()
        should_download = True

        # --- 24H CACHE LOGIC ---
        if self.games_file.exists():
            mtime = os.path.getmtime(self.games_file)
            last_modified = dt_util.as_local(dt_util.utc_from_timestamp(mtime))
            self.last_valid_update = last_modified.strftime("%Y-%m-%d %H:%M")

            if (now - last_modified) < timedelta(hours=24):
                should_download = False
                _LOGGER.debug("Local CSV is fresh (less than 24h old)")

        if should_download and not self.auth_failed:
            _LOGGER.info("Attempting daily update from TrueAchievements...")
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Cookie": f"TrueGamingIdentity={self.gamer_token}",
                "Referer": f"https://www.trueachievements.com/gamer/{self.gamer_tag}",
            }

            try:
                url_csv = URL_EXPORT_COLLECTION.format(self.gamer_id)
                async with self.session.get(
                    url_csv, headers=headers, timeout=ClientTimeout(total=20)
                ) as resp:

                    if resp.status == 200:
                        content = await resp.read()
                        # STRICT CONTENT CHECK: Ensure it's a real CSV with headers
                        if len(content) > 1000 and b"Game name" in content:
                            await self.hass.async_add_executor_job(
                                self._write_file, content
                            )
                            self.last_valid_update = now.strftime("%Y-%m-%d %H:%M")
                            self.auth_failed = (
                                False  # Reset binary sensor to OFF (Normal)
                            )
                            _LOGGER.info("CSV updated successfully")
                        else:
                            # Received 200 OK but content is not CSV (e.g., login page)
                            _LOGGER.error(
                                "Invalid CSV content received (Cookie probably expired)"
                            )
                            self.auth_failed = (
                                True  # This turns your binary_sensor ON (Problem)
                            )
                            self._send_error_notification()

                    elif resp.status in (401, 403):
                        _LOGGER.error(
                            "TA Authentication error (Status: %s)", resp.status
                        )
                        self.auth_failed = (
                            True  # This turns your binary_sensor ON (Problem)
                        )
                        self._send_error_notification()

                        # ANTI-BAN SAFETY: Touch the file even on failure to wait 24h
                        if self.games_file.exists():
                            await self.hass.async_add_executor_job(
                                os.utime, self.games_file, None
                            )

            except Exception as err:  # pylint: disable=broad-exception-caught
                _LOGGER.error("Network error during update: %s", err)

        # Always process local data
        game_info = self.get_game_info_local()
        raw_game_name = (game_info or {}).get("name")
        game_image = (game_info or {}).get("image")

        data = await self.hass.async_add_executor_job(
            self._read_and_process_csv, raw_game_name
        )

        if "current_game_details" not in data or not data["current_game_details"]:
            data["current_game_details"] = {}

        data["current_game_details"]["entity_picture"] = game_image

        data["last_update"] = self.last_valid_update
        return data

    def _write_file(self, content: bytes) -> None:
        """Physically save the CSV file."""
        self.games_file.parent.mkdir(parents=True, exist_ok=True)
        self.games_file.write_bytes(content)

    def _send_error_notification(self) -> None:
        """Notification for expired token."""
        self.hass.add_job(
            self.hass.services.async_call,
            "persistent_notification",
            "create",
            {
                "message": f"The cookie for **{self.gamer_tag}** has expired.",
                "title": "TrueAchievements: Access Error",
                "notification_id": "ta_access_error",
            },
        )

    def get_game_info_local(self) -> dict[str, Any] | None:
        """Retrieve current game name from the linked Xbox entity."""
        eid_sensor: str | None = self.entry.options.get(
            CONF_NOW_PLAYING_ENTITY, self.entry.data.get(CONF_NOW_PLAYING_ENTITY)
        )
        if not eid_sensor:
            return None

        state = self.hass.states.get(eid_sensor)
        if state and state.state not in ("unavailable", "unknown", "idle"):
            img_eid = eid_sensor.replace("sensor.", "image.")
            img_state = self.hass.states.get(img_eid)
            return {
                "name": state.state,
                "image": (
                    img_state.attributes.get("entity_picture") if img_state else None
                ),
            }
        return None

    def _read_and_process_csv(self, current_game_name: str | None) -> dict[str, Any]:
        """Parse the local CSV file and calculate statistics."""
        total_gs, total_ta, total_ach, max_ach, completed, started = 0, 0, 0, 0, 0, 0
        current_game_stats: dict[str, Any] = {}

        lookup_name: str | None = current_game_name
        if current_game_name is not None:
            lookup_name = GAME_NAME_MAPPING.get(current_game_name, current_game_name)

        if not self.games_file.exists():
            return {}

        try:
            with open(self.games_file, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    return {}

                reader.fieldnames = [
                    n.replace('"', "").strip() for n in reader.fieldnames
                ]

                def s_int(val: Any) -> int:
                    try:
                        clean_v = re.sub(r"[^\d]", "", str(val))
                        return int(clean_v) if clean_v else 0
                    except (ValueError, TypeError):
                        return 0

                for row in reader:
                    row = {
                        k.replace('"', "").strip(): (
                            str(v).replace('"', "").strip() if v else ""
                        )
                        for k, v in row.items()
                    }

                    name_in_csv = row.get("Game name", "")
                    plat = row.get("Platform", "")
                    if not name_in_csv:
                        continue

                    if "app" in plat or any(
                        x in name_in_csv.lower() for x in self.excluded_apps
                    ):
                        _LOGGER.debug("Excluding: %s (%s)", name_in_csv, plat)
                        continue

                    gs_won = s_int(row.get("GamerScore Won (incl. DLC)"))
                    ta_won = s_int(row.get("TrueAchievement Won (incl. DLC)"))
                    ach_won = s_int(row.get("Achievements Won (incl. DLC)"))
                    ach_max = s_int(row.get("Max Achievements (incl. DLC)"))

                    if (
                        lookup_name
                        and lookup_name.lower().strip() == name_in_csv.lower().strip()
                    ):
                        walkthrough = row.get("Walkthrough", "").strip()
                        current_game_stats = {
                            "name": current_game_name,
                            "platform": plat,
                            "achievements": f"{ach_won} / {ach_max}",
                            "gamerscore": f"{gs_won} G",
                            "ta_score": f"{ta_won} TA",
                            "hours_played": f"{row.get('Hours Played', '0')} h",
                            "game_completion": f"{row.get('My Completion Percentage', '0')}%",
                            "game_ratio": row.get("My Ratio", "1.00"),
                            "game_url": row.get("Game URL") or row.get("URL") or "N/A",
                            "walkthrough_url": (
                                walkthrough
                                if walkthrough and walkthrough.startswith("http")
                                else None
                            ),
                        }

                    if ach_won > 0:
                        total_gs += gs_won
                        total_ta += ta_won
                        total_ach += ach_won
                        max_ach += ach_max
                        started += 1
                        if ach_won >= ach_max > 0:
                            completed += 1

            if (
                lookup_name
                and not current_game_stats
                and lookup_name not in self._notified_games
            ):
                self._notified_games.add(lookup_name)
                self.hass.add_job(
                    self.hass.services.async_call,
                    "persistent_notification",
                    "create",
                    {
                        "title": "TrueAchievements: Action Required",
                        "message": f"Game **{lookup_name}** not matching. [Report here]({ISSUE_URL_MAPPING})",
                        "notification_id": f"ta_fix_{lookup_name.replace(' ', '_')}",
                    },
                )

        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOGGER.error("Error reading CSV: %s", err)

        return {
            ATTR_GAMERSCORE: total_gs,
            ATTR_TA_SCORE: total_ta,
            ATTR_TOTAL_GAMES: started,
            ATTR_COMPLETED_GAMES: completed,
            ATTR_TOTAL_ACHIEVEMENTS: total_ach,
            ATTR_COMPLETION_PCT: (
                round((total_ach / max_ach * 100), 2) if max_ach > 0 else 0
            ),
            "current_game_name": current_game_name or "offline_status",
            "current_game_details": current_game_stats,
        }
