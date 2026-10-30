"""Constants for the TrueAchievements integration."""

from datetime import timedelta

NAME = "TrueAchievements"
DOMAIN = "trueachievements"
VERSION = "2026.10.2"

# Minimum delay between two downloads of the TrueAchievements CSV export.
DOWNLOAD_INTERVAL = timedelta(hours=1)

# GitHub URLs
ISSUE_URL = "https://github.com/dckiller51/trueachievements/issues"
ISSUE_URL_MAPPING = "https://github.com/dckiller51/trueachievements/issues/new?template=game-mapping.yml"

# Configuration keys
CONF_AUTH_STATUS = "auth_status"
CONF_GAMERTAG = "gamertag"
CONF_GAMER_ID = "gamer_id"
CONF_GAMERTOKEN = "gamertoken"
CONF_USER_AGENT = "user_agent"
CONF_FILE_ONLY = "file_only"
CONF_WEBHOOK_ID = "webhook_id"

# Largest CSV accepted by the webhook (the real file is about 0.5 MB).
MAX_UPLOAD_BYTES = 5_000_000
CONF_MAPPING_FILE = "mapping_file"
CONF_NOW_PLAYING_ENTITY = "now_playing_entity"
CONF_EXCLUDED_APPS = "excluded_apps"
CONF_GAMES_FILE = "games_file"
CONF_NOTIFY_MAPPING = "notify_mapping"
CONF_NOTIFY_AUTH_ERROR = "notify_auth_error"
CONF_NOTIFY_COMPLETION_LOST = "notify_completion_lost"

# Defaults for notification toggles
DEFAULT_NOTIFY_MAPPING = True
DEFAULT_NOTIFY_AUTH_ERROR = True
DEFAULT_NOTIFY_COMPLETION_LOST = True

# Browser identity used when no custom User-Agent is configured.
# Users can paste their own browser's User-Agent in the options.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Default file paths
# Note: These are usually stored within the /config/ folder of Home Assistant
DEFAULT_GAMES_FILE = "trueachievements/games.csv"
DEFAULT_ACHIEVEMENTS_FILE = "trueachievements/achievements.csv"
DEFAULT_MAPPING_FILE = "trueachievements/mapping.json"

# TrueAchievements URLs
# Use gamecollection export to get all game stats for a specific GamerID
URL_EXPORT_COLLECTION = (
    "https://www.trueachievements.com/download.aspx?type=gamecollection&id={}"
)

# Sensor attributes
ATTR_GAMERSCORE = "gamerscore"
ATTR_TA_SCORE = "ta_score"
ATTR_COMPLETION_PCT = "completion_percentage"
ATTR_TOTAL_GAMES = "total_games"
ATTR_COMPLETED_GAMES = "completed_games"
ATTR_TOTAL_ACHIEVEMENTS = "total_achievements"
ATTR_LOST_COMPLETIONS = "lost_completions"

# Event fired when a game completed at 100% is no longer complete
# (new achievements added to the game, usually with a DLC).
EVENT_COMPLETION_LOST = f"{DOMAIN}_completion_lost"

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
