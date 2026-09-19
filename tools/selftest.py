#!/usr/bin/env python3
"""Prove that tools/verify.py rejects what it claims to reject.

A checker nobody checks decays quietly: a rule gets narrowed, the suite still
passes, and the verdict it used to produce is gone. Every FAIL and WARN rule in
verify.py gets a deliberately broken profile here, and this script asserts that
the rule fires on it.

    ~/.local/share/uv/tools/mistral-vibe/bin/python tools/selftest.py

Add a rule to verify.py, add its case here in the same commit.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VERIFY = REPO / "tools" / "verify.py"

VALID = """display_name = "Probe"
description = "A profile that is valid apart from the one defect under test."
safety = "safe"
agent_type = "agent"
"""

# (case name, filename, file body, expected verdict, marker that must appear)
CASES: list[tuple[str, str, str, str, str]] = [
    (
        "unparseable TOML",
        "broken.toml",
        'display_name = "Broken\ndescription = "unterminated string',
        "FAIL",
        "is not valid TOML",
    ),
    (
        "stem collides with a built-in",
        "plan.toml",
        VALID,
        "FAIL",
        "silently OVERRIDES the built-in",
    ),
    (
        "name key is ignored",
        "has-name.toml",
        VALID + 'name = "something-else"\n',
        "FAIL",
        "has a 'name' key",
    ),
    (
        "install_required does nothing",
        "wants-install.toml",
        VALID + "install_required = true\n",
        "FAIL",
        "has 'install_required'",
    ),
    (
        "bad safety value",
        "bad-safety.toml",
        'display_name = "X"\ndescription = "d"\nsafety = "readonly"\n',
        "FAIL",
        "is not one of ['destructive', 'neutral', 'safe', 'yolo']",
    ),
    (
        "bad agent_type value",
        "bad-type.toml",
        'display_name = "X"\ndescription = "d"\nagent_type = "helper"\n',
        "FAIL",
        "is not one of ['agent', 'subagent']",
    ),
    (
        "unknown top-level key",
        "typo-key.toml",
        VALID + 'systemprompt_id = "cli"\n',
        "FAIL",
        "is not a VibeConfig field",
    ),
    (
        "unknown key inside a tool table",
        "typo-tool-key.toml",
        VALID + "\n[tools.bash]\ntimeout = 900\n",
        "FAIL",
        "is not a field of this tool's config",
    ),
    (
        "table for a tool that does not exist",
        "ghost-tool.toml",
        VALID + '\n[tools.shell]\npermission = "never"\n',
        "FAIL",
        "is not a tool Vibe discovers",
    ),
    (
        "enabled_tools names an unknown tool",
        "ghost-enabled.toml",
        VALID + 'enabled_tools = ["read_file", "shell"]\n',
        "FAIL",
        "leaves the agent with ZERO tools",
    ),
    (
        "bad permission value",
        "bad-permission.toml",
        VALID + '\n[tools.write_file]\npermission = "deny"\n',
        "FAIL",
        "the whole profile is DROPPED",
    ),
    (
        "relative path pattern cannot match",
        "relative-allowlist.toml",
        VALID + '\n[tools.write_file]\npermission = "never"\nallowlist = ["drafts/*"]\n',
        "FAIL",
        "RESOLVED ABSOLUTE path",
    ),
    (
        "tilde path pattern cannot match",
        "tilde-allowlist.toml",
        VALID + '\n[tools.write_file]\nallowlist = ["~/drafts/*"]\n',
        "FAIL",
        "does not expand for a tool pattern",
    ),
    (
        "active_model is not an alias",
        "ghost-model.toml",
        VALID + 'active_model = "devstral-medium"\n',
        "FAIL",
        "crashes later",
    ),
    (
        "custom system prompt is missing",
        "ghost-prompt.toml",
        VALID + 'system_prompt_id = "no-such-prompt"\n',
        "FAIL",
        "does not exist",
    ),
    (
        "stem is not kebab case",
        "Not_Kebab.toml",
        VALID,
        "FAIL",
        "is not lower-case-kebab",
    ),
    (
        "house rule: no description",
        "no-description.toml",
        'display_name = "X"\nsafety = "safe"\n',
        "FAIL",
        "has no description",
    ),
    (
        "house rule: em dash",
        "em-dash.toml",
        'display_name = "X"\ndescription = "A dash — here."\n',
        "FAIL",
        "contains em dash",
    ),
    (
        "bash denylist replaces the defaults",
        "thin-denylist.toml",
        VALID + '\n[tools.bash]\ndenylist = ["curl"]\n',
        "WARN",
        "REPLACES Vibe's default list",
    ),
    (
        "task allowlist drops explore",
        "forgot-explore.toml",
        VALID + '\n[tools.task]\nallowlist = ["my-subagent"]\n',
        "WARN",
        "explore subagent now prompts",
    ),
    (
        "models list replaces the defaults",
        "own-models.toml",
        VALID + '\n[[models]]\nname = "x"\nprovider = "mistral"\nalias = "x"\n',
        "WARN",
        "REPLACES rather than merges",
    ),
    (
        "grep excludes replace the defaults",
        "own-excludes.toml",
        VALID + '\n[tools.grep]\nexclude_patterns = ["node_modules/"]\n',
        "WARN",
        "replaces Vibe's 23 default excludes",
    ),
]


def run(agent_dir: Path, prompts: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(VERIFY), str(agent_dir), "--prompts", str(prompts),
         "--house"],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    failures: list[str] = []
    prompts = REPO / ".vibe" / "prompts"

    for name, filename, body, verdict, marker in CASES:
        with tempfile.TemporaryDirectory(prefix="vibe-selftest-") as tmp:
            d = Path(tmp)
            (d / filename).write_text(body, encoding="utf-8")
            code, out = run(d, prompts)
            want_code = 1 if verdict == "FAIL" else 0
            problems = []
            if code != want_code:
                problems.append(f"exit {code}, wanted {want_code}")
            if f"{verdict}  " not in out:
                problems.append(f"no {verdict} line")
            if marker not in out:
                problems.append(f"missing marker {marker!r}")
            if problems:
                failures.append(f"{name}: {'; '.join(problems)}\n{out}")
                print(f"  fail  {name}")
            else:
                print(f"  ok    {name}")

    code, out = run(REPO / ".vibe" / "agents", prompts)
    if code != 0:
        failures.append(f"the repo's own profiles do not pass:\n{out}")
        print("  fail  the repo's own profiles pass clean")
    else:
        print("  ok    the repo's own profiles pass clean")

    print()
    if failures:
        for f in failures:
            print(f)
        print(f"{len(failures)} of {len(CASES) + 1} selftest cases failed. "
              "verify.py is not checking what this file says it checks.")
        return 1
    print(f"{len(CASES) + 1} selftest cases pass. Every rule in verify.py fires "
          "on a profile that breaks it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
