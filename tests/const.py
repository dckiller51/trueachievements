"""Constants and helpers shared by the TrueAchievements tests."""

from __future__ import annotations

import csv
import io

GAMER_ID = "123456"
GAMERTAG = "TestGamer"
# Fake credentials: nothing here is a real cookie.
COOKIE = "ASP.NET_SessionId=sess; GamerID=123456; GamerToken=tok; cf_clearance=old"
XBOX_ENTITY = "sensor.xbox_now_playing"
XBOX_IMAGE_ENTITY = "image.xbox_now_playing"

CSV_HEADER = [
    "Game name",
    "Platform",
    "Achievements Won (incl. DLC)",
    "Max Achievements (incl. DLC)",
    "GamerScore Won (incl. DLC)",
    "Max Gamerscore (incl. DLC)",
    "TrueAchievement Won (incl. DLC)",
    "Max TrueAchievement (incl. DLC)",
    "Hours Played",
    "My Completion Percentage",
    "My Ratio",
    "Game URL",
    "Walkthrough",
]

HALO_URL = "https://www.trueachievements.com/game/Halo-Infinite/achievements"
HALO_WALKTHROUGH = "https://www.trueachievements.com/game/Halo-Infinite/walkthrough"


def game_row(
    name: str,
    platform: str,
    *,
    won: int = 0,
    total: int = 0,
    gs: int = 0,
    gs_max: int = 0,
    ta: int = 0,
    ta_max: int = 0,
    hours: str = "0",
    completion: str = "0",
    ratio: str = "1.00",
    url: str = "",
    walkthrough: str = "",
) -> list[str]:
    """Return one CSV row, in the column order of CSV_HEADER."""
    return [
        name,
        platform,
        str(won),
        str(total),
        str(gs),
        str(gs_max),
        str(ta),
        str(ta_max),
        hours,
        completion,
        ratio,
        url,
        walkthrough,
    ]


BASE = "https://www.trueachievements.com/game"

CSV_ROWS: list[list[str]] = [
    game_row(
        "Halo Infinite",
        "Xbox Series X|S",
        won=50,
        total=119,
        gs=1000,
        gs_max=2000,
        ta=1500,
        ta_max=4000,
        hours="40.5",
        completion="42",
        ratio="1.55",
        url=HALO_URL,
        walkthrough=HALO_WALKTHROUGH,
    ),
    game_row(
        "Forza Horizon 5",
        "Xbox One",
        won=120,
        total=120,
        gs=1900,
        gs_max=1900,
        ta=5000,
        ta_max=5000,
        hours="100",
        completion="100",
        ratio="1.20",
        url=f"{BASE}/Forza/achievements",
    ),
    game_row(
        "Gears 5",
        "Xbox One",
        won=10,
        total=100,
        gs=200,
        gs_max=1000,
        ta=300,
        ta_max=3000,
        hours="5",
        completion="10",
        ratio="1.30",
        url=f"{BASE}/Gears-5/achievements",
    ),
    game_row(
        "Sea of Thieves",
        "Xbox One",
        won=10,
        total=50,
        gs=100,
        gs_max=1000,
        ta=150,
        ta_max=2500,
        hours="3",
        completion="20",
        ratio="1.10",
        url=f"{BASE}/SoT-Xbox/achievements",
    ),
    game_row(
        "Sea of Thieves",
        "Windows",
        won=20,
        total=50,
        gs=300,
        gs_max=1000,
        ta=450,
        ta_max=2500,
        hours="8",
        completion="40",
        ratio="1.15",
        url=f"{BASE}/SoT-Windows/achievements",
    ),
    # No progress yet: not counted as "started".
    game_row("Untouched Game", "Xbox One", total=50, gs_max=1000, ta_max=2500),
    # Apps are ignored.
    game_row("Netflix", "App"),
]

# Totals expected from CSV_ROWS
TOTAL_GAMERSCORE = 3500
TOTAL_TA_SCORE = 7400
TOTAL_ACHIEVEMENTS = 210
TOTAL_STARTED = 5
TOTAL_COMPLETED = 1
COMPLETION_PCT = 47.84  # 210 / 439


def build_csv(rows: list[list[str]] | None = None, fillers: int = 10) -> bytes:
    """Return a TrueAchievements-like CSV export, larger than the 1000-byte check."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    writer.writerows(CSV_ROWS if rows is None else rows)
    for index in range(fillers):
        writer.writerow(
            game_row(f"Filler Game {index}", "Xbox One", total=10, gs_max=100)
        )
    return ("﻿" + buffer.getvalue()).encode("utf-8")
