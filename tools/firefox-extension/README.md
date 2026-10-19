# TrueAchievements Sync (Firefox extension)

Runs inside a browser where you are signed in to TrueAchievements. It downloads
the CSV export and sends it to the upload address of the Home Assistant
integration (enable **Local file only** in its options).

- Synchronises when Firefox starts, then every N minutes (default 60).
- If the export comes back empty, it reloads a TrueAchievements tab (or opens
  your profile in a background tab) to renew the site session, then retries once.
- _Sync now_ in the settings forces a synchronisation.

Works on Firefox for desktop and Firefox for Android. Nothing is sent anywhere
except to TrueAchievements and to your own Home Assistant.

Install: https://addons.mozilla.org/addon/3100079/
