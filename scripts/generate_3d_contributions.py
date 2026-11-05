#!/usr/bin/env python3
"""Generate a red-and-white 3D GitHub contribution calendar as a static SVG."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

API_URL = "https://api.github.com/graphql"
OUTPUT = Path("profile-3d-contrib/profile-customize.svg")

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def fetch_contributions(username: str, token: str) -> list[list[dict]]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=364)

    variables = {
        "login": username,
        "from": start.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
        "to": end.isoformat(),
    }
    payload = json.dumps({"query": QUERY, "variables": variables}).encode("utf-8")
    request = Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "red-3d-contribution-heatmap",
        },
        method="POST",
    )

    with urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))

    if result.get("errors"):
        raise RuntimeError("GitHub GraphQL error: " + json.dumps(result["errors"]))
    user = result.get("data", {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub user '{username}' was not found or is not readable.")

    return user["contributionsCollection"]["contributionCalendar"]["weeks"]


def shade(count: int) -> str:
    if count <= 2:
        return "#FADADA"
    if count <= 5:
        return "#F28B8B"
    if count <= 10:
        return "#D93636"
    if count <= 20:
        return "#A90000"
    return "#780000"


def darken(hex_color: str, factor: float) -> str:
    value = hex_color.lstrip("#")
    channels = [int(value[i:i + 2], 16) for i in (0, 2, 4)]
    channels = [max(0, min(255, int(channel * factor))) for channel in channels]
    return "#" + "".join(f"{channel:02X}" for channel in channels)


def lighten(hex_color: str, amount: float) -> str:
    value = hex_color.lstrip("#")
    channels = [int(value[i:i + 2], 16) for i in (0, 2, 4)]
    channels = [max(0, min(255, int(channel + (255 - channel) * amount))) for channel in channels]
    return "#" + "".join(f"{channel:02X}" for channel in channels)


def block_height(count: int) -> int:
    # Up to 10 contributions: short-to-medium blocks.
    # Above 10: steep skyscraper-style growth, capped to keep the SVG readable.
    if count <= 10:
        return 8 + count * 5
    return min(230, 58 + (count - 10) * 9)


def render_svg(weeks: list[list[dict]], username: str) -> str:
    # Isometric calendar grid: each week advances right/down; each weekday advances left/down.
    origin_x, origin_y = 90, 260
    week_x, week_y = 14, 7
    day_x, day_y = -7, 7
    face_x, face_y = 10, 5
    side_x, side_y = -5, 5

    width, height = 880, 700
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="3D red GitHub contribution calendar for {username}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
    ]

    # Back-to-front drawing order keeps nearer blocks visually in front.
    cells = []
    for week_index, week in enumerate(weeks):
        for day_index, day in enumerate(week.get("contributionDays", [])):
            count = int(day.get("contributionCount", 0))
            if count > 0:
                cells.append((week_index + day_index, week_index, day_index, count))

    for _, week_index, day_index, count in sorted(cells):
        x = origin_x + week_index * week_x + day_index * day_x
        y = origin_y + week_index * week_y + day_index * day_y
        h = block_height(count)
        base = shade(count)
        top = lighten(base, 0.22)
        right = darken(base, 0.62)
        left = darken(base, 0.82)

        # Top rhombus.
        p0 = (x, y - h)
        p1 = (x + face_x, y + face_y - h)
        p2 = (x + face_x + side_x, y + face_y + side_y - h)
        p3 = (x + side_x, y + side_y - h)

        # Two visible vertical faces.
        p2_base = (p2[0], p2[1] + h)
        p1_base = (p1[0], p1[1] + h)
        p3_base = (p3[0], p3[1] + h)

        points = lambda pts: " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)

        parts.append(
            f'<polygon points="{points([p3, p2, p2_base, p3_base])}" '
            f'fill="{left}" stroke="#FFFFFF" stroke-width="0.55"/>'
        )
        parts.append(
            f'<polygon points="{points([p1, p2, p2_base, p1_base])}" '
            f'fill="{right}" stroke="#FFFFFF" stroke-width="0.55"/>'
        )
        parts.append(
            f'<polygon points="{points([p0, p1, p2, p3])}" '
            f'fill="{top}" stroke="#FFFFFF" stroke-width="0.55"/>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def main() -> int:
    username = os.environ.get("USERNAME", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()

    if not username or not token:
        print("USERNAME and GITHUB_TOKEN environment variables are required.", file=sys.stderr)
        return 1

    try:
        weeks = fetch_contributions(username, token)
        if not weeks:
            raise RuntimeError("GitHub returned an empty contribution calendar.")
        svg = render_svg(weeks, username)
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(svg, encoding="utf-8")
        print(f"Generated {OUTPUT} from {len(weeks)} contribution weeks.")
        return 0
    except Exception as exc:
        print(f"Could not generate contribution heatmap: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
