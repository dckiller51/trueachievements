"""Coordinator for the TrueAchievements integration."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_COMPLETED_GAMES,
    ATTR_COMPLETION_PCT,
    ATTR_GAMERSCORE,
    ATTR_LOST_COMPLETIONS,
    ATTR_TA_SCORE,
    ATTR_TOTAL_ACHIEVEMENTS,
    ATTR_TOTAL_GAMES,
    CONF_EXCLUDED_APPS,
    CONF_FILE_ONLY,
    CONF_GAMER_ID,
    CONF_GAMERTAG,
    CONF_GAMERTOKEN,
    CONF_GAMES_FILE,
    CONF_MAPPING_FILE,
    CONF_NOTIFY_AUTH_ERROR,
    CONF_NOTIFY_COMPLETION_LOST,
    CONF_NOTIFY_MAPPING,
    CONF_NOW_PLAYING_ENTITY,
    CONF_USER_AGENT,
    DEFAULT_GAMES_FILE,
    DEFAULT_MAPPING_FILE,
    DEFAULT_NOTIFY_AUTH_ERROR,
    DEFAULT_NOTIFY_COMPLETION_LOST,
    DEFAULT_NOTIFY_MAPPING,
    DEFAULT_USER_AGENT,
    DOMAIN,
    DOWNLOAD_INTERVAL,
    EVENT_COMPLETION_LOST,
    ISSUE_URL_MAPPING,
    URL_EXPORT_COLLECTION,
)

if TYPE_CHECKING:
    from aiohttp import ClientSession
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1


def parse_cookie(cookie: str) -> dict[str, str]:
    """Split a ``name=value; name=value`` cookie string, keeping the order."""
    pairs: dict[str, str] = {}
    for pair in cookie.split(";"):
        name, sep, value = pair.strip().partition("=")
        if name and sep:
            pairs[name] = value
    return pairs


def merge_cookie(cookie: str, updates: dict[str, str]) -> str:
    """Replace, in ``cookie``, the cookies renewed by the server.

    Only cookies that are already present are replaced: the server also sends
    anonymous session cookies that must not overwrite a valid login.
    """
    pairs = parse_cookie(cookie)
    for name, value in updates.items():
        if name in pairs and value:
            pairs[name] = value
    return "; ".join(f"{name}={value}" for name, value in pairs.items())


def describe_response(headers: Any, cookie_names: list[str]) -> str:
    """Summarise a response for the logs, without any cookie value."""
    parts = []
    for name in (
        "server",
        "content-type",
        "content-length",
        "cf-mitigated",
        "location",
    ):
        value = headers.get(name)
        if value:
            parts.append(f"{name}={value}")
    if cookie_names:
        parts.append(f"set-cookie={','.join(cookie_names)}")
    return ", ".join(parts) or "no useful header"


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
        self.file_only: bool = False
        self.user_agent: str = DEFAULT_USER_AGENT
        self._store: Store[dict[str, str]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._session_cookie: str = ""
        self._session_loaded: bool = False
        self._completed_store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.completed"
        )
        self._completed_games: dict[str, dict[str, str]] | None = None
        self._lost_keys: set[str] = set()
        self._notified_lost: dict[str, str] = {}
        self.lost_completions: list[dict[str, Any]] = []
        self.games_file: Path = Path("")
        self.excluded_apps: list[str] = []
        self.notify_mapping: bool = DEFAULT_NOTIFY_MAPPING
        self.notify_auth_error: bool = DEFAULT_NOTIFY_AUTH_ERROR
        self.notify_completion_lost: bool = DEFAULT_NOTIFY_COMPLETION_LOST
        conf_mapping = str(
            entry.options.get(
                CONF_MAPPING_FILE,
                entry.data.get(CONF_MAPPING_FILE, DEFAULT_MAPPING_FILE),
            )
        )
        self.mapping_file: Path = Path(self.hass.config.path(conf_mapping))
        self.game_mapping: dict[str, Any] = {}
        self.translations_dir: Path = Path(__file__).parent / "translations"
        self.notify_translations: dict[str, str] = {}

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
        self.file_only = bool(opts.get(CONF_FILE_ONLY, dat.get(CONF_FILE_ONLY, False)))
        user_agent = " ".join(
            str(opts.get(CONF_USER_AGENT, dat.get(CONF_USER_AGENT, ""))).split()
        )
        self.user_agent = user_agent or DEFAULT_USER_AGENT

        conf_path = str(dat.get(CONF_GAMES_FILE, DEFAULT_GAMES_FILE))
        self.games_file = Path(self.hass.config.path(conf_path))

        excluded_raw: str = opts.get(
            CONF_EXCLUDED_APPS, dat.get(CONF_EXCLUDED_APPS, "")
        )
        self.excluded_apps = [
            app.strip().lower() for app in excluded_raw.split(",") if app.strip()
        ]
        self.notify_mapping = bool(
            opts.get(
                CONF_NOTIFY_MAPPING,
                dat.get(CONF_NOTIFY_MAPPING, DEFAULT_NOTIFY_MAPPING),
            )
        )
        self.notify_auth_error = bool(
            opts.get(
                CONF_NOTIFY_AUTH_ERROR,
                dat.get(CONF_NOTIFY_AUTH_ERROR, DEFAULT_NOTIFY_AUTH_ERROR),
            )
        )
        self.notify_completion_lost = bool(
            opts.get(
                CONF_NOTIFY_COMPLETION_LOST,
                dat.get(CONF_NOTIFY_COMPLETION_LOST, DEFAULT_NOTIFY_COMPLETION_LOST),
            )
        )

    async def _handle_state_change(self, _event: Any) -> None:
        """Trigger a refresh when the Xbox game status changes."""
        _LOGGER.debug("Xbox game change detected, refreshing TrueAchievements data")
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from TA with a one-hour safety lock or use local CSV."""
        self._update_local_config()
        self.game_mapping = await self.hass.async_add_executor_job(
            self._load_mapping_file
        )
        self.notify_translations = await self.hass.async_add_executor_job(
            self._load_notify_translations
        )

        now = dt_util.now()
        should_download = True

        if self.games_file.exists():
            mtime = self.games_file.stat().st_mtime
            last_modified = dt_util.as_local(dt_util.utc_from_timestamp(mtime))
            self.last_valid_update = last_modified.strftime("%Y-%m-%d %H:%M")
            if (now - last_modified) < DOWNLOAD_INTERVAL:
                should_download = False

        if should_download and not self.auth_failed and not self.file_only:
            await self._download_csv(now)

        game_info = self.get_game_info_local()
        data = await self.hass.async_add_executor_job(
            self._read_and_process_csv, game_info
        )
        games = data.pop("_games", None)
        if games:
            await self._async_update_lost_completions(games)
        data[ATTR_LOST_COMPLETIONS] = self.lost_completions

        if "current_game_details" not in data or not data["current_game_details"]:
            data["current_game_details"] = {}
        data["current_game_details"]["entity_picture"] = (game_info or {}).get("image")
        data["last_update"] = self.last_valid_update
        return data

    async def _async_update_lost_completions(
        self, games: dict[str, dict[str, Any]]
    ) -> None:
        """Find the games completed at 100% that are no longer complete.

        TrueAchievements only gives the current progress, so every game seen
        at 100% is remembered. When such a game is below 100% again (new
        achievements, usually a DLC), it is reported until it is completed
        again. On the very first run, the current completions are only
        recorded: nothing can be reported yet.
        """
        if self._completed_games is None:
            stored = await self._completed_store.async_load()
            first_run = not stored
            self._completed_games = dict((stored or {}).get("games", {}))
            self._lost_keys = set((stored or {}).get("lost", []))
        else:
            first_run = False

        known = self._completed_games
        changed = False
        lost: list[dict[str, Any]] = []

        for key, game in games.items():
            if game["completed"]:
                if key not in known:
                    known[key] = {"name": game["name"], "platform": game["platform"]}
                    changed = True
            elif key in known and not first_run:
                lost.append(
                    {
                        "key": key,
                        "name": game["name"],
                        "platform": game["platform"],
                        "achievements": f"{game['ach_won']} / {game['ach_max']}",
                        "missing_achievements": game["ach_max"] - game["ach_won"],
                        "gamerscore": f"{game['gs_won']} G / {game['gs_max']} G",
                        "game_url": game["url"] or "N/A",
                    }
                )

        lost.sort(key=lambda game: str(game["name"]).lower())
        self.lost_completions = lost
        lost_keys = {game["key"] for game in lost}

        for game in lost:
            if game["key"] not in self._lost_keys:
                _LOGGER.info(
                    "%s (%s) is no longer completed: %s achievements",
                    game["name"],
                    game["platform"],
                    game["achievements"],
                )
                self.hass.bus.async_fire(
                    EVENT_COMPLETION_LOST,
                    {
                        "gamertag": self.gamer_tag,
                        **{k: v for k, v in game.items() if k != "key"},
                    },
                )
        if lost_keys != self._lost_keys:
            self._lost_keys = lost_keys
            changed = True

        if changed:
            await self._completed_store.async_save(
                {"games": known, "lost": sorted(lost_keys)}
            )

        self._handle_lost_completion_notifications(lost)

    def _handle_lost_completion_notifications(self, lost: list[dict[str, Any]]) -> None:
        """Create one notification per lost game, dismiss it once completed again."""
        current = {game["key"] for game in lost}
        for key in list(self._notified_lost):
            if key not in current:
                self.hass.add_job(
                    self.hass.services.async_call,
                    "persistent_notification",
                    "dismiss",
                    {"notification_id": self._notified_lost.pop(key)},
                )

        if not self.notify_completion_lost:
            return

        title = self.notify_translations.get(
            "completion_lost_title", "TrueAchievements: New achievements"
        )
        default_tpl = (
            "**{game}** ({platform}) is no longer completed at 100%: "
            "{achievements} achievements ({missing} missing). [Open on "
            "TrueAchievements]({url})"
        )
        message_tpl = self.notify_translations.get(
            "completion_lost_message", default_tpl
        )
        for game in lost:
            if game["key"] in self._notified_lost:
                continue
            values = {
                "game": game["name"],
                "platform": game["platform"],
                "achievements": game["achievements"],
                "missing": game["missing_achievements"],
                "url": game["game_url"],
            }
            try:
                message = message_tpl.format(**values)
            except Exception:  # pylint: disable=broad-exception-caught  # noqa: BLE001
                message = default_tpl.format(**values)

            slug = re.sub(r"[^a-z0-9]+", "_", game["key"].lower()).strip("_")
            notification_id = f"ta_lost_{slug}"
            self._notified_lost[game["key"]] = notification_id
            self.hass.add_job(
                self.hass.services.async_call,
                "persistent_notification",
                "create",
                {
                    "title": title,
                    "message": message,
                    "notification_id": notification_id,
                },
            )

    def _token_fingerprint(self) -> str:
        """Identify the cookie the user entered, without storing it."""
        return hashlib.sha256(self.gamer_token.encode("utf-8")).hexdigest()

    async def _load_session_cookie(self) -> None:
        """Reuse the cookie renewed by the server, unless the user entered a new one."""
        self._session_loaded = True
        data = await self._store.async_load()
        if data and data.get("base") == self._token_fingerprint():
            self._session_cookie = data.get("cookie", "")
        else:
            self._session_cookie = ""

    async def _remember_renewed_cookies(
        self, updates: dict[str, str], source: str
    ) -> None:
        """Keep the cookies renewed by the server for the next downloads."""
        current = self._session_cookie or self.gamer_token
        merged = merge_cookie(current, updates)
        renewed = sorted(
            name
            for name, value in updates.items()
            if parse_cookie(current).get(name, value) != value
        )
        _LOGGER.info(
            "Cookies sent by the server (%s): %s; renewed: %s",
            source,
            ", ".join(sorted(updates)) or "none",
            ", ".join(renewed) or "none",
        )
        if renewed:
            self._session_cookie = merged
            await self._store.async_save(
                {"base": self._token_fingerprint(), "cookie": merged}
            )

    def _request_headers(self) -> dict[str, str]:
        """Return the headers of a browser-like request with the session cookie."""
        return {
            "User-Agent": self.user_agent,
            "Cookie": self._session_cookie or self.gamer_token,
            "Referer": f"https://www.trueachievements.com/gamer/{self.gamer_tag}",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
        }

    async def _download_csv(self, now: Any) -> None:
        """Handle the CSV download logic using the full session cookie provided by the user."""
        if not self._session_loaded:
            await self._load_session_cookie()
        headers = self._request_headers()
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
                        await self._remember_renewed_cookies(
                            {
                                name: morsel.value
                                for name, morsel in resp.cookies.items()
                            },
                            "download",
                        )
                    else:
                        _LOGGER.error(
                            "Received file is empty or malformed: %s bytes, no CSV (%s)",
                            len(content),
                            describe_response(resp.headers, list(resp.cookies)),
                        )
                        self.auth_failed = True
                        self._send_error_notification()
                elif resp.status in (401, 403):
                    _LOGGER.error(
                        "Access denied by server (Error %s) (%s)",
                        resp.status,
                        describe_response(resp.headers, list(resp.cookies)),
                    )
                    self.auth_failed = True
                    self._send_error_notification()
        except Exception as err:  # pylint: disable=broad-exception-caught  # noqa: BLE001
            _LOGGER.error("Network error during update: %s", err)

    def _get_mapping_file(self) -> Path:
        """Return the user mapping file if it exists, else the bundled one."""
        if self.mapping_file.exists():
            return self.mapping_file
        return Path(__file__).parent / "mapping.json"

    def _load_mapping_file(self) -> dict[str, Any]:
        """Load mapping and normalize keys to lowercase."""
        mapping_file = self._get_mapping_file()
        if not mapping_file.exists():
            return {}
        try:
            with open(mapping_file, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {k.lower().strip(): v for k, v in data.items()}
                return {}
        except Exception:  # pylint: disable=broad-exception-caught  # noqa: BLE001
            _LOGGER.error("Failed to load mapping file: %s", mapping_file)
            return {}

    async def async_reload_mapping(self) -> None:
        """Force reload of the mapping file and refresh the data."""
        self.game_mapping = await self.hass.async_add_executor_job(
            self._load_mapping_file
        )
        _LOGGER.info("Mapping reloaded: %s entries", len(self.game_mapping))
        await self.async_request_refresh()

    def _load_notify_translations(self) -> dict[str, str]:
        """Load notification strings from the translation files.

        Tries the HA-configured language first, then falls back to English.
        Strings live under the "common" key so they can be shared with any
        notification (persistent or mobile), independently of the config_flow
        and entity translations.
        """
        language = self.hass.config.language
        for lang in (language, "en"):
            path = self.translations_dir / f"{lang}.json"
            if not path.exists():
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                common = data.get("common", {})
                if isinstance(common, dict) and common:
                    return {str(k): str(v) for k, v in common.items()}
            except Exception:  # pylint: disable=broad-exception-caught  # noqa: BLE001
                _LOGGER.debug("Failed to load notify translations for lang=%s", lang)
        return {}

    async def async_receive_csv(self, content: bytes) -> bool:
        """Store a CSV export sent by an external tool (webhook)."""
        if len(content) <= 1000 or b"Game name" not in content:
            _LOGGER.warning("Rejected an uploaded file that is not a CSV export")
            return False
        await self.hass.async_add_executor_job(self._write_file, content)
        self.last_valid_update = dt_util.now().strftime("%Y-%m-%d %H:%M")
        self.auth_failed = False
        _LOGGER.info("CSV export received (%s bytes)", len(content))
        await self.async_request_refresh()
        return True

    def _write_file(self, content: bytes) -> None:
        """Physically save the CSV file."""
        self.games_file.parent.mkdir(parents=True, exist_ok=True)
        self.games_file.write_bytes(content)

    def _send_error_notification(self) -> None:
        """Send a persistent notification for expired credentials."""
        if not self.notify_auth_error:
            return

        title = self.notify_translations.get(
            "auth_error_title", "TrueAchievements: Access Error"
        )
        message_tpl = self.notify_translations.get(
            "auth_error_message", "The cookie for **{gamer_tag}** has expired."
        )
        try:
            message = message_tpl.format(gamer_tag=self.gamer_tag)
        except Exception:  # pylint: disable=broad-exception-caught  # noqa: BLE001
            message = f"The cookie for **{self.gamer_tag}** has expired."

        self.hass.add_job(
            self.hass.services.async_call,
            "persistent_notification",
            "create",
            {
                "message": message,
                "title": title,
                "notification_id": "ta_access_error",
            },
        )

    def now_playing_image_entity_id(self) -> str | None:
        """Return the image entity that goes with the Xbox Now Playing sensor."""
        eid_sensor = self.entry.options.get(
            CONF_NOW_PLAYING_ENTITY, self.entry.data.get(CONF_NOW_PLAYING_ENTITY)
        )
        if not eid_sensor:
            return None
        return str(eid_sensor).replace("sensor.", "image.")

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

        lookup_name = self._resolve_mapped_name(current_name, current_pub, current_plat)
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
        games: dict[str, dict[str, Any]] = {}
        match_found = False

        if not self.games_file.exists():
            return {}

        name_only_fallback: dict[str, Any] | None = None

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

                    if row_vals["ach_max"] > 0:
                        url = row.get("Game URL") or row.get("URL") or ""
                        key = url or f"{name_csv}|{row.get('Platform', '')}"
                        games[key] = {
                            **row_vals,
                            "name": name_csv,
                            "platform": row.get("Platform", ""),
                            "url": url,
                            "completed": row_vals["ach_won"] >= row_vals["ach_max"],
                        }

                    # Matching Logic — name+platform match takes priority,
                    # falling back to name-only if no row matches the
                    # platform (TA can dynamically change the platform
                    # label based on the last console used)
                    if not match_found and target_name_low == name_csv.lower().strip():
                        if not current_plat or (
                            current_plat in plat_csv or plat_csv in current_plat
                        ):
                            current_game_stats = self._build_current_game_dict(
                                row, current_name, current_pub.title(), row_vals
                            )
                            match_found = True
                        elif name_only_fallback is None:
                            name_only_fallback = self._build_current_game_dict(
                                row, current_name, current_pub.title(), row_vals
                            )

                    # Accumulation
                    if row_vals["ach_won"] > 0:
                        stats["total_gs"] += row_vals["gs_won"]
                        stats["total_ta"] += row_vals["ta_won"]
                        stats["total_ach"] += row_vals["ach_won"]
                        stats["max_ach"] += row_vals["ach_max"]
                        stats["started"] += 1
                        if row_vals["ach_won"] >= row_vals["ach_max"] > 0:
                            stats["completed"] += 1

                if not match_found and name_only_fallback is not None:
                    current_game_stats = name_only_fallback
                    match_found = True

            self._handle_not_found_notification(
                lookup_name, match_found, current_name, safe_info
            )

        except Exception as err:  # pylint: disable=broad-exception-caught  # noqa: BLE001
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
            "_games": games,
        }

    def _resolve_mapped_name(self, name: str, publisher: str, platform: str) -> str:
        """Resolve game name using Publisher and Platform if necessary."""
        name_low = name.lower().strip()
        pub_low = publisher.lower().strip()
        plat_low = platform.lower().strip()

        if name_low in self.game_mapping:
            mapping_val = self.game_mapping[name_low]
            if isinstance(mapping_val, dict):
                lower_map = {str(k).lower().strip(): v for k, v in mapping_val.items()}
                combo_key = f"{pub_low}|{plat_low}"
                if combo_key in lower_map:
                    return str(lower_map[combo_key])
                if pub_low in lower_map:
                    return str(lower_map[pub_low])
                if plat_low in lower_map:
                    return str(lower_map[plat_low])

                return str(lower_map.get("unknown", name))
            return str(mapping_val)
        return name

    def _get_row_values(self, row: dict[str, str]) -> dict[str, int]:
        """Convert CSV row values to integers safely (Fixes E722)."""

        def _s_int(key: str) -> int:
            try:
                return int(re.sub(r"[^\d]", "", row.get(key, "0") or "0"))
            except ValueError, TypeError:
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
        """Handle 'Game not found' notifications: create on miss, dismiss on match."""
        notify_key = current_name or lookup_name
        notification_id = f"ta_fix_{notify_key.replace(' ', '_')}"

        # Game matched again after a mapping fix: dismiss the pending notification
        if match_found:
            if notify_key in self._notified_games:
                self._notified_games.discard(notify_key)
                self.hass.add_job(
                    self.hass.services.async_call,
                    "persistent_notification",
                    "dismiss",
                    {"notification_id": notification_id},
                )
            return

        if not self.notify_mapping:
            return
        if not lookup_name or notify_key in self._notified_games:
            return
        if current_name.lower() in (
            "unavailable",
            "unknown",
            "idle",
            "offline_status",
        ):
            return

        self._notified_games.add(notify_key)

        title = self.notify_translations.get(
            "mapping_title",
            "TrueAchievements: Access Error".replace("Access Error", "Action Required"),
        )
        message_tpl = self.notify_translations.get(
            "mapping_message",
            "Game **{game}** ({platform}) not matching. "
            "Publisher: {publisher}. "
            "Add it to `trueachievements/mapping.json` "
            "and press the reload button.",
        )
        try:
            message = message_tpl.format(
                game=current_name,
                platform=info.get("platform"),
                publisher=info.get("publisher"),
                issue_url=ISSUE_URL_MAPPING,
            )
        except Exception:  # pylint: disable=broad-exception-caught  # noqa: BLE001
            message = (
                f"Game **{current_name}** ({info.get('platform')}) not matching. "
                f"Publisher: {info.get('publisher')}. "
                "Add it to `trueachievements/mapping.json` "
                "and press the reload button."
            )

        self.hass.add_job(
            self.hass.services.async_call,
            "persistent_notification",
            "create",
            {
                "title": title,
                "message": message,
                "notification_id": notification_id,
            },
        )
