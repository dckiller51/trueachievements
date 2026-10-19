"use strict";

const fields = ["webhook", "gamertag", "gamerId"];

function showStatus(status) {
  const box = document.getElementById("status");
  if (!status) return;
  box.className = status.ok ? "ok" : "error";
  box.textContent = `${new Date(status.time).toLocaleString()}: ${
    status.message
  }`;
}

async function load() {
  const stored = await browser.storage.local.get([...fields, "status"]);
  for (const name of fields) {
    if (stored[name] !== undefined)
      document.getElementById(name).value = stored[name];
  }
  showStatus(stored.status);
}

document.getElementById("save").addEventListener("click", async () => {
  const values = {};
  for (const name of fields)
    values[name] = document.getElementById(name).value.trim();
  await browser.storage.local.set(values);
  document.getElementById("status").textContent =
    "Saved. Press Sync now to test.";
});

document.getElementById("run").addEventListener("click", async () => {
  document.getElementById("status").textContent = "Working...";
  showStatus(await browser.runtime.sendMessage("run"));
});

browser.storage.onChanged.addListener((changes) => {
  if (changes.status) showStatus(changes.status.newValue);
});

load();
