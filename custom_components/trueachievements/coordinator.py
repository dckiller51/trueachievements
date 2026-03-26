"""Coordinator for the TrueAchievements integration."""

from __future__ import annotations

import csv
import json
import logging
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
        self.mapping_file: Path = Path(__file__).parent / "mapping.json"
        self.game_mapping: dict[str, Any] = {}

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
        self.game_mapping = await self.hass.async_add_executor_job(self._load_mapping)

        now = dt_util.now()
        should_download = True

        if self.games_file.exists():
            mtime = self.games_file.stat().st_mtime
            last_modified = dt_util.as_local(dt_util.utc_from_timestamp(mtime))
            self.last_valid_update = last_modified.strftime("%Y-%m-%d %H:%M")
            if (now - last_modified) < timedelta(hours=24):
                should_download = False

        if should_download and not self.auth_failed:
            await self._download_csv(now)

        game_info = self.get_game_info_local()
        data = await self.hass.async_add_executor_job(
            self._read_and_process_csv, game_info
        )

        if "current_game_details" not in data or not data["current_game_details"]:
            data["current_game_details"] = {}
        data["current_game_details"]["entity_picture"] = (game_info or {}).get("image")
        data["last_update"] = self.last_valid_update
        return data

    async def _download_csv(self, now: Any) -> None:
        """Handle the CSV download logic."""
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
                    if len(content) > 1000 and b"Game name" in content:
                        await self.hass.async_add_executor_job(
                            self._write_file, content
                        )
                        self.last_valid_update = now.strftime("%Y-%m-%d %H:%M")
                        self.auth_failed = False
                    else:
                        self.auth_failed = True
                        self._send_error_notification()
                elif resp.status in (401, 403):
                    self.auth_failed = True
                    self._send_error_notification()
        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOGGER.error("Network error during update: %s", err)

    def _load_mapping(self) -> dict[str, Any]:
        """Load mapping and normalize keys to lowercase."""
        if not self.mapping_file.exists():
            return {}
        try:
            with open(self.mapping_file, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {k.lower().strip(): v for k, v in data.items()}
                return {}
        except Exception:  # pylint: disable=broad-exception-caught
            return {}

    def _write_file(self, content: bytes) -> None:
        """Physically save the CSV file."""
        self.games_file.parent.mkdir(parents=True, exist_ok=True)
        self.games_file.write_bytes(content)

    def _send_error_notification(self) -> None:
        """Send a persistent notification for expired credentials."""
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
        """Get info from Xbox sensor with dual-case publisher support."""
        eid_sensor = self.entry.options.get(
            CONF_NOW_PLAYING_ENTITY, self.entry.data.get(CONF_NOW_PLAYING_ENTITY)
        )
        if not eid_sensor:
            return None
        state = self.hass.states.get(eid_sensor)
        if state and state.state not in (
            "unavailable",
            "unknown",
            "idle",
            "Xbox 360 Dashboard",
        ):
            pub = (
                state.attributes.get("publisher")
                or state.attributes.get("Publisher")
                or "Unknown"
            )
            img_eid = eid_sensor.replace("sensor.", "image.")
            img_state = self.hass.states.get(img_eid)
            return {
                "name": state.state,
                "platform": state.attributes.get("platform"),
                "publisher": pub,
                "image": (
                    img_state.attributes.get("entity_picture") if img_state else None
                ),
            }
        return None

    def _read_and_process_csv(self, game_info: dict[str, Any] | None) -> dict[str, Any]:
        """Parse CSV with strict prioritised matching logic."""
        safe_info = game_info or {}
        current_name = safe_info.get("name", "")
        current_plat = str(safe_info.get("platform") or "").lower()
        current_pub = str(safe_info.get("publisher") or "Unknown").lower().strip()

        lookup_name = self._resolve_mapped_name(current_name, current_pub)
        target_name_low = lookup_name.lower().strip()

        stats = {
            "total_gs": 0,
            "total_ta": 0,
            "total_ach": 0,
            "max_ach": 0,
            "completed": 0,
            "started": 0,
        }
        current_game_stats: dict[str, Any] = {}
        match_found = False

        if not self.games_file.exists():
            return {}

        try:
            with open(self.games_file, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames:
                    reader.fieldnames = [
                        n.replace('"', "").strip() for n in reader.fieldnames
                    ]

                for row in reader:
                    row = {
                        k.strip(): (str(v).strip() if v else "") for k, v in row.items()
                    }
                    name_csv = row.get("Game name", "")
                    plat_csv = row.get("Platform", "").lower()

                    if (
                        not name_csv
                        or "app" in plat_csv
                        or any(x in name_csv.lower() for x in self.excluded_apps)
                    ):
                        continue

                    # Safe conversion
                    row_vals = self._get_row_values(row)

                    # Matching Logic
                    if not match_found and target_name_low == name_csv.lower().strip():
                        if not current_plat or (
                            current_plat in plat_csv or plat_csv in current_plat
                        ):
                            current_game_stats = self._build_current_game_dict(
                                row, current_name, current_pub.title(), row_vals
                            )
                            match_found = True

                    # Accumulation
                    if row_vals["ach_won"] > 0:
                        stats["total_gs"] += row_vals["gs_won"]
                        stats["total_ta"] += row_vals["ta_won"]
                        stats["total_ach"] += row_vals["ach_won"]
                        stats["max_ach"] += row_vals["ach_max"]
                        stats["started"] += 1
                        if row_vals["ach_won"] >= row_vals["ach_max"] > 0:
                            stats["completed"] += 1

            self._handle_not_found_notification(
                lookup_name, match_found, current_name, safe_info
            )

        except Exception as err:  # pylint: disable=broad-exception-caught
            _LOGGER.error("Error reading CSV: %s", err)

        return {
            ATTR_GAMERSCORE: stats["total_gs"],
            ATTR_TA_SCORE: stats["total_ta"],
            ATTR_TOTAL_GAMES: stats["started"],
            ATTR_COMPLETED_GAMES: stats["completed"],
            ATTR_TOTAL_ACHIEVEMENTS: stats["total_ach"],
            ATTR_COMPLETION_PCT: (
                round((stats["total_ach"] / stats["max_ach"] * 100), 2)
                if stats["max_ach"] > 0
                else 0
            ),
            "current_game_name": current_name or "offline_status",
            "current_game_details": current_game_stats,
        }

    def _resolve_mapped_name(self, name: str, publisher: str) -> str:
        """Resolve game name from mapping file."""
        name_low = name.lower().strip()
        if name_low in self.game_mapping:
            mapping_val = self.game_mapping[name_low]
            if isinstance(mapping_val, dict):
                lower_pub_map = {
                    str(k).lower().strip(): v for k, v in mapping_val.items()
                }
                return str(lower_pub_map.get(publisher, name))
            return str(mapping_val)
        return name

    def _get_row_values(self, row: dict[str, str]) -> dict[str, int]:
        """Convert CSV row values to integers safely (Fixes E722)."""

        def _s_int(key: str) -> int:
            try:
                return int(re.sub(r"[^\d]", "", row.get(key, "0") or "0"))
            except (ValueError, TypeError):
                return 0

        return {
            "ach_won": _s_int("Achievements Won (incl. DLC)"),
            "ach_max": _s_int("Max Achievements (incl. DLC)"),
            "gs_won": _s_int("GamerScore Won (incl. DLC)"),
            "gs_max": _s_int("Max Gamerscore (incl. DLC)"),
            "ta_won": _s_int("TrueAchievement Won (incl. DLC)"),
            "ta_max": _s_int("Max TrueAchievement (incl. DLC)"),
        }

    def _build_current_game_dict(
        self, row: dict[str, str], name: str, pub: str, vals: dict[str, int]
    ) -> dict[str, Any]:
        """Build the details dictionary for the current game (Fixes R0915)."""
        walkthrough = row.get("Walkthrough", "").strip()
        return {
            "name": name,
            "platform": row.get("Platform"),
            "publisher": pub,
            "achievements": f"{vals['ach_won']} / {vals['ach_max']}",
            "gamerscore": f"{vals['gs_won']} G / {vals['gs_max']} G",
            "ta_score": f"{vals['ta_won']} TA / {vals['ta_max']} TA",
            "hours_played": f"{row.get('Hours Played', '0')} h",
            "game_completion": f"{row.get('My Completion Percentage', '0')}%",
            "game_ratio": row.get("My Ratio", "1.00"),
            "game_url": row.get("Game URL") or row.get("URL") or "N/A",
            "walkthrough_url": (
                walkthrough if walkthrough.startswith("http") else "not_available"
            ),
        }

    def _handle_not_found_notification(
        self, lookup_name: str, match_found: bool, current_name: str, info: dict
    ) -> None:
        """Handle 'Game not found' notifications."""
        if lookup_name and not match_found and lookup_name not in self._notified_games:
            if current_name.lower() not in (
                "unavailable",
                "unknown",
                "idle",
                "offline_status",
            ):
                self._notified_games.add(lookup_name)
                self.hass.add_job(
                    self.hass.services.async_call,
                    "persistent_notification",
                    "create",
                    {
                        "title": "TrueAchievements: Action Required",
                        "message": (
                            f"Game **{lookup_name}** ({info.get('platform')}) not matching. "
                            f"Publisher: {info.get('publisher')}. [Report here]({ISSUE_URL_MAPPING})"
                        ),
                        "notification_id": f"ta_fix_{lookup_name.replace(' ', '_')}",
                    },
                )
