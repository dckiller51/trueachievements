"""Coordinator for the TrueAchievements integration."""

from __future__ import annotations

import csv
import logging
import re
from datetime import timedelta
from pathlib import Path
from typing import Any, TYPE_CHECKING

from aiohttp import ClientTimeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    DOMAIN, CONF_GAMER_ID,
    CONF_GAMERTAG,
    CONF_GAMERTOKEN,
    CONF_NOW_PLAYING_ENTITY,
    CONF_EXCLUDED_APPS,
    CONF_GAMES_FILE,
    DEFAULT_GAMES_FILE,
    URL_EXPORT_COLLECTION,
    ATTR_GAMERSCORE,
    ATTR_TA_SCORE,
    ATTR_TOTAL_GAMES,
    ATTR_COMPLETED_GAMES,
    ATTR_TOTAL_ACHIEVEMENTS,
    ATTR_COMPLETION_PCT
)

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

class TrueAchievementsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching data from TrueAchievements."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        session: ClientSession
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=30)
        )
        self.entry: ConfigEntry = entry
        self.session: ClientSession = session
        self.auth_failed: bool = False

        # Attributes initialized in _update_local_config
        self.gamer_id: str = ""
        self.gamer_tag: str = ""
        self.gamer_token: str = ""
        self.games_file: Path = Path("")
        self.excluded_apps: list[str] = []

        # Initial configuration load
        self._update_local_config()

        # Track Xbox Now Playing entity
        now_playing_eid: str | None = entry.options.get(
            CONF_NOW_PLAYING_ENTITY,
            entry.data.get(CONF_NOW_PLAYING_ENTITY)
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

        excluded_raw: str = opts.get(CONF_EXCLUDED_APPS, dat.get(CONF_EXCLUDED_APPS, ""))
        self.excluded_apps = [
            app.strip().lower() for app in excluded_raw.split(",") if app.strip()
        ]

    async def _handle_state_change(self, _event: Any) -> None:
        """Trigger a refresh when the Xbox game status changes."""
        _LOGGER.debug("Xbox game change detected, refreshing TrueAchievements data")
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch and process data from TrueAchievements."""
        self._update_local_config()

        if self.auth_failed:
            raise UpdateFailed("Token expired. Update it in settings.")

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Cookie": f"TrueGamingIdentity={self.gamer_token}",
            "Referer": f"https://www.trueachievements.com/gamer/{self.gamer_tag}",
        }

        try:
            url_csv = URL_EXPORT_COLLECTION.format(self.gamer_id)
            async with self.session.get(
                url_csv,
                headers=headers,
                timeout=ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    self.auth_failed = False
                    content = await resp.read()
                    await self.hass.async_add_executor_job(self._write_file, content)
                elif resp.status in (401, 403):
                    self.auth_failed = True
                    self._send_error_notification()
                    raise UpdateFailed("Access denied by TrueAchievements (Invalid Token)")

            game_info = self.get_game_info_local()
            return await self.hass.async_add_executor_job(
                self._read_and_process_csv,
                game_info["name"] if game_info else None
            )
        except Exception as e:
            if not isinstance(e, UpdateFailed):
                _LOGGER.error("Error updating TrueAchievements: %s", e)
                raise UpdateFailed(f"Update error: {e}") from e
            raise e

    def _write_file(self, content: bytes) -> None:
        """Physically save the CSV file to disk."""
        self.games_file.parent.mkdir(parents=True, exist_ok=True)
        self.games_file.write_bytes(content)

    def _send_error_notification(self) -> None:
        """Send a system notification when the session token expires."""
        self.hass.async_create_task(
            self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "message": f"The cookie for **{self.gamer_tag}** has expired.",
                    "title": "TrueAchievements: Cookie Expired",
                    "notification_id": "ta_cookie_expired",
                },
            )
        )

    def get_game_info_local(self) -> dict[str, Any] | None:
        """Retrieve current game name from the linked Xbox entity."""
        eid_sensor: str | None = self.entry.options.get(
            CONF_NOW_PLAYING_ENTITY,
            self.entry.data.get(CONF_NOW_PLAYING_ENTITY)
        )
        if not eid_sensor:
            return None

        state = self.hass.states.get(eid_sensor)
        if state and state.state not in ("unavailable", "unknown", "idle"):
            img_eid = eid_sensor.replace("sensor.", "image.")
            img_state = self.hass.states.get(img_eid)
            return {
                "name": state.state,
                "image": img_state.attributes.get("entity_picture") if img_state else None
            }
        return None

    def _read_and_process_csv(self, current_game_name: str | None) -> dict[str, Any]:
        """Parse the CSV and extract global and per-game statistics."""
        total_gs, total_ta, total_ach, max_ach, completed, started = 0, 0, 0, 0, 0, 0
        current_game_stats: dict[str, Any] = {}

        if not self.games_file.exists():
            _LOGGER.warning("CSV file not found at %s", self.games_file)
            return {}

        with open(self.games_file, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return {}

            reader.fieldnames = [n.replace('"', '').strip() for n in reader.fieldnames]

            def s_int(v: Any) -> int:
                """Safely convert string to integer."""
                try:
                    clean_v = re.sub(r'[^\d]', '', str(v))
                    return int(clean_v) if clean_v else 0
                except (ValueError, TypeError):
                    return 0

            for row in reader:
                row = {k: (v.replace('"', '').strip() if v else "") for k, v in row.items()}
                name = row.get("Game name", "")
                plat = row.get("Platform", "")

                if "app" in plat.lower() or any(x in name.lower() for x in self.excluded_apps):
                    continue

                gs_won = s_int(row.get("GamerScore Won (incl. DLC)"))
                ta_won = s_int(row.get("TrueAchievement Won (incl. DLC)"))
                ach_won = s_int(row.get("Achievements Won (incl. DLC)"))
                ach_max = s_int(row.get("Max Achievements (incl. DLC)"))

                if current_game_name and current_game_name.lower() == name.lower():
                    completion_raw = row.get("My Completion Percentage", "0")
                    completion_display = (
                        completion_raw
                        if "%" in str(completion_raw)
                        else f"{completion_raw}%"
                    )

                    game_url = row.get("Game URL") or row.get("URL") or "N/A"
                    raw_hours = str(row.get("Hours Played", "0")).strip()
                    hours_display = (
                        f"{raw_hours} h"
                        if raw_hours not in ("N/A", "0")
                        else "0 h"
                    )

                    current_game_stats = {
                        "platform": plat,
                        "achievements": f"{ach_won} / {ach_max}",
                        "gamerscore": f"{gs_won}G",
                        "ta_score": f"{ta_won} TA",
                        "hours_played": hours_display,
                        "game_completion": completion_display,
                        "game_ratio": row.get("My Ratio", "1.00"),
                        "game_url": game_url,
                    }

                if ach_won > 0:
                    total_gs += gs_won
                    total_ta += ta_won
                    total_ach += ach_won
                    max_ach += ach_max
                    started += 1
                    if ach_won >= ach_max > 0:
                        completed += 1

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
            "current_game_details": current_game_stats
        }
