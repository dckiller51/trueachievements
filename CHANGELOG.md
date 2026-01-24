# Changelog

All notable changes to this project will be documented in this file.

<!--next-version-placeholder-->

## 2026.1.4

- **Added** Anti-Ban Security Lock: Implemented a 24-hour physical file-age check. The integration now strictly limits TrueAchievements server requests to once per day, regardless of Home Assistant restarts.

- **Added** Dynamic Status Attributes: Added last_update attribute to both the "Now Playing" sensor and "Connection Status" binary sensor to track data freshness.

- **Improved** Resilience: Added a content validation check to prevent overwriting local data with empty or invalid (HTML) responses during network errors or Cloudflare challenges.

- **Fixed** Indentation & Stability: Resolved an IndentationError in the binary sensor platform and improved error logging for authentication failures.

## 2026.1.3

- **Improved** Configuration Flow: The "Now Playing" Xbox entity is now optional. You can also update or add this entity at any time via the Integration Options without reinstalling.

- **Improved** Entity Selector: Added a dedicated filter to the configuration UI that only shows Xbox integration sensors, making it easier to find your console
- **Fixed** Entity Naming: Standardized entity_id to English (e.g., total_games instead of total_de_jeux) to follow Home Assistant best practices and ensure automation stability.

## 2026.1.2

- **Added** Global Mapping Issue: Added a dedicated [GitHub Issue]({ISSUE_URL}) to report missing game name mappings.
- **Added** Automated Notifications: The integration now notifies you via Home Assistant if a game name mismatch is detected, providing a direct link to report it.
- **Fixed** Game matching: Updated `GAME_NAME_MAPPING` to correct the inconsistency for **Roblox**.
- **Fixed** Stability: Fixed a thread-safety issue where notifications could cause the integration to crash during CSV processing.

## 2026.1.1

- **Fixed** Game Matching: Added a mapping system (`GAME_NAME_MAPPING`) to resolve discrepancies between Xbox "Now Playing" names and TrueAchievements CSV names (e.g., matching "Minecraft for Android" with "Minecraft (Android)").

## 2026.1.0

- Initial public release.
- Support for TrueAchievements Pro CSV export.
- "Now Playing" real-time sensor linked with Xbox integration.
- Global stats sensors (Gamerscore, TA Score, Completion %).
- Support for English and French languages.
