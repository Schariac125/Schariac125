#!/usr/bin/env python3
"""Generate an animated contribution snake as a standalone SVG.

Fetches the public contribution calendar through GitHub's GraphQL API and
writes a light and a dark SVG. No third-party Python packages are required.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.github.com/graphql"
DURATION = 54.0
CELL = 11
GAP = 3
STEP = CELL + GAP
MARGIN = 16
ROWS = 7
BODY_CELLS = 6

CONTRIBUTIONS_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks {
          contributionDays {
            weekday
            contributionLevel
          }
        }
      }
    }
  }
}
"""

LEVEL_INDEX = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}

PALETTES = {
    "light": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
    "dark": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
}
SNAKE_COLORS = {"light": "#8250df", "dark": "#a371f7"}
HEAD_COLORS = {"light": "#6639ba", "dark": "#d2a8ff"}


def request_weeks(user: str, token: str) -> list[dict]:
    body = json.dumps(
        {"query": CONTRIBUTIONS_QUERY, "variables": {"login": user}}
    ).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{user}-profile-snake",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"GitHub API returned {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Could not reach GitHub: {exc.reason}") from exc

    if payload.get("errors"):
        raise SystemExit("GitHub API error: " + json.dumps(payload["errors"])[:500])

    user_data = (payload.get("data") or {}).get("user")
    if not user_data:
        raise SystemExit(f"No GitHub user found for {user!r}.")

    weeks = user_data["contributionsCollection"]["contributionCalendar"]["weeks"]
    if not weeks:
        raise SystemExit("GitHub returned an empty contribution calendar.")
    return weeks[-53:]


def demo_weeks(count: int = 53) -> list[dict]:
    rng = random.Random(20261115)
    levels = (
        ["NONE"] * 9
        + ["FIRST_QUARTILE"] * 6
        + ["SECOND_QUARTILE"] * 3
        + ["THIRD_QUARTILE"]
        + ["FOURTH_QUARTILE"]
    )
    weeks = []
    for _ in range(count):
        days = []
        for weekday in range(ROWS):
            chance = 0.25 if weekday in (0, 6) else 0.55
            level = rng.choice(levels) if rng.random() < chance else "NONE"
            days.append({"weekday": weekday, "contributionLevel": level})
        weeks.append({"contributionDays": days})
    return weeks


def number(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def build_svg(weeks: list[dict], theme: str) -> str:
    weeks = weeks[-53:]
    columns = len(weeks)
    width = MARGIN * 2 + columns * STEP - GAP
    height = MARGIN * 2 + ROWS * STEP - GAP

    cells: dict[tuple[int, int], int] = {}
    for column, week in enumerate(weeks):
        for day in week.get("contributionDays", []):
            row = int(day.get("weekday", 0))
            if 0 <= row < ROWS:
                cells[(column, row)] = LEVEL_INDEX.get(
                    day.get("contributionLevel", "NONE"), 0
                )

    points: list[tuple[float, float]] = []
    for column in range(columns):
        rows = range(ROWS) if column % 2 == 0 else range(ROWS - 1, -1, -1)
        for row in rows:
            points.append(
                (
                    MARGIN + column * STEP + CELL / 2,
                    MARGIN + row * STEP + CELL / 2,
                )
            )

    total = (len(points) - 1) * STEP
    body_length = BODY_CELLS * STEP
    travel = total - body_length
    if travel <= 0:
        raise SystemExit("Not enough weeks to draw the snake.")

    palette = PALETTES[theme]
    snake = SNAKE_COLORS[theme]
    head = HEAD_COLORS[theme]
    last_index = len(points) - 1

    rects: list[str] = []
    for column in range(columns):
        for row in range(ROWS):
            level = cells.get((column, row), 0)
            x = MARGIN + column * STEP
            y = MARGIN + row * STEP
            attrs = (
                f'x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                f'rx="2" fill="{palette[level]}"'
            )
            if not level:
                rects.append(f"<rect {attrs}/>")
                continue

            index = column * ROWS + (row if column % 2 == 0 else ROWS - 1 - row)
            if index < BODY_CELLS:
                moment = 0.0
            else:
                moment = (index - BODY_CELLS) / (last_index - BODY_CELLS)
            start = min(max(moment, 0.0001), 0.998)
            end = min(1.0, start + 0.002)
            rects.append(
                f'<rect {attrs}><animate attributeName="opacity" '
                f'values="1;1;0" keyTimes="0;{start:.4f};{end:.4f}" '
                f'dur="{number(DURATION)}s" repeatCount="indefinite"/></rect>'
            )

    path_data = "M " + " L ".join(f"{number(x)} {number(y)}" for x, y in points)

    head_stops: list[int] = []
    for column in range(columns):
        for index in (column * ROWS, column * ROWS + ROWS - 1):
            if index >= BODY_CELLS:
                head_stops.append(index)
    head_stops = sorted(set(head_stops))

    frames = []
    for index in head_stops:
        x, y = points[index]
        percent = (index - BODY_CELLS) / (last_index - BODY_CELLS) * 100
        frames.append(
            f"{percent:.4f}% {{ transform: translate({number(x)}px, {number(y)}px); }}"
        )
    keyframes = "\n      ".join(frames)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="snake-title">
  <title id="snake-title">Contribution snake</title>
  <desc>An animated snake crawling across the GitHub contribution graph.</desc>
  <style>
    .body {{
      fill: none;
      stroke: {snake};
      stroke-width: 9;
      stroke-linecap: round;
      stroke-linejoin: round;
      stroke-dasharray: {body_length} 100000;
      animation: crawl {number(DURATION)}s linear infinite;
    }}
    .head {{ animation: head {number(DURATION)}s linear infinite; }}
    @keyframes crawl {{
      from {{ stroke-dashoffset: 0; }}
      to {{ stroke-dashoffset: {-travel}; }}
    }}
    @keyframes head {{
      {keyframes}
    }}
  </style>
  <g>
    {chr(10).join("    " + rect for rect in rects)}
  </g>
  <path class="body" d="{path_data}"/>
  <g class="head">
    <circle r="6.5" fill="{head}"/>
    <circle r="2.2" cx="1.6" cy="-1.6" fill="#ffffff" opacity="0.85"/>
  </g>
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", required=True, help="GitHub username")
    parser.add_argument("--out", default="dist", help="output directory")
    parser.add_argument("--demo", action="store_true", help="use generated data")
    args = parser.parse_args()

    if args.demo:
        weeks = demo_weeks()
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            raise SystemExit("GITHUB_TOKEN is not set.")
        weeks = request_weeks(args.user, token)

    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    for theme, filename in (("light", "snake.svg"), ("dark", "snake-dark.svg")):
        svg = build_svg(weeks, theme)
        path = output / filename
        path.write_text(svg, encoding="utf-8")
        print(f"wrote {path} ({len(svg.encode('utf-8'))} bytes)")


if __name__ == "__main__":
    main()
