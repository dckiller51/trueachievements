# TrueAchievements Sync (Firefox extension)

Companion of the [TrueAchievements for Home Assistant](https://github.com/dckiller51/trueachievements) integration.

TrueAchievements is protected by Cloudflare, so Home Assistant cannot download your CSV export reliably. This extension does it in Firefox, where you are signed in, and sends the file to your Home Assistant.

> **Requires a TrueAchievements Pro account** (the collection export is a Pro feature) and the integration set to **Local file only**.

## Install

From Mozilla Add-ons: <https://addons.mozilla.org/addon/3100079/> (Firefox for desktop and Firefox for Android).

## Set up

1. In Home Assistant, add the integration and tick **Local file only**, then open its options to read the **upload address** (`/api/webhook/...`).
2. Sign in to [trueachievements.com](https://www.trueachievements.com) in Firefox.
3. Open the extension settings and fill:
   - **Upload address**: `http://<your Home Assistant>:8123` followed by the path above (use the IP address, not a `.local` name, on Android),
   - **Gamertag** and **GamerID**.
4. Press **Save**, then **Sync now**.

## How it works

- It synchronises **when Firefox starts**. Nothing runs in the background afterwards.
- Open the settings to see the result of the last synchronisation. If it failed, press **Sync now**.
- If TrueAchievements answers with an empty file, the extension reloads a TrueAchievements tab (or opens your profile in a background tab), then retries once.

## Privacy

It only contacts `www.trueachievements.com` and the upload address you entered. No analytics, no third party. Settings are stored locally in the browser.

Permissions: `tabs` (reload or open a TrueAchievements tab), `storage` (your settings), and access to `trueachievements.com` and to your Home Assistant webhook.

No build step: plain JavaScript, HTML and JSON, exactly what is in this folder.
