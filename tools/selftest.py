#!/usr/bin/env python3
"""Prove that tools/verify.py rejects what it claims to reject.

A checker nobody checks decays quietly: a rule gets narrowed, the suite still
passes, and the verdict it used to produce is gone. A case here is a small
profile, most of them deliberately broken, that verify.py has to reject, warn
about, note or pass. This script asserts the exit code and the line.

It also reads verify.py itself, as a floor under the cases. The reading knows a
PLACE by the way it is written, inside a top-level `def` of verify.py. A
recording call: `rep.fail(...)`, `rep.warn(...)` or `<x>.notes.append(...)`,
with a positional argument. A reason check_path_pattern returns, written out.
A printed line: `print(...)` or `say(...)` whose first argument is written out
and begins with FAIL, WARN or note. The longest fixed text of each place has to
show up in the output of a case, run in the mode that can print it, or stand in
NO_CASE below with the reason nothing here provokes it. A recording call whose
message is not written out in the call, or whose fixed text is under eight
characters, fails the reading: it is not passed over.

What the reading does not do, so that nobody takes it for more. It knows a
place by its fixed text, not by its logic: two places that print the same words
count as one, a text counts as shown wherever its words stand in what a case
printed, and the reading cannot tell that the case which shows a text is the
case that was meant for it. Where one call holds two messages, only the longer
is looked for, and a text that is part of a NO_CASE key is excused with it. It
knows a place by its spelling, not by its effect: a FAIL recorded through a
report that is not named `rep`, in a method of a top-level class, with keyword
arguments only, or by writing to the report's lists directly, is not a place
and passes with no case, and so does a line written out by anything but `print`
or `say`. The text of a recording call in main() is looked for under a Vibe 3
interpreter only. A printed line is passed over when its first argument holds
under eight characters of fixed text after the word, which is also how
verify.py prints the findings it has recorded and, in two of the three calls
that print one, a note about the interpreter: through a variable alone. The
third of those calls is written out: it is a place, and it stands in NO_CASE.
And it says nothing about `--record` and `--json`, nor about the exit on a
Python older than 3.11. Today verify.py records through those three calls only,
apart from the two methods of its Report class, which are the recording itself.

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

# Lines of verify.py that no case provokes, each with its reason. The key is text
# of the message as verify.py writes it.
NO_CASE: dict[str, str] = {
    "did not find this profile and recorded no reason":
        "a guard: the one kind of file Vibe 3.1.4 was seen to leave out with no reason "
        "recorded is a file named after an approval policy, and that has a line of its own",
    "is reserved for hook matching: Vibe":
        "Vibe 3.1.4 records the reserved name itself, and that line has a case; this "
        "one is for a Vibe 3 that does not",
    "leaves its subagent session: the tool checks for it were skipped":
        "needs a Vibe 3 without the function that computes a subagent's tools",
    "AgentManager did not load:":
        "a guard: a profile that passes every rule and that Vibe 2.5.0 then does not list",
    "these profiles override built-ins:":
        "cannot print: the same filename already fails in the rules for one file",
    "Vibe is not importable here, running static checks only.":
        "about the interpreter, not about a profile: it needs a Python with no Vibe",
}
# The two lines of the 2.5.0 rules that need the live load, so the static mirror
# cannot print them.
LIVE_ONLY = ("AgentProfile.from_toml raises", "apply_to_config raises")
# Every output verify.py gave during this run, for the reading at the end, by the
# kind of run: the 2.5.0 rules (live under Vibe CLI 2.5.0, their static mirror
# otherwise) and the Vibe 3 mode. The same words can stand in both, and a case of
# one must not count for the other.
OUTPUTS: dict[str, list[str]] = {"rules": [], "vibe3": []}
# Set by main() from the mode the interpreter gives.
VIBE3 = False


def pool(extra: tuple[str, ...]) -> str:
    """Which kind of run a verify.py call was: under Vibe 3 the 2.5.0 rules are run
    with --static-only, and everything else there is the Vibe 3 mode."""
    return "vibe3" if VIBE3 and "--static-only" not in extra else "rules"

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
        "tools is not a table",
        "tools-not-a-table.toml",
        VALID + 'tools = "bash"\n',
        "FAIL",
        "'tools' is not a table",
    ),
    (
        "a tool's entry is not a table",
        "tool-not-a-table.toml",
        VALID + "\n[tools]\nbash = 1\n",
        "FAIL",
        "[tools.bash]: is not a table of settings",
    ),
    (
        "an allowlist entry is not a string",
        "allowlist-number.toml",
        VALID + '\n[tools.write_file]\npermission = "never"\nallowlist = [1]\n',
        "FAIL",
        "allowlist entry 1 is not a string",
    ),
    (
        "enabled_tools is not a list",
        "tools-string.toml",
        VALID + 'enabled_tools = "bash"\n',
        "FAIL",
        "enabled_tools is not a list",
    ),
    (
        "an enabled_tools entry is not a string",
        "enabled-number.toml",
        VALID + "enabled_tools = [1]\n",
        "FAIL",
        "enabled_tools entry 1 is not a string",
    ),
    (
        "an enabled_tools pattern matches no tool",
        "ghost-pattern.toml",
        VALID + 'enabled_tools = ["zzz*"]\n',
        "FAIL",
        "matches no known tool",
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
        'display_name = "X"\ndescription = "A dash \u2014 here."\n',
        "FAIL",
        "contains em dash",
    ),
    (
        "house rule: no display_name",
        "no-display-name.toml",
        'description = "A profile with no display name."\nsafety = "safe"\n',
        "FAIL",
        "has no display_name",
    ),
    (
        "house rule: en dash",
        "en-dash.toml",
        'display_name = "X"\ndescription = "A range, 1\u20132."\n',
        "FAIL",
        "contains en dash",
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
        "providers list replaces the defaults",
        "own-providers.toml",
        VALID + '\n[[providers]]\nname = "mistral"\napi_base = "https://api.mistral.ai/v1"\n'
        'api_key_env_var = "MISTRAL_API_KEY"\n',
        "WARN",
        "sets 'providers'",
    ),
    (
        "grep excludes replace the defaults",
        "own-excludes.toml",
        VALID + '\n[tools.grep]\nexclude_patterns = ["node_modules/"]\n',
        "WARN",
        "replaces Vibe's 23 default excludes",
    ),
    (
        "one key in the bash table leaves both lists to the config.toml Vibe reads",
        "one-key-bash.toml",
        VALID + '\n[tools.bash]\ndefault_timeout = 600\n',
        "NOTE",
        "without restating 'denylist'",
    ),
    (
        "one key in a read tool's table leaves its permission to the config.toml Vibe reads",
        "one-key-read.toml",
        VALID + '\n[tools.read_file]\nmax_read_bytes = 1000\n',
        "NOTE",
        "permission falls from 'always' to 'ask'",
    ),
    (
        "one key in the task table leaves its allowlist to the config.toml Vibe reads",
        "one-key-task.toml",
        VALID + '\n[tools.task]\ndenylist = ["some-agent"]\n',
        "NOTE",
        "without restating 'allowlist'",
    ),
]

# The rules of Vibe 3 mode. They run only under an interpreter that has Vibe 3, where
# verify.py asks Vibe what it recorded about each file. NOTE means exit 0 and the
# marker on a line that starts with "note". PASS means exit 0, no FAIL and no WARN
# line, and the marker anywhere.
SUBAGENT = """display_name = "Probe"
description = "A subagent that is valid apart from the one defect under test."
agent_type = "subagent"
"""
V3_CASES: list[tuple[str, str, str, str, str]] = [
    (
        "Vibe 3 mode: unparseable TOML",
        "v3-broken.toml",
        'display_name = "Broken\ndescription = "unterminated string',
        "FAIL",
        "is not valid TOML",
    ),
    (
        "Vibe 3 mode: stem is not kebab case",
        "Not_Kebab.toml",
        VALID,
        "FAIL",
        "is not lower-case-kebab",
    ),
    (
        "Vibe 3 mode, house rule: no description",
        "v3-no-description.toml",
        'display_name = "X"\n',
        "FAIL",
        "has no description",
    ),
    (
        "Vibe 3 mode, house rule: no display_name",
        "v3-no-display-name.toml",
        'description = "A profile with no display name."\n',
        "FAIL",
        "has no display_name",
    ),
    (
        "Vibe 3 mode, house rule: em dash",
        "v3-em-dash.toml",
        'display_name = "X"\ndescription = "A dash \u2014 here."\n',
        "FAIL",
        "contains em dash",
    ),
    (
        "Vibe 3 mode, house rule: en dash",
        "v3-en-dash.toml",
        'display_name = "X"\ndescription = "A range, 1\u20132."\n',
        "FAIL",
        "contains en dash",
    ),
    (
        "Vibe 3 denies a subagent a tool its own filter switches off by pattern",
        "v3-subagent-filtered.toml",
        SUBAGENT + 'enabled_tools = ["read_file", "bash"]\ndisabled_tools = ["ba*"]\n',
        "FAIL",
        "although its file lists it in enabled_tools",
    ),
    (
        "Vibe 3 keeps the built-in agent when the file named after it cannot be used",
        "explore.toml",
        SUBAGENT + "\n[tools.bash]\ndefault_timeout = 900\n",
        "FAIL",
        "is the name of a built-in agent",
    ),
    (
        "Vibe 3 ignores an allowlist in an agent file",
        "v3-allowlist.toml",
        VALID + '\n[tools.bash]\nallowlist = ["make"]\n',
        "FAIL",
        "ignores 'tools.bash.allowlist'",
    ),
    (
        "Vibe 3 ignores a denylist in an agent file",
        "v3-denylist.toml",
        VALID + '\n[tools.bash]\ndenylist = ["curl"]\n',
        "FAIL",
        "ignores 'tools.bash.denylist'",
    ),
    (
        "Vibe 3 drops a permission that loosens",
        "v3-always.toml",
        VALID + '\n[tools.write_file]\npermission = "always"\n',
        "FAIL",
        "ignores 'tools.write_file.permission'",
    ),
    (
        "Vibe 3 ignores a context setting",
        "v3-context.toml",
        VALID + "include_project_context = false\n",
        "FAIL",
        "ignores 'include_project_context'",
    ),
    (
        "Vibe 3 refuses half a timeout pair",
        "v3-timeout.toml",
        VALID + "\n[tools.bash]\ndefault_timeout = 900\n",
        "FAIL",
        "cannot use this profile",
    ),
    (
        "Vibe 3 has no tool of that name",
        "v3-old-edit-tool.toml",
        VALID + 'enabled_tools = ["read_file", "search_replace"]\n',
        "FAIL",
        "has no tool of that name",
    ),
    (
        "Vibe 3 runs no tool for a retired name",
        "v3-retired-name.toml",
        VALID + 'enabled_tools = ["read_file", "grep"]\n',
        "FAIL",
        "a former tool name",
    ),
    (
        "Vibe 3 keeps skills the profile cannot open",
        "v3-skills.toml",
        VALID + 'enabled_tools = ["read_file"]\nenabled_skills = ["*-review"]\n',
        "FAIL",
        "can open none of the skills it keeps",
    ),
    (
        "Vibe 3 falls back on a model it does not have",
        "v3-model.toml",
        VALID + 'active_model = "no-such-model"\n',
        "FAIL",
        "runs its default model",
    ),
    (
        "Vibe 3 gives a subagent no shell under never",
        "v3-subagent-shell.toml",
        SUBAGENT + 'enabled_tools = ["read_file", "bash"]\n\n[tools.bash]\n'
        'permission = "never"\nallowlist = ["git diff"]\n',
        "FAIL",
        "refuses every call this subagent makes to 'bash'",
    ),
    (
        "Vibe 3 denies a subagent a tool its own list switches off",
        "v3-subagent-listed-and-off.toml",
        SUBAGENT + 'enabled_tools = ["read_file", "bash"]\ndisabled_tools = ["bash"]\n',
        "FAIL",
        "names it in enabled_tools and in disabled_tools",
    ),
    (
        "Vibe 3 does not load a file named after a policy as an agent",
        "ask.toml",
        VALID,
        "FAIL",
        "is the name of an approval policy",
    ),
    (
        "Vibe 3 refuses the reserved name",
        "main.toml",
        VALID,
        "FAIL",
        "is reserved for hook matching",
    ),
    (
        "Vibe 3: a stem that overrides a built-in agent",
        "explore.toml",
        VALID,
        "FAIL",
        "OVERRIDES the built-in agent",
    ),
    (
        "Vibe 3 ignores the safety label, and it is a note",
        "v3-label.toml",
        VALID,
        "NOTE",
        "ignores 'safety' in an agent file",
    ),
    (
        "Vibe 3 keeps a profile that only narrows",
        "v3-narrows.toml",
        'display_name = "Probe"\ndescription = "Narrows and nothing else."\n'
        'enabled_tools = ["read_file", "write_file"]\n\n[tools.write_file]\n'
        'permission = "never"\n',
        "PASS",
        "recorded no file here that it cannot use",
    ),
]
STATUS = REPO / "docs" / "vibe-3-status.json"


def run(agent_dir: Path, prompts: Path, *extra: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(VERIFY), str(agent_dir), "--prompts", str(prompts),
         "--house", *extra],
        capture_output=True, text=True,
    )
    OUTPUTS[pool(extra)].append(proc.stdout + proc.stderr)
    return proc.returncode, proc.stdout + proc.stderr


MIN_TEXT = 8
WORDS = ("FAIL", "WARN", "note")


def places_with_no_case(mode: str) -> list[str]:
    """The places of verify.py (see the docstring at the top) whose fixed text
    showed up in no output of this run and is not in NO_CASE, and the places the
    reading cannot read. Which places count depends on the mode: the Vibe 3
    function's can only print under Vibe 3, the live load of the 2.5.0 rules only
    under Vibe CLI 2.5.0."""
    import ast

    def literal(node: ast.AST) -> list[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.JoinedStr):
            runs, buf = [], ""
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    buf += part.value
                else:
                    runs.append(buf)
                    buf = ""
            return runs + [buf]
        if isinstance(node, ast.BinOp):
            return literal(node.left) + literal(node.right)
        if isinstance(node, ast.IfExp):
            return literal(node.body) + literal(node.orelse)
        return []

    def longest(node: ast.AST) -> str:
        return max((" ".join(run.split()) for run in literal(node)), key=len, default="")

    # (kind of run that can print it, line, function, fixed text)
    places: list[tuple[str, int, str, str]] = []
    unread: list[str] = []
    tree = ast.parse(VERIFY.read_text(encoding="utf-8"))
    for func in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
        kind = {"verify_file_v3": "vibe3", "live_discovery": "live250"}.get(func.name, "rules")
        for node in ast.walk(func):
            if isinstance(node, ast.Return) and func.name == "check_path_pattern" and node.value:
                text = longest(node.value)
                if text:
                    places.append(("rules", node.lineno, func.name, text))
                continue
            if not isinstance(node, ast.Call) or not node.args:
                continue
            f = node.func
            recorded = isinstance(f, ast.Attribute) and (
                (isinstance(f.value, ast.Name) and f.value.id == "rep" and f.attr in ("fail", "warn"))
                or (isinstance(f.value, ast.Attribute) and f.value.attr == "notes" and f.attr == "append"))
            printed = isinstance(f, ast.Name) and f.id in ("print", "say")
            if recorded:
                message = node.args[1] if f.attr in ("fail", "warn") and len(node.args) > 1 else node.args[0]
                text = longest(message)
                if len(text) < MIN_TEXT:
                    unread.append(f"verify.py:{node.lineno} ({func.name}): the message is not "
                                  "written out in the call, or its fixed text is under "
                                  f"{MIN_TEXT} characters")
                    continue
                # main() records one note, and only in the Vibe 3 mode.
                places.append(("vibe3" if func.name == "main" else kind, node.lineno, func.name, text))
            elif printed:
                runs = literal(node.args[0])
                first = runs[0].strip() if runs else ""
                if not first.startswith(WORDS):
                    continue
                text = longest(node.args[0])
                for word in WORDS:
                    text = text.removeprefix(word).strip()
                if len(text) < MIN_TEXT:
                    continue  # passed over, as every line printed through a variable alone is: see the docstring
                places.append(("any" if func.name == "main" else kind, node.lineno, func.name, text))

    def seen(kinds: tuple[str, ...]) -> str:
        return " ".join(" ".join(out.split()) for k in kinds for out in OUTPUTS[k])

    rules, vibe3, both = seen(("rules",)), seen(("vibe3",)), seen(("rules", "vibe3"))
    missing = list(unread)
    for kind, line, func, text in places:
        if kind == "vibe3":
            if mode != "live-vibe3":
                continue
            where = vibe3
        elif kind == "live250":
            if mode != "live-2.5.0":
                continue
            where = rules
        elif kind == "any":
            where = both
        else:
            if mode != "live-2.5.0" and any(text.startswith(live) for live in LIVE_ONLY):
                continue
            where = rules
        if text in where or any(key in text or text in key for key in NO_CASE):
            continue
        missing.append(f"verify.py:{line} ({func}): {text[:90]}")
    return missing


def command_line_fails(prompts: Path) -> str | None:
    """A path that is not a directory, then an empty folder: verify.py has to exit 1
    and say which. Returns None when it does, else what it printed."""
    with tempfile.TemporaryDirectory(prefix="vibe-selftest-") as tmp:
        empty = Path(tmp) / "empty"
        empty.mkdir()
        for target, words in ((Path(tmp) / "no-such-folder", "is not a directory"),
                              (empty, "no .toml files in")):
            proc = subprocess.run([sys.executable, str(VERIFY), str(target), "--prompts",
                                   str(prompts)], capture_output=True, text=True)
            out = proc.stdout + proc.stderr
            OUTPUTS["rules"].append(out)
            if proc.returncode != 1 or words not in out:
                return f"exit {proc.returncode}, wanted 1 and the words {words!r}\n{out}"
    return None


def string_list_names_no_letters(prompts: Path) -> str | None:
    """Vibe 3 mode, a file whose enabled_tools is a string and not a list: Vibe's own
    line has to print, and no line may name a letter of the string as a tool. The
    first version walked the string and printed "names 'b'", "names 'a'" and so on."""
    with tempfile.TemporaryDirectory(prefix="vibe-selftest-") as tmp:
        (Path(tmp) / "v3-string-list.toml").write_text(VALID + 'enabled_tools = "bash"\n',
                                                        encoding="utf-8")
        code, out = run(Path(tmp), prompts)
        if code == 1 and "cannot use this profile" in out and "names 'b'" not in out:
            return None
        return f"exit {code}, wanted 1, Vibe's own line and no line naming a letter\n{out}"


def which_mode() -> str:
    proc = subprocess.run([sys.executable, str(VERIFY), "--mode"],
                          capture_output=True, text=True)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return lines[-1].strip() if lines else "static"


def check_cases(cases, prompts: Path, failures: list[str], *extra: str) -> None:
    for name, filename, body, verdict, marker in cases:
        with tempfile.TemporaryDirectory(prefix="vibe-selftest-") as tmp:
            d = Path(tmp)
            (d / filename).write_text(body, encoding="utf-8")
            code, out = run(d, prompts, *extra)
            want_code = 1 if verdict == "FAIL" else 0
            lines = out.splitlines()
            problems = []
            if code != want_code:
                problems.append(f"exit {code}, wanted {want_code}")
            if verdict == "PASS":
                if any(ln.startswith(("FAIL  ", "WARN  ")) for ln in lines):
                    problems.append("a FAIL or WARN line where none was wanted")
                if marker not in out:
                    problems.append(f"missing marker {marker!r}")
            else:
                # The marker has to sit on a line of the verdict's own kind.
                line_start = "note  " if verdict == "NOTE" else f"{verdict}  "
                if not any(ln.startswith(line_start) and marker in ln for ln in lines):
                    problems.append(f"no {line_start.strip()} line holding {marker!r}")
            if problems:
                failures.append(f"{name}: {'; '.join(problems)}\n{out}")
                print(f"  fail  {name}")
            else:
                print(f"  ok    {name}")


def duplicate_stem_fires(prompts: Path, *extra: str) -> str | None:
    """Two folders that each hold a file of the same name: the second must FAIL.
    Returns None when it does, else what verify.py printed."""
    with tempfile.TemporaryDirectory(prefix="vibe-selftest-") as tmp:
        first, second = Path(tmp) / "first", Path(tmp) / "second"
        for folder in (first, second):
            folder.mkdir()
            (folder / "twice.toml").write_text(VALID, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(VERIFY), str(first), str(second), "--prompts",
             str(prompts), "--house", *extra], capture_output=True, text=True)
        out = proc.stdout + proc.stderr
        OUTPUTS[pool(extra)].append(out)
        if proc.returncode == 1 and "duplicate stem" in out:
            return None
        return f"exit {proc.returncode}, wanted 1 and the words 'duplicate stem'\n{out}"


def two_folders_load(prompts: Path, *extra: str) -> str | None:
    """Two folders, one valid file in each, different names: both have to reach
    Vibe. Returns None when verify.py exits 0 with no FAIL line, else what it
    printed. The first version handed Vibe the first folder alone and then reported
    every file of the second as one Vibe did not load."""
    with tempfile.TemporaryDirectory(prefix="vibe-selftest-") as tmp:
        first, second = Path(tmp) / "first", Path(tmp) / "second"
        for folder, name in ((first, "one.toml"), (second, "two.toml")):
            folder.mkdir()
            (folder / name).write_text(VALID, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(VERIFY), str(first), str(second), "--prompts",
             str(prompts), "--house", *extra], capture_output=True, text=True)
        out = proc.stdout + proc.stderr
        OUTPUTS[pool(extra)].append(out)
        if proc.returncode == 0 and not any(
                ln.startswith("FAIL  ") for ln in out.splitlines()):
            return None
        return f"exit {proc.returncode}, wanted 0 and no FAIL line\n{out}"


def recorded_status_holds(prompts: Path) -> str | None:
    """Under Vibe 3 the repo's own profiles do NOT pass, and docs/vibe-3-status.json
    records exactly how. Returns None when a fresh run gives the same findings,
    else what differs. A Vibe release that changes one of them fails here first,
    which is the point: the table in the README is a measurement, and this is
    what notices that it has gone stale.
    """
    import json
    if not STATUS.is_file():
        return f"{STATUS.relative_to(REPO)} is missing"
    recorded = json.loads(STATUS.read_text(encoding="utf-8"))
    proc = subprocess.run(
        [sys.executable, str(VERIFY), str(REPO / ".vibe" / "agents"), "--prompts",
         str(prompts), "--json"], capture_output=True, text=True)
    try:
        fresh = json.loads(proc.stdout)
    except ValueError:
        return f"verify.py --json did not print JSON:\n{proc.stdout[:400]}{proc.stderr[:400]}"
    want = {(f["level"], f["profile"], f["code"]) for f in recorded["findings"]}
    got = {(f["level"], f["profile"], f["code"]) for f in fresh["findings"]}
    if want == got:
        return None
    lines = [f"recorded with Vibe {recorded.get('findings_recorded_with')}, this run is Vibe {fresh['vibe']}"]
    lines += [f"  recorded, not found now: {x}" for x in sorted(want - got)]
    lines += [f"  found now, not recorded: {x}" for x in sorted(got - want)]
    return "\n".join(lines)


def main() -> int:
    failures: list[str] = []
    prompts = REPO / ".vibe" / "prompts"
    global VIBE3
    mode = which_mode()
    vibe3 = VIBE3 = mode == "live-vibe3"
    total = len(CASES) + 1  # the cases, and the repository's own profiles

    # The 2.5.0 rules. Under Vibe 3 they run against their static mirror, because
    # there the live mode asks Vibe 3 and these rules are not its rules.
    legacy = ("--static-only",) if vibe3 else ()
    check_cases(CASES, prompts, failures, *legacy)
    total += 1
    problem = duplicate_stem_fires(prompts, *legacy)
    if problem:
        failures.append(f"a duplicate stem across two folders: {problem}")
        print("  fail  a duplicate stem across two folders")
    else:
        print("  ok    a duplicate stem across two folders")
    total += 1
    problem = two_folders_load(prompts, *legacy)
    if problem:
        failures.append(f"two folders, a valid file in each: {problem}")
        print("  fail  two folders, a valid file in each")
    else:
        print("  ok    two folders, a valid file in each")
    total += 1
    problem = command_line_fails(prompts)
    if problem:
        failures.append(f"a path that is not a directory, and an empty folder: {problem}")
        print("  fail  a path that is not a directory, and an empty folder")
    else:
        print("  ok    a path that is not a directory, and an empty folder")
    code, out = run(REPO / ".vibe" / "agents", prompts, *legacy)
    if code != 0:
        failures.append(f"the repo's own profiles do not pass:\n{out}")
        print("  fail  the repo's own profiles pass clean")
    else:
        print("  ok    the repo's own profiles pass clean"
              + (" (the 2.5.0 rules, static)" if vibe3 else ""))

    if vibe3:
        total += len(V3_CASES) + 4
        check_cases(V3_CASES, prompts, failures)
        problem = string_list_names_no_letters(prompts)
        if problem:
            failures.append(f"Vibe 3: a list written as a string: {problem}")
            print("  fail  Vibe 3: a list written as a string names no letter as a tool")
        else:
            print("  ok    Vibe 3: a list written as a string names no letter as a tool")
        problem = duplicate_stem_fires(prompts)
        if problem:
            failures.append(f"Vibe 3: a duplicate stem across two folders: {problem}")
            print("  fail  Vibe 3: a duplicate stem across two folders")
        else:
            print("  ok    Vibe 3: a duplicate stem across two folders")
        problem = two_folders_load(prompts)
        if problem:
            failures.append(f"Vibe 3: two folders, a valid file in each: {problem}")
            print("  fail  Vibe 3: two folders, a valid file in each")
        else:
            print("  ok    Vibe 3: two folders, a valid file in each")
        difference = recorded_status_holds(prompts)
        if difference:
            failures.append("the repo's own profiles no longer give the recorded Vibe 3 "
                            f"status:\n{difference}")
            print("  fail  the repo's own profiles give the recorded Vibe 3 status")
        else:
            print("  ok    the repo's own profiles give the recorded Vibe 3 status")
    else:
        try:
            from importlib.metadata import version
            major = int(version("mistral-vibe").split(".")[0])
        except Exception:
            major = None
        if major is not None and major >= 3:
            # A Vibe 3 that the checker's Vibe 3 mode cannot ask is not a reason to
            # skip: it means the recorded status was compared with nothing.
            failures.append(f"this interpreter has Vibe {major}.x and verify.py gives mode "
                            f"'{mode}': its Vibe 3 mode did not load, so the Vibe 3 cases "
                            "and the recorded status were not checked")
            print("  fail  the Vibe 3 mode loads under a Vibe 3 interpreter")
        else:
            print(f"  skip  {len(V3_CASES) + 4} Vibe 3 cases: this interpreter gives mode "
                  f"'{mode}', and they need Vibe 3")

    # The reading of verify.py itself: a line it can print with no case and no reason.
    total += 1
    orphans = places_with_no_case(mode)
    if orphans:
        failures.append("places of verify.py that no case here shows and NO_CASE gives no "
                        "reason for, or that the reading cannot read:\n  " + "\n  ".join(orphans))
        print("  fail  the reading of verify.py: each place it can read has a case or a reason")
    else:
        print("  ok    the reading of verify.py: each place it can read has a case or a reason")

    print()
    if failures:
        for f in failures:
            print(f)
        print(f"{len(failures)} of {total} selftest cases failed. "
              "verify.py is not checking what this file says it checks.")
        return 1
    print(f"{total} selftest cases pass. Each one is a profile, or a pair of folders, "
          "that verify.py has to reject, warn about, note or pass; one reads verify.py "
          "for a place with no case; and the repository's own profiles give what is "
          "expected of them: clean under the 2.5.0 rules"
          + (", and the recorded findings under Vibe 3." if vibe3 else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
