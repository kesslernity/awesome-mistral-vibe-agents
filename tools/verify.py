#!/usr/bin/env python3
"""Verify Mistral Vibe agent profiles before Vibe drops them in silence.

Vibe loads an agent profile like this (core/agents/manager.py, _try_load_agent):

    try:
        agent = AgentProfile.from_toml(agent_file)
        agent.apply_to_config(self._config)
        return agent
    except Exception as e:
        logger.warning("Failed to load agent at %s: %s", agent_file, e)
        return None

A warning in a log file you are not reading is the only sign. The agent simply is
not in the list. This script reproduces those two calls and adds the checks for
the failures that do NOT raise: keys that are dropped, keys that are kept and do
nothing, lists that replace defaults instead of extending them, and path patterns
that can never match.

Run it with the interpreter that has Vibe installed:

    ~/.local/share/uv/tools/mistral-vibe/bin/python tools/verify.py

Static-only mode needs nothing but Python 3.11 or newer:

    python3 tools/verify.py --static-only

Exit code 0 means every profile passed. 1 means at least one FAIL.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit(
        "verify.py needs Python 3.11 or newer for tomllib, and this is "
        f"{sys.version_info.major}.{sys.version_info.minor}. Mistral Vibe ships "
        "its own interpreter, which is the one to use here:\n"
        "  ~/.local/share/uv/tools/mistral-vibe/bin/python tools/verify.py"
    )

import tomllib  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DEFAULT_AGENT_DIR = REPO / ".vibe" / "agents"
DEFAULT_PROMPT_DIR = REPO / ".vibe" / "prompts"

STEM_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DASHES = "—–"

# The four keys AgentProfile.from_toml pops. Everything else in the file becomes
# an override and is merged into VibeConfig.
PROFILE_KEYS = {"display_name", "description", "safety", "agent_type"}

BUILTIN_STEMS = {
    "default",
    "plan",
    "accept-edits",
    "auto-approve",
    "explore",
    "lean",
}
BUILTIN_PROMPT_IDS = {"cli", "explore", "tests", "lean"}
PERMISSIONS = {"always", "ask", "never"}
SAFETIES = {"safe", "neutral", "destructive", "yolo"}
AGENT_TYPES = {"agent", "subagent"}

# Tools whose allowlist and denylist entries are matched with fnmatch against a
# RESOLVED ABSOLUTE path. A pattern that cannot start at the filesystem root can
# never match one.
PATH_TOOLS = {"write_file", "search_replace", "read_file", "grep"}

# Vibe picks the bash defaults per platform at import time, and _deep_merge
# replaces a list wholesale rather than extending it. A profile that sets one of
# these lists on macOS silently deletes the Windows entries for a Windows user,
# and the reverse. The union of both platforms is the only portable restatement.
BASH_DEFAULTS = {
    "allowlist": [
        "echo", "git diff", "git log", "git status", "tree", "whoami",
        "cat", "file", "head", "ls", "pwd", "stat", "tail", "uname", "wc", "which",
        "dir", "findstr", "more", "type", "ver", "where",
    ],
    "denylist": [
        "gdb", "pdb", "passwd",
        "nano", "vim", "vi", "emacs", "bash -i", "sh -i", "zsh -i", "fish -i",
        "dash -i", "screen", "tmux",
        "cmd /k", "powershell -NoExit", "pwsh -NoExit", "notepad",
    ],
    "denylist_standalone": [
        "python", "python3", "ipython",
        "bash", "sh", "nohup", "vi", "vim", "emacs", "nano", "su",
        "cmd", "powershell", "pwsh", "notepad",
    ],
}

# Set when live mode is refused for a reason other than "Vibe is not importable",
# so the note at the end names the real cause instead of the generic one.
LIVE_OFF_REASON: str | None = None

# Fallback sets for --static-only, where the installed Vibe cannot be asked.
# Measured against mistral-vibe 2.5.0.
FALLBACK_TOOL_FIELDS = {
    "ask_user_question": {"permission", "allowlist", "denylist"},
    "bash": {"permission", "allowlist", "denylist", "denylist_standalone",
             "max_output_bytes", "default_timeout"},
    "exit_plan_mode": {"permission", "allowlist", "denylist"},
    "grep": {"permission", "allowlist", "denylist", "max_output_bytes",
             "default_max_matches", "default_timeout", "exclude_patterns",
             "codeignore_file"},
    "read_file": {"permission", "allowlist", "denylist", "max_read_bytes"},
    "search_replace": {"permission", "allowlist", "denylist", "max_content_size",
                       "create_backup", "fuzzy_threshold"},
    "task": {"permission", "allowlist", "denylist"},
    "todo": {"permission", "allowlist", "denylist", "max_todos"},
    "web_fetch": {"permission", "allowlist", "denylist", "default_timeout",
                  "max_timeout", "max_content_bytes", "user_agent"},
    "web_search": {"permission", "allowlist", "denylist", "timeout", "model"},
    "write_file": {"permission", "allowlist", "denylist", "max_write_bytes",
                   "create_parent_dirs"},
}
FALLBACK_CONFIG_KEYS = {
    "active_model", "agent_paths", "auto_approve", "auto_compact_threshold",
    "compaction_model", "disabled_agents", "disabled_skills", "disabled_tools",
    "enable_notifications", "enable_telemetry", "enabled_agents", "enabled_skills",
    "enabled_tools", "include_model_info", "include_project_context",
    "include_prompt_detail", "installed_agents", "mcp_servers", "models",
    "providers", "skill_paths", "system_prompt_id", "tool_paths", "tools",
}
FALLBACK_MODEL_ALIASES = {"devstral-2", "devstral-small", "local"}


class Report:
    def __init__(self) -> None:
        self.fails: list[tuple[str, str]] = []
        self.warns: list[tuple[str, str]] = []
        self.checked = 0

    def fail(self, where: str, msg: str) -> None:
        self.fails.append((where, msg))

    def warn(self, where: str, msg: str) -> None:
        self.warns.append((where, msg))


def load_vibe_facts(agent_dir: Path, prompt_dir: Path) -> dict | None:
    """Ask the installed Vibe what exists. Returns None if Vibe is not importable.

    Runs against an isolated VIBE_HOME so the caller's own ~/.vibe/config.toml,
    providers and agents cannot change the verdict. A placeholder MISTRAL_API_KEY
    is set only if the variable is unset: VibeConfig has a model validator that
    raises when the active model's provider has no key. Nothing reads, prints or
    writes a real key.
    """
    tmp_home = Path(tempfile.mkdtemp(prefix="vibe-verify-home-"))
    (tmp_home / "prompts").mkdir(parents=True, exist_ok=True)
    if prompt_dir.is_dir():
        for md in prompt_dir.glob("*.md"):
            shutil.copy2(md, tmp_home / "prompts" / md.name)
    os.environ["VIBE_HOME"] = str(tmp_home)
    os.environ.setdefault("MISTRAL_API_KEY", "verify-placeholder-not-a-key")

    try:
        from vibe.core.config.harness_files import init_harness_files_manager
    except Exception:
        shutil.rmtree(tmp_home, ignore_errors=True)
        return None

    init_harness_files_manager("user")

    from vibe.core.agents.models import BUILTIN_AGENTS, AgentProfile
    # The root config class was renamed between the two releases this script has
    # to run against: VibeConfig in 2.5.0, VibeConfigSchema in 2.25.5. Importing
    # only the old name made live mode die with an ImportError on the current
    # release, which turned the honest measurement into a stack trace for anyone
    # who upgraded. Take whichever the installed package exports.
    try:
        from vibe.core.config import VibeConfigSchema as VibeConfig
    except ImportError:
        from vibe.core.config import VibeConfig
    from vibe.core.paths import DEFAULT_TOOL_DIR
    from vibe.core.tools.manager import ToolManager

    # Live mode reproduces Vibe's own two calls: from_toml, then apply_to_config.
    # 2.25.5 removed apply_to_config, and on that release every profile came back
    # "apply_to_config raises, so Vibe drops it" — thirteen confident FAILs about
    # the profiles, caused entirely by this script reaching for an API that no
    # longer exists. A checker that reports the world broken because IT is stale
    # is worse than one that crashes: a crash is obviously the checker's fault,
    # a red run reads as the repo's. So detect the mismatch and say so.
    if not hasattr(AgentProfile, "apply_to_config"):
        global LIVE_OFF_REASON
        LIVE_OFF_REASON = (
            "the installed Vibe has no AgentProfile.apply_to_config, so it is not the\n"
            "      2.5.0 line these profiles are verified against. Live mode is OFF and\n"
            "      the static checks below still hold. Re-verifying this repo against a\n"
            "      newer Vibe is a deliberate job, not a side effect of this script."
        )
        shutil.rmtree(tmp_home, ignore_errors=True)
        return None

    tool_fields: dict[str, set[str]] = {}
    try:
        for cls in ToolManager._iter_tool_classes([DEFAULT_TOOL_DIR.path]):
            tool_fields[cls.get_name()] = set(cls._get_tool_config_class().model_fields)
    except Exception:
        tool_fields = {}

    base = VibeConfig.model_validate({"agent_paths": [str(agent_dir)]})

    return {
        "tmp_home": tmp_home,
        "AgentProfile": AgentProfile,
        "builtins": set(BUILTIN_AGENTS),
        "config_keys": set(VibeConfig.model_fields),
        "tool_fields": tool_fields,
        # `models` changed SHAPE as well as the class name: a list of
        # ModelConfig carrying .alias in 2.5.0, a dict keyed BY the alias in
        # 2.25.5. Reading .alias off the dict gave 'str' object has no
        # attribute 'alias', which is the second way live mode died on the
        # current release. Take the aliases out of whichever shape is there.
        "model_aliases": (set(base.models) if isinstance(base.models, dict)
                          else {m.alias for m in base.models}),
        "base": base,
        "VibeConfig": VibeConfig,
    }


def check_path_pattern(pattern: str) -> str | None:
    """Return a reason if this pattern can never match a resolved absolute path."""
    if pattern.startswith("~"):
        return (
            "starts with '~', which Vibe does not expand for a tool pattern, "
            "so fnmatch compares it to an absolute path and never matches"
        )
    if pattern.startswith(("/", "*")):
        return None
    if re.match(r"^[A-Za-z]:[\\/]", pattern):
        return None
    return (
        "is relative, and Vibe runs fnmatch against the RESOLVED ABSOLUTE path, "
        "so it never matches. Write '*/" + pattern.lstrip("./") + "' instead"
    )


def verify_file(path: Path, facts: dict | None, rep: Report, *, house: bool,
                prompt_dir: Path, seen_stems: dict[str, Path]) -> None:
    where = path.name
    rep.checked += 1

    raw = path.read_bytes()
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except Exception as e:
        rep.fail(where, f"is not valid TOML, so Vibe drops it: {e}")
        return

    stem = path.stem

    if not STEM_RE.match(stem):
        rep.fail(where, f"filename stem '{stem}' is not lower-case-kebab, "
                        "and the stem IS the agent name a user types")
    if stem in BUILTIN_STEMS or (facts and stem in facts["builtins"]):
        rep.fail(where, f"stem '{stem}' silently OVERRIDES the built-in agent of "
                        "the same name. Vibe logs this at info level and carries on")
    if stem in seen_stems:
        rep.fail(where, f"duplicate stem, already seen at {seen_stems[stem]}. "
                        "Across search paths the FIRST one wins and the rest are "
                        "skipped at debug level")
    seen_stems[stem] = path

    if "name" in data:
        rep.fail(where, "has a 'name' key. from_toml sets name from the filename "
                        "and never reads this key, so it is silently ignored")
    if "install_required" in data:
        rep.fail(where, "has 'install_required'. It is not a profile key, so it "
                        "lands in the config overrides, stays False, and does nothing")

    safety = data.get("safety")
    if safety is not None and safety not in SAFETIES:
        rep.fail(where, f"safety '{safety}' is not one of {sorted(SAFETIES)}; "
                        "AgentSafety raises and the profile is DROPPED")
    atype = data.get("agent_type")
    if atype is not None and atype not in AGENT_TYPES:
        rep.fail(where, f"agent_type '{atype}' is not one of {sorted(AGENT_TYPES)}; "
                        "AgentType raises and the profile is DROPPED")

    config_keys = facts["config_keys"] if facts else FALLBACK_CONFIG_KEYS
    for key in data:
        if key in PROFILE_KEYS or key in {"name", "install_required"}:
            continue
        if key not in config_keys:
            rep.fail(where, f"top-level key '{key}' is not a VibeConfig field. "
                            "VibeConfig ignores extra keys, so it loads and does nothing")

    tool_fields = facts["tool_fields"] if facts and facts["tool_fields"] else FALLBACK_TOOL_FIELDS
    known_tools = set(tool_fields)

    tools = data.get("tools") or {}
    if not isinstance(tools, dict):
        rep.fail(where, "'tools' is not a table")
        tools = {}

    for tname, tconf in tools.items():
        tw = f"{where} [tools.{tname}]"
        if tname not in known_tools:
            rep.fail(tw, f"'{tname}' is not a tool Vibe discovers. The section "
                         f"loads and does nothing. Known: {', '.join(sorted(known_tools))}")
            continue
        if not isinstance(tconf, dict):
            rep.fail(tw, "is not a table")
            continue
        for k, v in tconf.items():
            if k not in tool_fields[tname]:
                rep.fail(tw, f"key '{k}' is not a field of this tool's config. "
                             "BaseToolConfig allows extra keys, so it is KEPT in "
                             "model_extra and has no effect at all")
            if k == "permission" and v not in PERMISSIONS:
                rep.fail(tw, f"permission '{v}' is not one of {sorted(PERMISSIONS)}; "
                             "validation fails and the whole profile is DROPPED")
        if tname in PATH_TOOLS:
            for listkey in ("allowlist", "denylist"):
                for pat in tconf.get(listkey) or []:
                    if not isinstance(pat, str):
                        rep.fail(tw, f"{listkey} entry {pat!r} is not a string")
                        continue
                    if (reason := check_path_pattern(pat)) is not None:
                        rep.fail(tw, f"{listkey} pattern '{pat}' {reason}")
        if tname == "bash":
            # With permission = "never" the allowlist is the entire permitted
            # surface, so restating Vibe's defaults would WIDEN the profile
            # rather than protect it. The denylists are different: dropping an
            # entry there removes a guard, on every platform it came from.
            deny_only = tconf.get("permission") == "never"
            for listkey, defaults in BASH_DEFAULTS.items():
                if listkey not in tconf:
                    continue
                if deny_only and listkey == "allowlist":
                    continue
                given = set(tconf[listkey] or [])
                missing = [d for d in defaults if d not in given]
                if missing:
                    rep.warn(tw, f"{listkey} REPLACES Vibe's default list. These "
                                 f"defaults are dropped: {', '.join(missing)}")
        if tname == "task":
            allow = tconf.get("allowlist")
            if allow is not None and "explore" not in allow:
                rep.warn(tw, "allowlist replaces the default ['explore'], so the "
                             "built-in explore subagent now prompts every time")
        if tname == "grep" and "exclude_patterns" in tconf:
            rep.warn(tw, "exclude_patterns replaces Vibe's 23 default excludes "
                         "rather than adding to them")

    for listkey in ("enabled_tools", "disabled_tools"):
        for entry in data.get(listkey) or []:
            if not isinstance(entry, str):
                rep.fail(where, f"{listkey} entry {entry!r} is not a string")
                continue
            if entry.startswith("re:") or any(c in entry for c in "*?["):
                if not any(fnmatch.fnmatch(t, entry) for t in known_tools) and not entry.startswith("re:"):
                    rep.fail(where, f"{listkey} pattern '{entry}' matches no known tool")
                continue
            if entry not in known_tools:
                rep.fail(where, f"{listkey} names '{entry}', which is not a tool. "
                                "An enabled_tools list that matches nothing leaves "
                                "the agent with ZERO tools, and nothing is logged")

    aliases = facts["model_aliases"] if facts else FALLBACK_MODEL_ALIASES
    for key in ("active_model", "compaction_model"):
        val = data.get(key)
        if isinstance(val, str) and val not in aliases:
            rep.fail(where, f"{key} '{val}' is not a model alias in the merged "
                            f"config ({', '.join(sorted(aliases))}). The profile "
                            "LOADS and crashes later, when something asks for the "
                            "active model")
    if isinstance(data.get("models"), list):
        rep.warn(where, "sets 'models', and a list REPLACES rather than merges. "
                        "Every default alias not restated here is gone")
    if isinstance(data.get("providers"), list):
        rep.warn(where, "sets 'providers', and a list REPLACES rather than merges")

    spid = data.get("system_prompt_id")
    if isinstance(spid, str) and spid not in BUILTIN_PROMPT_IDS:
        candidate = prompt_dir / f"{spid}.md"
        if not candidate.is_file():
            rep.fail(where, f"system_prompt_id '{spid}' is not built in "
                            f"({', '.join(sorted(BUILTIN_PROMPT_IDS))}) and "
                            f"{candidate.relative_to(REPO) if candidate.is_relative_to(REPO) else candidate}"
                            " does not exist. _check_system_prompt runs at load, "
                            "so the profile is DROPPED")

    if house:
        if not str(data.get("description", "")).strip():
            rep.fail(where, "has no description. It is the only text a user has to "
                            "choose the agent by")
        if not str(data.get("display_name", "")).strip():
            rep.fail(where, "has no display_name")
        text = raw.decode("utf-8", errors="ignore")
        for ch in DASHES:
            if ch in text:
                rep.fail(where, f"contains {'em' if ch == DASHES[0] else 'en'} dash")

    if facts:
        try:
            profile = facts["AgentProfile"].from_toml(path)
        except Exception as e:
            rep.fail(where, f"AgentProfile.from_toml raises, so Vibe drops it: "
                            f"{type(e).__name__}: {e}")
            return
        try:
            profile.apply_to_config(facts["base"])
        except Exception as e:
            rep.fail(where, f"apply_to_config raises, so Vibe drops it: "
                            f"{type(e).__name__}: {e}")


def live_discovery(agent_dir: Path, facts: dict, expected: set[str],
                   rep: Report) -> None:
    """Instantiate the real AgentManager and confirm what it actually sees."""
    from vibe.core.agents.manager import AgentManager
    from vibe.core.agents.models import AgentType

    cfg = facts["base"]
    mgr = AgentManager(lambda: cfg)
    available = set(mgr.available_agents)

    missing = sorted(expected - available)
    if missing:
        rep.fail("live", f"AgentManager did not load: {', '.join(missing)}")

    overridden = sorted(facts["builtins"] & expected)
    if overridden:
        rep.fail("live", f"these profiles override built-ins: {', '.join(overridden)}")

    subs = sorted(a.name for a in mgr.get_subagents() if a.name in expected)
    primaries = sorted(n for n in expected if n not in subs)
    print(f"  live   AgentManager sees {len(available)} agents in total")
    print(f"  live   from this repo: {len(expected - facts['builtins'])} loaded, "
          f"{len(primaries)} primary, {len(subs)} subagent")
    print(f"  live   subagents: {', '.join(subs) if subs else 'none'}")
    if subs:
        print("  note   a custom subagent is not pre-approved: tools.task.allowlist "
              "defaults to ['explore'], so the others ASK")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="*", type=Path, default=None,
                    help="directories of agent .toml files (default: .vibe/agents)")
    ap.add_argument("--prompts", type=Path, default=DEFAULT_PROMPT_DIR,
                    help="directory of custom system prompts (default: .vibe/prompts)")
    ap.add_argument("--static-only", action="store_true",
                    help="skip every check that needs Vibe installed")
    ap.add_argument("--house", action="store_true",
                    help="also apply this repo's own style rules")
    args = ap.parse_args()

    dirs = args.dirs or [DEFAULT_AGENT_DIR]
    files: list[Path] = []
    for d in dirs:
        if not d.is_dir():
            print(f"FAIL  {d} is not a directory")
            return 1
        files.extend(sorted(d.glob("*.toml")))
    if not files:
        print(f"FAIL  no .toml files in {', '.join(str(d) for d in dirs)}")
        return 1

    facts = None
    if not args.static_only:
        facts = load_vibe_facts(dirs[0], args.prompts)
        if facts is None:
            if LIVE_OFF_REASON:
                print(f"note  {LIVE_OFF_REASON}")
            else:
                print("note  Vibe is not importable here, running static checks only.")
                print("      For the full set, use the interpreter Vibe is installed in:")
                print("      ~/.local/share/uv/tools/mistral-vibe/bin/python tools/verify.py")

    rep = Report()
    seen: dict[str, Path] = {}
    for f in files:
        verify_file(f, facts, rep, house=args.house, prompt_dir=args.prompts,
                    seen_stems=seen)

    if facts and not rep.fails:
        live_discovery(dirs[0], facts, set(seen), rep)

    print()
    for where, msg in rep.warns:
        print(f"WARN  {where}: {msg}")
    for where, msg in rep.fails:
        print(f"FAIL  {where}: {msg}")

    mode = "static" if facts is None else "static + live"
    print()
    print(f"{rep.checked} profiles checked ({mode}), "
          f"{len(rep.fails)} FAIL, {len(rep.warns)} WARN")
    if facts:
        shutil.rmtree(facts["tmp_home"], ignore_errors=True)
    if rep.fails:
        print("A FAIL means Vibe would drop the profile, or load it and ignore the "
              "part you wrote it for.")
        return 1
    if facts is None:
        print("Every profile passes the static rules. Nothing here proves the "
              "installed Vibe loads them: run this again under the interpreter "
              "Vibe lives in for that.")
    else:
        print("Every profile loads in the installed Vibe, and every key in it "
              "does something.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
