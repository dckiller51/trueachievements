# Changelog

All notable changes to this project will be documented in this file.

<!--next-version-placeholder-->

## 2026.1.2

- **Added** Global Mapping Issue: Added a dedicated [GitHub Issue]({ISSUE_URL}) to report missing game name mappings.
- **Added** Automated Notifications: The integration now notifies you via Home Assistant if a game name mismatch is detected, providing a direct link to report it.
- **Fixed** Game matching: Updated `GAME_NAME_MAPPING` to correct the inconsistency for **Roblox**.
- **Fixed\*** Stability: Fixed a thread-safety issue where notifications could cause the integration to crash during CSV processing.

## 2026.1.1

- **Fixed** Game Matching: Added a mapping system (`GAME_NAME_MAPPING`) to resolve discrepancies between Xbox "Now Playing" names and TrueAchievements CSV names (e.g., matching "Minecraft for Android" with "Minecraft (Android)").

## 2026.1.0

- Initial public release.
- Support for TrueAchievements Pro CSV export.
- "Now Playing" real-time sensor linked with Xbox integration.
- Global stats sensors (Gamerscore, TA Score, Completion %).
- Support for English and French languages.
