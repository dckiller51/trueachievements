"use strict";

const SITE = "https://www.trueachievements.com/";
const ALARM = "ta-sync";
const DEFAULTS = { webhook: "", gamerId: "", gamertag: "", interval: 20 };

async function getConfig() {
  const stored = await browser.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

async function saveStatus(ok, message) {
  const status = { ok, message, time: new Date().toISOString() };
  await browser.storage.local.set({ status });
  console.log("TA Sync:", ok ? "OK" : "FAILED", message);
  return status;
}

// A real page visit renews the session of the site: open the profile in a
// background tab, wait for it to load, then close it.
async function visitProfileInTab(gamertag) {
  const url = `${SITE}gamer/${encodeURIComponent(gamertag)}`;
  let tab;
  let created = false;
  try {
    // Reuse a tab already open on the site: a simple reload renews the session.
    const open = await browser.tabs.query({
      url: "*://www.trueachievements.com/*",
    });
    if (open.length) {
      tab = open[0];
      await browser.tabs.reload(tab.id);
    } else {
      tab = await browser.tabs.create({ url, active: false });
      created = true;
    }
    await new Promise((resolve) => {
      const done = () => {
        browser.tabs.onUpdated.removeListener(listener);
        clearTimeout(timer);
        resolve();
      };
      const listener = (tabId, info) => {
        if (tabId === tab.id && info.status === "complete") done();
      };
      const timer = setTimeout(done, 45000);
      browser.tabs.onUpdated.addListener(listener);
    });
    // Leave time to a possible automatic Cloudflare check.
    await new Promise((resolve) => setTimeout(resolve, 8000));
    return true;
  } catch (err) {
    console.log("TA Sync: could not open a tab:", err.message);
    return false;
  } finally {
    if (tab && created) browser.tabs.remove(tab.id).catch(() => {});
  }
}

// One attempt: profile, CSV, then upload. Returns {ok, message, retry}.
async function attempt(cfg) {
  const profile = await fetch(
    `${SITE}gamer/${encodeURIComponent(cfg.gamertag)}`,
    {
      credentials: "include",
    }
  );
  if (
    profile.headers.get("cf-mitigated") === "challenge" ||
    profile.status === 403
  ) {
    return {
      ok: false,
      retry: true,
      message:
        "Cloudflare asks for a check: open trueachievements.com in this browser once.",
    };
  }
  await profile.arrayBuffer();

  const response = await fetch(
    `${SITE}download.aspx?type=gamecollection&id=${encodeURIComponent(
      cfg.gamerId
    )}`,
    { credentials: "include" }
  );
  const content = new Uint8Array(await response.arrayBuffer());
  const text = new TextDecoder().decode(content);
  if (
    response.status !== 200 ||
    content.length < 1000 ||
    !text.includes("Game name")
  ) {
    return {
      ok: false,
      retry: true,
      message: `Not a CSV export (HTTP ${response.status}, ${content.length} bytes): sign in to trueachievements.com in this browser.`,
    };
  }

  const upload = await fetch(cfg.webhook, { method: "POST", body: content });
  if (!upload.ok) {
    return {
      ok: false,
      retry: false,
      message: `Home Assistant refused the file (HTTP ${upload.status}).`,
    };
  }
  return {
    ok: true,
    retry: false,
    message: `CSV sent to Home Assistant (${content.length} bytes).`,
  };
}

// Download the CSV export and send it to the Home Assistant webhook. When it
// fails, visit the profile in a real tab (this renews the session) and retry once.
async function runSync() {
  const cfg = await getConfig();
  if (!cfg.webhook || !cfg.gamerId || !cfg.gamertag) {
    return saveStatus(
      false,
      "Fill the settings first (upload address, GamerID, gamertag)."
    );
  }
  try {
    let result = await attempt(cfg);
    if (!result.ok && result.retry) {
      const first = result.message;
      if (await visitProfileInTab(cfg.gamertag)) {
        result = await attempt(cfg);
        if (result.ok)
          result.message += " (after visiting your profile in a tab)";
        else result.message = `${result.message} First attempt: ${first}`;
      }
    }
    return saveStatus(result.ok, result.message);
  } catch (err) {
    return saveStatus(false, `Error: ${err.message}`);
  }
}

async function schedule() {
  const { interval } = await getConfig();
  await browser.alarms.clear(ALARM);
  browser.alarms.create(ALARM, {
    periodInMinutes: Math.max(5, Number(interval) || 20),
  });
}

browser.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM) runSync();
});
browser.runtime.onInstalled.addListener(schedule);
browser.runtime.onStartup.addListener(() => {
  schedule();
  runSync();
});
browser.storage.onChanged.addListener((changes) => {
  if (changes.interval) schedule();
});
browser.browserAction.onClicked.addListener(() =>
  browser.runtime.openOptionsPage()
);
browser.runtime.onMessage.addListener((message) => {
  if (message === "run") return runSync();
  return undefined;
});
