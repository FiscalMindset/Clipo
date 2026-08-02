#!/usr/bin/env python3
"""Regenerate the auto-managed Contributors block in README.md from live
GitHub contributor stats. Commit counts stay fresh; focus tags are static.

Run from the repo root:  python .github/scripts/update_contributors.py
"""

import json
import os
import re
import subprocess
import sys

REPO = os.environ.get("GITHUB_REPOSITORY", "SACHINN122/Clipo")

FALLBACK = {"SACHINN122": 52, "FiscalMindset": 40}

META = {
    "SACHINN122": {
        "name": "SACHIN PRAJAPATI",
        "role": "Creator",
    },
    "FiscalMindset": {
        "name": "Vicky Kumar",
        "role": "Co-developer",
    },
}


def fetch_counts():
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{REPO}/contributors", "--paginate",
             "--jq", r'.[] | "\(.login)\t\(.contributions)"'],
            capture_output=True, text=True, check=True, timeout=60,
        ).stdout
        counts = {}
        for line in out.strip().splitlines():
            if "\t" in line:
                login, n = line.split("\t")
                counts[login] = int(n)
        return counts if counts else FALLBACK
    except Exception as exc:
        print(f"warning: fetching contributors failed ({exc}); using fallback", file=sys.stderr)
        return dict(FALLBACK)


def build_section(counts):
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(counts.values())

    pie_lines = ["```mermaid", f"pie showData title Commit share ({total} total)"]
    for login, n in ordered:
        meta = META[login]
        pie_lines.append(f'    "{meta["name"]}" : {n}')
    pie_lines.append("```")

    rows = []
    for login, n in ordered:
        meta = META[login]
        rows.append(
            f"| [![{meta['name']}](https://github.com/{login}.png?size=28)]"
            f"(https://github.com/{login}) **{meta['name']}** — "
            f"[@{login}](https://github.com/{login}) | {meta['role']} |"
        )

    return (
        "Made with care by:\n\n"
        + "\n".join(pie_lines)
        + "\n\n| Contributor | Role |\n"
        + "| :--- | :--- |\n"
        + "\n".join(rows)
        + "\n"
    )


def main():
    counts = fetch_counts()
    section = build_section(counts)
    path = "README.md"
    with open(path, encoding="utf-8") as fh:
        readme = fh.read()
    pattern = re.compile(
        r"<!-- CONTRIBUTORS:START -->.*?<!-- CONTRIBUTORS:END -->", re.S
    )
    if not pattern.search(readme):
        print("error: CONTRIBUTORS markers not found in README.md", file=sys.stderr)
        sys.exit(1)
    readme = pattern.sub(
        f"<!-- CONTRIBUTORS:START -->\n{section}<!-- CONTRIBUTORS:END -->",
        readme,
        count=1,
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(readme)
    print("updated README contributors block")


if __name__ == "__main__":
    main()
