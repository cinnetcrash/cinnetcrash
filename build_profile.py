#!/usr/bin/env python3
"""Regenerate the GitHub profile README and its graphics from live repo data.

Everything it draws is committed into this repository as plain SVG. No badge
services, no tracking pixels, no external requests when someone views the
profile — which also means the page keeps working if some third-party service
disappears.

Usage:
    GITHUB_TOKEN=$(gh auth token) python3 build_profile.py [--dry-run]

Reads config.json for what to feature. Writes README.md and assets/*.svg.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
ASSETS = ROOT / "assets"
API = "https://api.github.com"

# Palette shared by every generated graphic. Two variants so the profile does
# not glare in one theme and vanish in the other.
#
# The categorical slots are NOT GitHub's language colours. Those fail a
# colour-vision check badly — Shell #89e051 and JavaScript #f1e05a sit ΔE 13
# apart for normal vision and ΔE 3.3 under protanopia, i.e. the same colour to
# a lot of readers. The slot order below is validated in both modes:
#   worst adjacent pair ΔE 9.1 protan / 19.6 normal (light)
#   worst adjacent pair ΔE 8.4 protan / 19.3 normal (dark)
# Every segment also carries a direct label, so identity never rests on colour.
THEMES = {
    "light": dict(
        panel="#f6f8fa", border="#d0d7de", fg="#1f2328", muted="#59636e",
        accent="#2a78d6", surface="#f6f8fa",
        slots=["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
               "#e87ba4", "#008300", "#4a3aa7", "#e34948"],
    ),
    "dark": dict(
        panel="#151b23", border="#3d444d", fg="#f0f6fc", muted="#9198a1",
        accent="#3987e5", surface="#151b23",
        slots=["#3987e5", "#d95926", "#199e70", "#c98500",
               "#d55181", "#008300", "#9085e9", "#e66767"],
    ),
}

# Colour follows the language, not its rank — so a language moving up or down
# the list does not repaint the others. Anything outside this list is folded
# into "Other" rather than given an invented hue.
LANG_SLOT_ORDER = ["Python", "R", "Nextflow", "HTML", "Shell", "JavaScript",
                   "Jupyter Notebook", "CSS"]
MAX_LANGS = 8


def lang_colour(name: str, theme: dict) -> str:
    """Stable slot for a language; grey for the 'Other' bucket."""
    if name == "Other":
        return theme["muted"]
    try:
        return theme["slots"][LANG_SLOT_ORDER.index(name) % len(theme["slots"])]
    except ValueError:
        return theme["muted"]


# ─── GitHub API ──────────────────────────────────────────────────────────────

def api(path: str, token: str) -> object:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "profile-builder"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        sys.exit(f"GitHub API {exc.code} on {path}: {exc.read()[:200].decode()}")


def fetch_repos(user: str, token: str) -> list[dict]:
    repos, page = [], 1
    while True:
        batch = api(f"/users/{user}/repos?per_page=100&page={page}&sort=pushed", token)
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


# ─── SVG helpers ─────────────────────────────────────────────────────────────

def esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


FONT = ("-apple-system,BlinkMacSystemFont,Segoe UI,Noto Sans,Helvetica,"
        "Arial,sans-serif")


def stats_svg(stats: dict, theme: dict) -> str:
    """A summary card: four numbers and a caption."""
    w, h = 760, 132
    cells = [
        ("repositories", stats["public_repos"]),
        ("stars earned", stats["stars"]),
        ("languages",    stats["n_languages"]),
        ("years active", stats["years_active"]),
    ]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="Repository statistics">',
        f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="10" '
        f'fill="{theme["panel"]}" stroke="{theme["border"]}"/>',
        f'<text x="24" y="34" font-family="{FONT}" font-size="13" '
        f'font-weight="600" fill="{theme["muted"]}" '
        f'letter-spacing="0.6">AT A GLANCE</text>',
    ]
    step = (w - 48) / len(cells)
    for i, (label, value) in enumerate(cells):
        cx = 24 + step * i
        parts.append(
            f'<text x="{cx:.0f}" y="86" font-family="{FONT}" font-size="34" '
            f'font-weight="700" fill="{theme["accent"]}">{value}</text>')
        parts.append(
            f'<text x="{cx:.0f}" y="108" font-family="{FONT}" font-size="12.5" '
            f'fill="{theme["muted"]}">{esc(label)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def languages_svg(langs: list[tuple[str, int]], theme: dict) -> str:
    """Share of repositories by primary language, as one stacked bar.

    Every segment is direct-labelled below, so a reader never has to resolve a
    colour to know what a segment is. Segments are separated by a 2 px gap in
    the surface colour so adjacent fills stay countable.
    """
    total = sum(n for _, n in langs) or 1
    w, bar_y, bar_h, gap = 760, 44, 16, 2
    per_row = 4
    rows = (len(langs) + per_row - 1) // per_row
    h = bar_y + bar_h + 22 + rows * 22 + 8
    inner = w - 48

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="Share of repositories by primary language">',
        f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="10" '
        f'fill="{theme["panel"]}" stroke="{theme["border"]}"/>',
        f'<text x="24" y="30" font-family="{FONT}" font-size="13" '
        f'font-weight="600" fill="{theme["muted"]}" '
        f'letter-spacing="0.6">REPOSITORIES BY PRIMARY LANGUAGE</text>',
        f'<clipPath id="barclip"><rect x="24" y="{bar_y}" width="{inner}" '
        f'height="{bar_h}" rx="{bar_h/2:.1f}"/></clipPath>',
        '<g clip-path="url(#barclip)">',
    ]
    x = 24.0
    for i, (name, n) in enumerate(langs):
        seg = inner * n / total
        draw = seg - gap if i < len(langs) - 1 else seg
        parts.append(f'<rect x="{x:.2f}" y="{bar_y}" width="{max(draw, 0.5):.2f}" '
                     f'height="{bar_h}" fill="{lang_colour(name, theme)}"/>')
        x += seg
    parts.append("</g>")

    ly = bar_y + bar_h + 34
    for i, (name, n) in enumerate(langs):
        col, row = i % per_row, i // per_row
        lx = 24 + col * (inner / per_row)
        pct = 100 * n / total
        parts.append(f'<circle cx="{lx+5:.0f}" cy="{ly + row*22 - 4:.0f}" r="5" '
                     f'fill="{lang_colour(name, theme)}"/>')
        parts.append(
            f'<text x="{lx+18:.0f}" y="{ly + row*22:.0f}" font-family="{FONT}" '
            f'font-size="12.5" fill="{theme["fg"]}">{esc(name)} '
            f'<tspan fill="{theme["muted"]}">{pct:.0f}%</tspan></text>')
    parts.append("</svg>")
    return "\n".join(parts)


def timeline_svg(projects: list[dict], theme: dict) -> str:
    """One horizontal bar per featured project: first commit to last push.

    This replaces an earlier "pushes per month" column chart, which counted each
    repository once at its most recent push and so turned a day of bulk edits
    into a fake spike. Span of activity is something the API actually knows.
    """
    if not projects:
        return ""
    row_h, top, pad_l = 26, 52, 210
    w = 760
    label_gutter = 58        # room for the "5 yr" / "18 mo" duration label
    h = top + row_h * len(projects) + 34

    lo = min(p["start"] for p in projects)
    hi = max(p["end"] for p in projects)
    span = max((hi - lo).days, 1)
    plot_l, plot_r = pad_l, w - 28 - label_gutter
    plot_w = plot_r - plot_l

    def px(d) -> float:
        return plot_l + plot_w * (d - lo).days / span

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="Active period of each featured project">',
        f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="10" '
        f'fill="{theme["panel"]}" stroke="{theme["border"]}"/>',
        f'<text x="24" y="30" font-family="{FONT}" font-size="13" '
        f'font-weight="600" fill="{theme["muted"]}" '
        f'letter-spacing="0.6">PROJECT TIMELINE &#183; FIRST COMMIT TO LAST PUSH</text>',
    ]

    # Year gridlines, recessive.
    for year in range(lo.year, hi.year + 1):
        jan = datetime(year, 1, 1, tzinfo=timezone.utc)
        if not (lo <= jan <= hi):
            continue
        gx = px(jan)
        parts.append(f'<line x1="{gx:.1f}" y1="{top-14}" x2="{gx:.1f}" '
                     f'y2="{h-26}" stroke="{theme["border"]}" stroke-width="1"/>')
        parts.append(f'<text x="{gx:.1f}" y="{h-10}" font-family="{FONT}" '
                     f'font-size="11" fill="{theme["muted"]}" '
                     f'text-anchor="middle">{year}</text>')

    for i, proj in enumerate(projects):
        y = top + row_h * i
        x0, x1 = px(proj["start"]), px(proj["end"])
        bw = max(x1 - x0, 4)
        parts.append(
            f'<text x="{pad_l-12}" y="{y+11}" font-family="{FONT}" font-size="12" '
            f'fill="{theme["fg"]}" text-anchor="end">{esc(proj["name"])}</text>')
        parts.append(
            f'<rect x="{x0:.1f}" y="{y}" width="{bw:.1f}" height="12" rx="4" '
            f'fill="{theme["accent"]}"/>')
        months = max(1, round((proj["end"] - proj["start"]).days / 30.4))
        label = f'{months} mo' if months < 24 else f'{months//12} yr'
        parts.append(
            f'<text x="{x0 + bw + 8:.1f}" y="{y+11}" '
            f'font-family="{FONT}" font-size="11" fill="{theme["muted"]}">'
            f'{label}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def picture(name: str, alt: str) -> str:
    """GitHub-safe light/dark image switch."""
    return (f'<picture>\n'
            f'  <source media="(prefers-color-scheme: dark)" '
            f'srcset="assets/{name}-dark.svg">\n'
            f'  <img alt="{esc(alt)}" src="assets/{name}-light.svg" width="100%">\n'
            f'</picture>')


# ─── Aggregation ─────────────────────────────────────────────────────────────

def summarise(repos: list[dict], user_created: str) -> dict:
    own = [r for r in repos if not r["fork"]]

    counts: dict[str, int] = {}
    for r in own:
        if r.get("language"):
            counts[r["language"]] = counts.get(r["language"], 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    langs = ranked[:MAX_LANGS]
    tail = sum(n for _, n in ranked[MAX_LANGS:])
    if tail:                      # never silently truncate — fold the rest in
        langs.append(("Other", tail))

    created = datetime.fromisoformat(user_created.replace("Z", "+00:00"))
    years = max(1, round((datetime.now(timezone.utc) - created).days / 365.25))

    return {
        "public_repos": len([r for r in repos if not r["private"]]),
        "stars":        sum(r["stargazers_count"] for r in own),
        "n_languages":  len(counts),
        "years_active": years,
        "languages":    langs,
    }


def timeline_data(by_name: dict[str, dict], names: list[str]) -> list[dict]:
    """Featured projects as (name, first commit, last push), longest first."""
    out = []
    for name in names:
        r = by_name.get(name)
        if r is None:
            continue
        start = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00"))
        if end < start:
            end = start
        out.append({"name": name, "start": start, "end": end})
    return sorted(out, key=lambda p: p["start"])


def table(repos_by_name: dict[str, dict], names: list[str], blurbs: dict) -> str:
    rows = ["| Repository | What it does |", "|---|---|"]
    for name in names:
        r = repos_by_name.get(name)
        if r is None:
            continue                      # renamed or deleted: drop it silently
        desc = blurbs.get(name) or r.get("description") or "—"
        star = f" ⭐{r['stargazers_count']}" if r["stargazers_count"] else ""
        rows.append(f"| [**{name}**](https://github.com/{r['full_name']}){star} | {desc} |")
    return "\n".join(rows) if len(rows) > 2 else ""


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="render to stdout without writing files")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is not set. Try: GITHUB_TOKEN=$(gh auth token) "
                 f"python3 {Path(__file__).name}")

    cfg = json.loads((ROOT / "config.json").read_text())
    user = cfg["user"]

    repos = fetch_repos(user, token)
    by_name = {r["name"]: r for r in repos}
    profile = api(f"/users/{user}", token)
    stats = summarise(repos, profile["created_at"])

    featured = [n for g in cfg["sections"] for n in g["repos"]]
    timeline = timeline_data(by_name, featured)

    ASSETS.mkdir(exist_ok=True)
    if not args.dry_run:
        for theme_name, theme in THEMES.items():
            (ASSETS / f"stats-{theme_name}.svg").write_text(stats_svg(stats, theme))
            (ASSETS / f"languages-{theme_name}.svg").write_text(
                languages_svg(stats["languages"], theme))
            (ASSETS / f"timeline-{theme_name}.svg").write_text(
                timeline_svg(timeline, theme))

    sections = []
    for group in cfg["sections"]:
        body = table(by_name, group["repos"], cfg.get("blurbs", {}))
        if body:
            sections.append(f"## {group['title']}\n\n{body}")

    live = []
    for label, url in cfg.get("sites", {}).items():
        live.append(f"| [{label}]({url}) | {url} |")
    sites_block = ("## Live sites\n\n| Page | URL |\n|---|---|\n" + "\n".join(live)
                   if live else "")

    readme = cfg["intro"].rstrip() + "\n\n"
    readme += picture("stats", "Repository statistics") + "\n\n"
    readme += picture("languages", "Language distribution") + "\n\n"
    readme += "\n\n".join(sections) + "\n\n"
    if sites_block:
        readme += sites_block + "\n\n"
    readme += picture("timeline", "Active period of each featured project") + "\n\n"
    readme += cfg["outro"].rstrip() + "\n\n"
    readme += (f"<sub>Generated by "
               f"[`build_profile.py`](build_profile.py) on "
               f"{datetime.now(timezone.utc):%Y-%m-%d}.</sub>\n")

    if args.dry_run:
        print(readme)
    else:
        (ROOT / "README.md").write_text(readme)
        print(f"README.md + 6 SVG written. "
              f"{stats['public_repos']} public repos, {stats['stars']} stars, "
              f"{stats['n_languages']} languages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
