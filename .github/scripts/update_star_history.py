#!/usr/bin/env python3
"""Generate a linear star-history chart (SVG) for the repo from live GitHub
stargazer data, and save it to images/star-history.svg. Dependency-free.

Run from the repo root:  python .github/scripts/update_star_history.py
"""

import datetime
import math
import os
import subprocess
import sys

REPO = os.environ.get("GITHUB_REPOSITORY", "SACHINN122/Clipo")
OUT = "images/star-history.svg"

WIDTH, HEIGHT = 900, 340
MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 64, 24, 46, 44
PLOT_W = WIDTH - MARGIN_L - MARGIN_R
PLOT_H = HEIGHT - MARGIN_T - MARGIN_B


def fetch_starred_at():
    out = subprocess.run(
        ["gh", "api", "-H", "Accept: application/vnd.github.star+json",
         "--paginate", f"repos/{REPO}/stargazers",
         "--jq", ".[] | .starred_at"],
        capture_output=True, text=True, check=True, timeout=120,
    ).stdout
    stamps = [t.strip() for t in out.splitlines() if t.strip()]
    times = sorted(
        datetime.datetime.fromisoformat(t.replace("Z", "+00:00")) for t in stamps
    )
    return times


def nice_max(v):
    if v <= 0:
        return 10
    step = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 5, 10):
        if v <= m * step:
            return m * step
    return 10 * step


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_svg(times):
    counts = list(range(1, len(times) + 1))
    total = counts[-1] if counts else 0

    first = times[0] if times else datetime.datetime.now(datetime.timezone.utc)
    last = times[-1] if times else first

    ymax = nice_max(total)
    def px_y(c):
        return MARGIN_T + PLOT_H * (1 - c / ymax)

    def px_x(i, n):
        if n <= 1:
            return MARGIN_L + PLOT_W / 2
        return MARGIN_L + PLOT_W * i / (n - 1)

    # gridline values
    yticks = [ymax * i / 4 for i in range(5)]
    # x tick indices
    n = len(counts)
    xticks = sorted({int(round(i * (n - 1) / 5)) for i in range(6)}) if n > 1 else [0]

    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="Star history for {esc(REPO)}">'
    )
    parts.append('<rect width="100%" height="100%" fill="#ffffff"/>')

    # title
    parts.append(
        f'<text x="{MARGIN_L}" y="26" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="16" font-weight="700" fill="#24292f">Star History — {esc(REPO)}</text>'
    )
    parts.append(
        f'<text x="{MARGIN_L}" y="44" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="13" fill="#57606a">{total} stars · {first.date().isoformat()} → {last.date().isoformat()}</text>'
    )

    # horizontal gridlines + y labels
    for c in yticks:
        y = px_y(c)
        parts.append(
            f'<line x1="{MARGIN_L}" y1="{y:.1f}" x2="{MARGIN_L + PLOT_W}" y2="{y:.1f}" '
            f'stroke="#d0d7de" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{MARGIN_L - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" font-size="12" fill="#57606a">{int(c)}</text>'
        )

    # vertical gridlines + x labels
    for i in xticks:
        x = px_x(i, n)
        parts.append(
            f'<line x1="{x:.1f}" y1="{MARGIN_T}" x2="{x:.1f}" y2="{MARGIN_T + PLOT_H}" '
            f'stroke="#d0d7de" stroke-width="1" stroke-dasharray="3 3"/>'
        )
        if n:
            label = times[i].date().isoformat()
            parts.append(
                f'<text x="{x:.1f}" y="{MARGIN_T + PLOT_H + 20}" text-anchor="middle" '
                f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" font-size="12" fill="#57606a">{label}</text>'
            )

    # axes
    parts.append(
        f'<line x1="{MARGIN_L}" y1="{MARGIN_T}" x2="{MARGIN_L}" y2="{MARGIN_T + PLOT_H}" stroke="#24292f" stroke-width="1.5"/>'
    )
    parts.append(
        f'<line x1="{MARGIN_L}" y1="{MARGIN_T + PLOT_H}" x2="{MARGIN_L + PLOT_W}" y2="{MARGIN_T + PLOT_H}" stroke="#24292f" stroke-width="1.5"/>'
    )

    if n:
        points = " ".join(f"{px_x(i, n):.1f},{px_y(counts[i]):.1f}" for i in range(n))
        area = f"{MARGIN_L},{MARGIN_T + PLOT_H} {points} {px_x(n - 1, n):.1f},{MARGIN_T + PLOT_H}"
        parts.append(f'<polygon points="{area}" fill="#ffd500" opacity="0.18"/>')
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="#d4a72c" stroke-width="2.5" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        # end dot + value label
        lx, ly = px_x(n - 1, n), px_y(total)
        parts.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="5" fill="#d4a72c"/>')
        parts.append(
            f'<text x="{lx + 9:.1f}" y="{ly - 6:.1f}" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
            f'font-size="13" font-weight="700" fill="#24292f">{total}</text>'
        )
    else:
        parts.append(
            f'<text x="{MARGIN_L + PLOT_W / 2}" y="{MARGIN_T + PLOT_H / 2}" text-anchor="middle" '
            f'font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" font-size="14" fill="#57606a">No stars yet — be the first!</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    times = fetch_starred_at()
    svg = build_svg(times)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"wrote {OUT} with {len(times)} star events")


if __name__ == "__main__":
    main()
