"""Constants for the TrueAchievements integration."""

NAME = "TrueAchievements"
DOMAIN = "trueachievements"
VERSION = "2026.2.1"

# GitHub URLs
ISSUE_URL = "https://github.com/dckiller51/trueachievements/issues"
ISSUE_URL_MAPPING = "https://github.com/dckiller51/trueachievements/issues/2"

# Configuration keys
CONF_AUTH_STATUS = "auth_status"
CONF_GAMERTAG = "gamertag"
CONF_GAMER_ID = "gamer_id"
CONF_GAMERTOKEN = "gamertoken"
CONF_NOW_PLAYING_ENTITY = "now_playing_entity"
CONF_EXCLUDED_APPS = "excluded_apps"
CONF_GAMES_FILE = "games_file"

# Default file paths
# Note: These are usually stored within the /config/ folder of Home Assistant
DEFAULT_GAMES_FILE = "trueachievements/games.csv"
DEFAULT_ACHIEVEMENTS_FILE = "trueachievements/achievements.csv"

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

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
