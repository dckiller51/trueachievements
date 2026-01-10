"""Constants for the TrueAchievements integration."""

NAME = "TrueAchievements"
DOMAIN = "trueachievements"
VERSION = "2026.1.1"

ISSUE_URL = "https://github.com/dckiller51/trueachievements/issues"

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
URL_EXPORT_COLLECTION = "https://www.trueachievements.com/download.aspx?type=gamecollection&id={}"

# Sensor attributes
ATTR_GAMERSCORE = "gamerscore"
ATTR_TA_SCORE = "ta_score"
ATTR_COMPLETION_PCT = "completion_percentage"
ATTR_TOTAL_GAMES = "total_games"
ATTR_COMPLETED_GAMES = "completed_games"
ATTR_TOTAL_ACHIEVEMENTS = "total_achievements"

# Game Name Mapping (Xbox Name: TrueAchievements Name)
# This handles discrepancies between Xbox Live's "Now Playing" status
# and how games are indexed in the TA CSV export.
GAME_NAME_MAPPING = {

    "Minecraft for Android": "Minecraft (Android)"
}

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration!
If you have any issues with this you need to open an issue here:
{ISSUE_URL}
-------------------------------------------------------------------
"""
