#!/usr/bin/env python3
"""Build local SVG profile cards for the GitHub profile README."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


USERNAME = os.environ.get("PROFILE_USERNAME", "Martin-Munive")
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets" / "generated"
REST_ROOT = "https://api.github.com"
GRAPHQL_ROOT = "https://api.github.com/graphql"

BG = "#0b1220"
PANEL = "#111827"
BORDER = "#243244"
TEXT = "#e5edf7"
MUTED = "#94a3b8"
BLUE = "#38bdf8"
GREEN = "#22c55e"
RED = "#ef4444"
AMBER = "#f59e0b"
VIOLET = "#a78bfa"
CYAN = "#06b6d4"
GRID_EMPTY = "#1f2937"

# GitHub's language endpoint occasionally counts generated platform wrappers as
# first-class project languages. Keep corrections narrow, explicit and reviewable.
REPOSITORY_LANGUAGE_EXCLUSIONS = {
    "Control-insulinas": {
        "C",
        "C++",
        "CMake",
        "Kotlin",
        "Objective-C",
        "Swift",
    }
}


def token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def request_json(url: str, *, payload: dict[str, Any] | None = None) -> Any:
    data = None
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Martin-Munive-profile-cards",
    }
    if token():
        headers["Authorization"] = f"Bearer {token()}"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if token():
            raise
        return gh_fallback(url, payload=payload)


def gh_fallback(url: str, *, payload: dict[str, Any] | None = None) -> Any:
    if payload is not None and url == GRAPHQL_ROOT:
        args = ["gh", "api", "graphql", "-f", f"query={payload['query']}"]
        for key, value in payload.get("variables", {}).items():
            args.extend(["-F", f"{key}={value}"])
    else:
        path = url.removeprefix(REST_ROOT)
        args = ["gh", "api", "--paginate", path]
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=True)
    text = result.stdout.strip()
    if not text:
        return []
    if "\n" in text and payload is None:
        return [item for line in text.splitlines() for item in json.loads(line)]
    return json.loads(text)


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def write_svg(path: Path, svg: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(svg.strip() + "\n", encoding="utf-8")


def fetch_repos() -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        params = urllib.parse.urlencode(
            {"type": "owner", "sort": "updated", "per_page": 100, "page": page}
        )
        batch = request_json(f"{REST_ROOT}/users/{USERNAME}/repos?{params}")
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_language_signals(repos: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    signals: dict[str, dict[str, float | int]] = {}
    for repo in repos:
        if repo.get("fork") or repo.get("archived") or repo.get("name") == USERNAME:
            continue
        languages_url = repo.get("languages_url")
        if not languages_url:
            continue
        excluded = REPOSITORY_LANGUAGE_EXCLUSIONS.get(repo.get("name", ""), set())
        languages = {
            language: int(size)
            for language, size in request_json(languages_url).items()
            if language not in excluded and language != "Procfile" and int(size) > 0
        }
        repo_total = sum(languages.values())
        if not repo_total:
            continue
        for language, size in languages.items():
            signal = signals.setdefault(
                language,
                {"score": 0.0, "repositories": 0, "bytes": 0},
            )
            signal["score"] = float(signal["score"]) + size / repo_total
            signal["repositories"] = int(signal["repositories"]) + 1
            signal["bytes"] = int(signal["bytes"]) + size
    return signals


def fetch_contributions() -> dict[str, Any]:
    today = dt.datetime.now(dt.timezone.utc).date()
    since = today - dt.timedelta(days=365)
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
          totalPullRequestReviewContributions
          restrictedContributionsCount
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                weekday
                contributionCount
                contributionLevel
              }
            }
          }
        }
      }
    }
    """
    payload = {
        "query": query,
        "variables": {
            "login": USERNAME,
            "from": f"{since.isoformat()}T00:00:00Z",
            "to": f"{today.isoformat()}T23:59:59Z",
        },
    }
    data = request_json(GRAPHQL_ROOT, payload=payload)
    if errors := data.get("errors"):
        raise RuntimeError(json.dumps(errors, indent=2))
    return data["data"]["user"]["contributionsCollection"]


def count_streaks(days: list[dict[str, Any]]) -> tuple[int, int, str]:
    ordered = sorted(days, key=lambda day: day["date"])
    longest = 0
    current_run = 0
    last_active = "sin actividad"
    for day in ordered:
        if day["contributionCount"] > 0:
            current_run += 1
            longest = max(longest, current_run)
            last_active = day["date"]
        else:
            current_run = 0

    recent = 0
    for day in reversed(ordered):
        if day["contributionCount"] > 0:
            recent += 1
        elif recent > 0:
            break
    return recent, longest, last_active


def metric(x: int | float) -> str:
    if isinstance(x, float):
        return f"{x:.1f}"
    return f"{x:,}".replace(",", ".")


def svg_header(title: str, subtitle: str, width: int, height: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        "<defs>",
        "<linearGradient id=\"accent\" x1=\"0\" x2=\"1\" y1=\"0\" y2=\"1\">",
        f'<stop offset="0%" stop-color="{BLUE}"/>',
        f'<stop offset="52%" stop-color="{GREEN}"/>',
        f'<stop offset="100%" stop-color="{RED}"/>',
        "</linearGradient>",
        "</defs>",
        f'<rect width="{width}" height="{height}" rx="12" fill="{BG}"/>',
        f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="11" fill="none" stroke="{BORDER}"/>',
        '<rect x="0" y="0" width="8" height="100%" fill="url(#accent)"/>',
        f'<text x="28" y="36" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="20" font-weight="700" fill="{TEXT}">{esc(title)}</text>',
        f'<text x="28" y="60" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="13" fill="{MUTED}">{esc(subtitle)}</text>',
    ]


def svg_footer(parts: list[str]) -> str:
    return "\n".join(parts + ["</svg>"])


def build_stats_card(repos: list[dict[str, Any]], contrib: dict[str, Any]) -> str:
    calendar = contrib["contributionCalendar"]
    days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
    active_days = sum(1 for day in days if day["contributionCount"] > 0)
    recent, longest, last_active = count_streaks(days)
    last_7 = sum(day["contributionCount"] for day in days[-7:])
    last_30 = sum(day["contributionCount"] for day in days[-30:])
    public_repos = [repo for repo in repos if not repo.get("fork")]
    stars = sum(int(repo.get("stargazers_count", 0)) for repo in public_repos)
    forks = sum(int(repo.get("forks_count", 0)) for repo in public_repos)
    updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    items = [
        ("Contribuciones 365d", metric(calendar["totalContributions"]), BLUE),
        ("Dias activos 365d", metric(active_days), GREEN),
        ("Ultimos 7 dias", metric(last_7), AMBER),
        ("Ultimos 30 dias", metric(last_30), VIOLET),
        ("Racha reciente", f"{recent} dias", GREEN if recent else MUTED),
        ("Racha maxima 365d", f"{longest} dias", RED),
        ("Repos publicos propios", metric(len(public_repos)), CYAN),
        ("Estrellas / forks", f"{metric(stars)} / {metric(forks)}", AMBER),
    ]
    parts = svg_header(
        "GitHub Signals",
        f"Resumen generado en el repositorio; ultima actividad detectada: {last_active}",
        820,
        260,
    )
    x_positions = [28, 222, 416, 610]
    for index, (label, value, color) in enumerate(items):
        col = index % 4
        row = index // 4
        x = x_positions[col]
        y = 104 + row * 82
        parts.extend(
            [
                f'<rect x="{x}" y="{y - 34}" width="168" height="58" rx="8" fill="{PANEL}" stroke="{BORDER}"/>',
                f'<text x="{x + 14}" y="{y - 12}" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="12" fill="{MUTED}">{esc(label)}</text>',
                f'<text x="{x + 14}" y="{y + 14}" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="22" font-weight="700" fill="{color}">{esc(value)}</text>',
            ]
        )
    parts.append(
        f'<text x="28" y="236" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="11" fill="{MUTED}">Actualizado: {esc(updated)}. Fuente: GitHub API, criterio publico de contribuciones.</text>'
    )
    return svg_footer(parts)


def build_language_constellation(signals: dict[str, dict[str, float | int]]) -> str:
    ranked = sorted(
        signals.items(),
        key=lambda item: (float(item[1]["score"]), int(item[1]["repositories"])),
        reverse=True,
    )[:8]
    total_score = sum(float(signal["score"]) for signal in signals.values()) or 1.0
    colors = [BLUE, GREEN, AMBER, VIOLET, CYAN, RED, "#f97316", "#64748b"]
    positions = [
        (176, 126),
        (356, 111),
        (530, 137),
        (660, 220),
        (535, 292),
        (350, 310),
        (175, 283),
        (94, 207),
    ]
    parts = svg_header(
        "Language Constellation",
        "Project-normalized footprint; generated build languages are filtered by repository policy",
        820,
        390,
    )
    center_x, center_y = 382, 211
    parts.extend(
        [
            f'<circle cx="{center_x}" cy="{center_y}" r="58" fill="{PANEL}" stroke="{BORDER}" stroke-width="2"/>',
            f'<circle cx="{center_x}" cy="{center_y}" r="73" fill="none" stroke="{BORDER}" stroke-width="1" stroke-dasharray="3 7"/>',
            f'<text x="{center_x}" y="{center_y - 7}" text-anchor="middle" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="11" font-weight="700" fill="{MUTED}">PORTFOLIO</text>',
            f'<text x="{center_x}" y="{center_y + 18}" text-anchor="middle" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="22" font-weight="700" fill="{TEXT}">{len(ranked)}/{len(signals)}</text>',
            f'<text x="{center_x}" y="{center_y + 35}" text-anchor="middle" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="9" fill="{MUTED}">SHOWN / TOTAL</text>',
        ]
    )
    for index, ((language, signal), (x, y)) in enumerate(zip(ranked, positions)):
        score = float(signal["score"])
        repositories = int(signal["repositories"])
        share = score / total_score
        radius = 23 + min(24, 75 * share)
        color = colors[index % len(colors)]
        label_size = 10 if len(language) > 13 else 12
        parts.extend(
            [
                f'<line x1="{center_x}" y1="{center_y}" x2="{x}" y2="{y}" stroke="{color}" stroke-width="{1.0 + 3.0 * share:.1f}" opacity="0.45"/>',
                f'<circle cx="{x}" cy="{y}" r="{radius:.1f}" fill="{color}" fill-opacity="0.13" stroke="{color}" stroke-width="2"/>',
                f'<circle cx="{x}" cy="{y}" r="4" fill="{color}"/>',
                f'<text x="{x}" y="{y - 9}" text-anchor="middle" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="{label_size}" font-weight="700" fill="{TEXT}">{esc(language)}</text>',
                f'<text x="{x}" y="{y + 17}" text-anchor="middle" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="10" fill="{MUTED}">{repositories} repo{"s" if repositories != 1 else ""}</text>',
                f'<title>{esc(language)}: {share * 100:.1f}% project-normalized signal across {repositories} repositories</title>',
            ]
        )
    parts.extend(
        [
            f'<text x="28" y="366" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="10" fill="{MUTED}">Node size = normalized project signal. Each repository contributes the same total weight.</text>',
            f'<text x="792" y="366" text-anchor="end" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="10" fill="{MUTED}">Source: GitHub Linguist API</text>',
        ]
    )
    return svg_footer(parts)


def polar_point(cx: float, cy: float, radius: float, index: int, total: int = 7) -> tuple[float, float]:
    angle = -math.pi / 2 + (2 * math.pi * index / total)
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def point_string(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def build_engineering_pulse(contrib: dict[str, Any]) -> str:
    calendar = contrib["contributionCalendar"]
    weeks = calendar["weeks"][-12:]
    days = [day for week in weeks for day in week["contributionDays"]]
    weekly_totals = [sum(day["contributionCount"] for day in week["contributionDays"]) for week in weeks]
    max_week = max(weekly_totals, default=1) or 1
    last_7 = sum(day["contributionCount"] for day in days[-7:])
    last_30 = sum(day["contributionCount"] for day in days[-30:])
    recent_28 = sum(day["contributionCount"] for day in days[-28:])
    previous_28 = sum(day["contributionCount"] for day in days[-56:-28])
    active_30 = sum(1 for day in days[-30:] if day["contributionCount"] > 0)
    consistency = round(100 * sum(total > 0 for total in weekly_totals) / max(len(weekly_totals), 1))
    if previous_28:
        momentum_value = round(100 * (recent_28 - previous_28) / previous_28)
        momentum = f"{momentum_value:+d}%"
        momentum_color = GREEN if momentum_value >= 0 else RED
    elif recent_28:
        momentum = "NEW"
        momentum_color = CYAN
    else:
        momentum = "0%"
        momentum_color = MUTED

    parts = svg_header(
        "Engineering Pulse",
        "12-week signal and cadence vector; designed to complement GitHub's native calendar",
        820,
        370,
    )
    parts.extend(
        [
            f'<text x="28" y="88" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="11" font-weight="700" fill="{CYAN}">WEEKLY SIGNAL / 12 CYCLES</text>',
            f'<text x="604" y="88" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="11" font-weight="700" fill="{VIOLET}">CADENCE VECTOR</text>',
        ]
    )

    chart_left = 36
    chart_right = 535
    chart_top = 110
    chart_bottom = 238
    for index in range(4):
        y = chart_top + index * ((chart_bottom - chart_top) / 3)
        parts.append(
            f'<line x1="{chart_left}" y1="{y:.1f}" x2="{chart_right}" y2="{y:.1f}" stroke="{BORDER}" stroke-width="1" stroke-dasharray="3 7"/>'
        )
    average = sum(weekly_totals) / max(len(weekly_totals), 1)
    average_y = chart_bottom - ((average / max_week) * (chart_bottom - chart_top))
    parts.extend(
        [
            f'<line x1="{chart_left}" y1="{average_y:.1f}" x2="{chart_right}" y2="{average_y:.1f}" stroke="{AMBER}" stroke-width="1" stroke-dasharray="8 6" opacity="0.75"/>',
            f'<text x="{chart_right - 2}" y="{average_y - 6:.1f}" text-anchor="end" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="9" fill="{AMBER}">AVG {average:.1f}</text>',
        ]
    )
    denominator = max(len(weekly_totals) - 1, 1)
    signal_points = [
        (
            chart_left + index * ((chart_right - chart_left) / denominator),
            chart_bottom - (total / max_week) * (chart_bottom - chart_top),
        )
        for index, total in enumerate(weekly_totals)
    ]
    if signal_points:
        area_points = [(signal_points[0][0], chart_bottom), *signal_points, (signal_points[-1][0], chart_bottom)]
        parts.extend(
            [
                f'<polygon points="{point_string(area_points)}" fill="{CYAN}" fill-opacity="0.10"/>',
                f'<polyline points="{point_string(signal_points)}" fill="none" stroke="{CYAN}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>',
            ]
        )
    for index, ((x, y), total) in enumerate(zip(signal_points, weekly_totals)):
        color = AMBER if total == max_week else BLUE
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{BG}" stroke="{color}" stroke-width="2"><title>Cycle {index + 1}: {total} contributions</title></circle>'
        )
        if index in {0, len(weekly_totals) - 1}:
            label = "-11W" if index == 0 else "NOW"
            parts.append(
                f'<text x="{x:.1f}" y="258" text-anchor="middle" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="9" fill="{MUTED}">{label}</text>'
            )

    weekday_totals = {index: 0 for index in range(7)}
    for day in days:
        weekday_totals[int(day["weekday"])] += int(day["contributionCount"])
    weekday_order = [(1, "M"), (2, "T"), (3, "W"), (4, "T"), (5, "F"), (6, "S"), (0, "S")]
    max_day = max(weekday_totals.values(), default=1) or 1
    cx, cy, radius = 690.0, 184.0, 70.0
    for ring_scale in (0.33, 0.66, 1.0):
        ring = [polar_point(cx, cy, radius * ring_scale, index) for index in range(7)]
        parts.append(
            f'<polygon points="{point_string(ring)}" fill="none" stroke="{BORDER}" stroke-width="1"/>'
        )
    for index, (_, label) in enumerate(weekday_order):
        outer_x, outer_y = polar_point(cx, cy, radius, index)
        label_x, label_y = polar_point(cx, cy, radius + 17, index)
        parts.extend(
            [
                f'<line x1="{cx}" y1="{cy}" x2="{outer_x:.1f}" y2="{outer_y:.1f}" stroke="{BORDER}" stroke-width="1"/>',
                f'<text x="{label_x:.1f}" y="{label_y + 4:.1f}" text-anchor="middle" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="10" fill="{MUTED}">{label}</text>',
            ]
        )
    cadence_points = [
        polar_point(cx, cy, 12 + 58 * (weekday_totals[weekday] / max_day), index)
        for index, (weekday, _) in enumerate(weekday_order)
    ]
    parts.extend(
        [
            f'<polygon points="{point_string(cadence_points)}" fill="{VIOLET}" fill-opacity="0.22" stroke="{VIOLET}" stroke-width="2" stroke-linejoin="round"/>',
            f'<circle cx="{cx}" cy="{cy}" r="3" fill="{TEXT}"/>',
        ]
    )

    metrics = [
        ("CURRENT 7D", metric(last_7), GREEN),
        ("ROLLING 30D", metric(last_30), AMBER),
        ("4W MOMENTUM", momentum, momentum_color),
        ("ACTIVE DAYS / 30", f"{active_30}/30", CYAN),
        ("WEEKLY UPTIME", f"{consistency}%", VIOLET),
    ]
    metric_x = [28, 184, 340, 496, 652]
    for index, ((label, value, color), x) in enumerate(zip(metrics, metric_x)):
        if index:
            parts.append(f'<line x1="{x - 18}" y1="292" x2="{x - 18}" y2="342" stroke="{BORDER}"/>')
        parts.extend(
            [
                f'<text x="{x}" y="307" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="9" font-weight="700" fill="{MUTED}">{label}</text>',
                f'<text x="{x}" y="337" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="22" font-weight="700" fill="{color}">{esc(value)}</text>',
            ]
        )
    parts.extend(
        [
            f'<text x="28" y="359" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="9" fill="{MUTED}">Telemetry derived from GitHub contribution data. Current week may be incomplete.</text>',
        ]
    )
    return svg_footer(parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--card",
        choices=("all", "languages"),
        default="all",
        help="Generate every card or only the language constellation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repos = fetch_repos()
    signals = fetch_language_signals(repos)
    write_svg(OUT_DIR / "top-languages.svg", build_language_constellation(signals))
    if args.card == "all":
        contrib = fetch_contributions()
        write_svg(OUT_DIR / "github-signals.svg", build_stats_card(repos, contrib))
        write_svg(OUT_DIR / "contribution-rhythm.svg", build_engineering_pulse(contrib))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
