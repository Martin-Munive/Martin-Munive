#!/usr/bin/env python3
"""Build local SVG profile cards for the GitHub profile README."""

from __future__ import annotations

import datetime as dt
import html
import json
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


def fetch_languages(repos: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for repo in repos:
        if repo.get("fork") or repo.get("archived") or repo.get("name") == USERNAME:
            continue
        languages_url = repo.get("languages_url")
        if not languages_url:
            continue
        for language, size in request_json(languages_url).items():
            totals[language] = totals.get(language, 0) + int(size)
    return totals


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


def build_languages_card(languages: dict[str, int]) -> str:
    total = sum(languages.values()) or 1
    ranked = sorted(languages.items(), key=lambda item: item[1], reverse=True)
    top = ranked[:7]
    other = sum(size for _, size in ranked[7:])
    if other:
        top.append(("Other", other))
    colors = [BLUE, GREEN, RED, AMBER, VIOLET, CYAN, "#f97316", "#64748b"]
    parts = svg_header(
        "Top Languages",
        "Distribucion por bytes reportados por GitHub Linguist en repositorios publicos propios",
        820,
        324,
    )
    x = 28
    y = 88
    max_width = 590
    for index, (language, size) in enumerate(top):
        pct = size / total
        bar_width = max(4, int(max_width * pct))
        color = colors[index % len(colors)]
        row_y = y + index * 22
        parts.extend(
            [
                f'<text x="{x}" y="{row_y + 11}" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="12" fill="{TEXT}">{esc(language)}</text>',
                f'<rect x="150" y="{row_y}" width="{max_width}" height="12" rx="6" fill="{GRID_EMPTY}"/>',
                f'<rect x="150" y="{row_y}" width="{bar_width}" height="12" rx="6" fill="{color}"/>',
                f'<text x="756" y="{row_y + 11}" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="12" text-anchor="end" fill="{MUTED}">{pct * 100:.1f}%</text>',
            ]
        )
    parts.extend(
        [
            f'<text x="28" y="288" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="11" fill="{MUTED}">Fuente: GitHub Linguist por bytes en repositorios publicos propios.</text>',
            f'<text x="28" y="306" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="11" fill="{MUTED}">Markdown, documentacion, datos y codigo generado pueden quedar excluidos.</text>',
        ]
    )
    return svg_footer(parts)


def heat_color(count: int) -> str:
    if count <= 0:
        return GRID_EMPTY
    if count == 1:
        return "#14532d"
    if count <= 3:
        return "#15803d"
    if count <= 6:
        return "#22c55e"
    return "#86efac"


def build_rhythm_card(contrib: dict[str, Any]) -> str:
    calendar = contrib["contributionCalendar"]
    weeks = calendar["weeks"][-30:]
    days = [day for week in weeks for day in week["contributionDays"]]
    weekly_totals = [sum(day["contributionCount"] for day in week["contributionDays"]) for week in weeks]
    max_week = max(weekly_totals) if weekly_totals else 1
    parts = svg_header(
        "Daily / Weekly Contribution Rhythm",
        "30-week heatmap generated by this repository workflow",
        820,
        360,
    )
    parts.extend(
        [
            f'<text x="52" y="82" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="11" fill="{MUTED}">Daily heatmap</text>',
            f'<text x="512" y="82" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="11" fill="{MUTED}">Weekly volume</text>',
        ]
    )
    labels = [("L", 1), ("M", 2), ("X", 3), ("J", 4), ("V", 5), ("S", 6), ("D", 0)]
    for label, weekday in labels:
        y = 96 + weekday * 14
        parts.append(
            f'<text x="28" y="{y + 9}" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="10" fill="{MUTED}">{label}</text>'
        )
    for week_index, week in enumerate(weeks):
        for day in week["contributionDays"]:
            x = 52 + week_index * 14
            y = 96 + int(day["weekday"]) * 14
            parts.append(
                f'<rect x="{x}" y="{y}" width="10" height="10" rx="2" fill="{heat_color(int(day["contributionCount"]))}">'
                f'<title>{esc(day["date"])}: {day["contributionCount"]} contribuciones</title></rect>'
            )
    bar_x = 512
    base_y = 218
    for index, total in enumerate(weekly_totals):
        height = int(96 * (total / max_week)) if max_week else 0
        x = bar_x + index * 9
        parts.append(
            f'<rect x="{x}" y="{base_y - height}" width="6" height="{height}" rx="2" fill="{BLUE}"><title>Semana {index + 1}: {total} contribuciones</title></rect>'
        )
    last_7 = sum(day["contributionCount"] for day in days[-7:])
    last_30 = sum(day["contributionCount"] for day in days[-30:])
    parts.extend(
        [
            f'<text x="512" y="252" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="12" fill="{MUTED}">Ultimos 7 dias</text>',
            f'<text x="512" y="282" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="26" font-weight="700" fill="{GREEN}">{metric(last_7)}</text>',
            f'<text x="642" y="252" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="12" fill="{MUTED}">Ultimos 30 dias</text>',
            f'<text x="642" y="282" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="26" font-weight="700" fill="{AMBER}">{metric(last_30)}</text>',
            f'<text x="28" y="322" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="11" fill="{MUTED}">Fuente: calendario publico de contribuciones de GitHub.</text>',
            f'<text x="28" y="340" font-family="Segoe UI, Inter, Arial, sans-serif" font-size="11" fill="{MUTED}">Los pushes recientes pueden tardar en reflejarse.</text>',
        ]
    )
    return svg_footer(parts)


def main() -> int:
    repos = fetch_repos()
    contrib = fetch_contributions()
    languages = fetch_languages(repos)
    write_svg(OUT_DIR / "github-signals.svg", build_stats_card(repos, contrib))
    write_svg(OUT_DIR / "top-languages.svg", build_languages_card(languages))
    write_svg(OUT_DIR / "contribution-rhythm.svg", build_rhythm_card(contrib))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
