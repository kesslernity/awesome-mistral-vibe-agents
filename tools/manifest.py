#!/usr/bin/env python3
"""Write MANIFEST.json and fill the counts and tables in README.md.

Markers, not {{PLACEHOLDER}} tokens. A placeholder is consumed the first time it
is filled, so the second run has nothing to substitute and writes the literal
token into the page. Markers survive every run.

    python3 tools/manifest.py            # rewrite MANIFEST.json and README.md
    python3 tools/manifest.py --check    # exit 1 if either is out of date
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("manifest.py needs Python 3.11 or newer for tomllib.")

import tomllib  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
AGENT_DIR = REPO / ".vibe" / "agents"
PROMPT_DIR = REPO / ".vibe" / "prompts"
README = REPO / "README.md"
MANIFEST = REPO / "MANIFEST.json"

VERIFIED_AGAINST = "2.5.0"
PROFILE_KEYS = {"display_name", "description", "safety", "agent_type"}
SUMMARY_CHARS = 200


def override_keys(data: dict) -> list[str]:
    keys: list[str] = []
    for k, v in data.items():
        if k in PROFILE_KEYS:
            continue
        if k == "tools" and isinstance(v, dict):
            keys.extend(f"tools.{t}" for t in v)
        else:
            keys.append(k)
    return sorted(keys)


def summarise(description: str) -> str:
    """As many whole sentences as fit the budget, at least one.

    One sentence is not always enough: several descriptions here open with
    "Subagent." or with a four-word summary, and a table row of "Subagent."
    tells a reader nothing.
    """
    text = " ".join(description.split())
    if not text:
        return ""
    parts = re.split(r"(?<=\.)\s+", text)
    out = parts[0]
    for part in parts[1:]:
        if len(out) + 1 + len(part) > SUMMARY_CHARS:
            break
        out = f"{out} {part}"
    if len(out) <= SUMMARY_CHARS:
        return out
    return out[:SUMMARY_CHARS].rsplit(" ", 1)[0] + " ..."


def collect() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(AGENT_DIR.glob("*.toml")):
        raw = path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
        rows.append({
            "name": path.stem,
            "file": str(path.relative_to(REPO)),
            "display_name": data.get("display_name", path.stem.replace("-", " ").title()),
            "description": data.get("description", ""),
            "safety": data.get("safety", "neutral"),
            "agent_type": data.get("agent_type", "agent"),
            "system_prompt_id": data.get("system_prompt_id"),
            "enabled_tools": data.get("enabled_tools"),
            "override_keys": override_keys(data),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    return rows


def table(rows: list[dict]) -> str:
    out = ["| Profile | What it does | Keys it sets |", "|---|---|---|"]
    for r in rows:
        keys = ", ".join(f"`{k}`" for k in r["override_keys"]) or "none"
        out.append(f"| [`{r['name']}`]({r['file']}) | {summarise(r['description'])} | {keys} |")
    return "\n".join(out)


def fill(text: str, marker: str, value: str) -> str:
    pattern = re.compile(
        rf"(<!-- {re.escape(marker)}:start -->).*?(<!-- {re.escape(marker)}:end -->)",
        re.DOTALL,
    )
    if not pattern.search(text):
        sys.exit(f"README.md has no '{marker}' marker pair. Nothing was written.")
    return pattern.sub(lambda m: m.group(1) + value + m.group(2), text)


def build(rows: list[dict]) -> tuple[str, str]:
    primary = [r for r in rows if r["agent_type"] == "agent"]
    subs = [r for r in rows if r["agent_type"] == "subagent"]

    prompts = sorted(p.stem for p in PROMPT_DIR.glob("*.md"))
    manifest = {
        "verified_against": {"package": "mistral-vibe", "version": VERIFIED_AGAINST},
        "generator": "tools/manifest.py",
        "profile_count": len(rows),
        "primary_count": len(primary),
        "subagent_count": len(subs),
        "custom_prompts": prompts,
        "profiles": rows,
    }
    manifest_text = json.dumps(manifest, indent=1) + "\n"

    readme = README.read_text(encoding="utf-8")
    readme = fill(readme, "n-profiles", str(len(rows)))
    readme = fill(readme, "n-primary", str(len(primary)))
    readme = fill(readme, "n-subagents", str(len(subs)))
    readme = fill(
        readme, "badge-profiles",
        f"[![Profiles](https://img.shields.io/badge/profiles-{len(rows)}-blue)](.vibe/agents/)",
    )
    readme = fill(readme, "primary-table", "\n" + table(primary) + "\n")
    readme = fill(readme, "subagent-table", "\n" + table(subs) + "\n")
    return manifest_text, readme


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="do not write, exit 1 if anything would change")
    args = ap.parse_args()

    rows = collect()
    if not rows:
        sys.exit(f"no .toml profiles in {AGENT_DIR}")
    manifest_text, readme_text = build(rows)

    if args.check:
        stale = []
        if not MANIFEST.is_file() or MANIFEST.read_text(encoding="utf-8") != manifest_text:
            stale.append("MANIFEST.json")
        if README.read_text(encoding="utf-8") != readme_text:
            stale.append("README.md")
        if stale:
            print("stale: " + ", ".join(stale) + ". Run tools/manifest.py.")
            return 1
        print(f"MANIFEST.json and README.md match the {len(rows)} profiles on disk.")
        return 0

    MANIFEST.write_text(manifest_text, encoding="utf-8")
    README.write_text(readme_text, encoding="utf-8")
    print(f"wrote MANIFEST.json and README.md for {len(rows)} profiles "
          f"({sum(1 for r in rows if r['agent_type'] == 'agent')} primary, "
          f"{sum(1 for r in rows if r['agent_type'] == 'subagent')} subagent)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
