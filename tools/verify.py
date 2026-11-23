#!/usr/bin/env python3
"""Verify Mistral Vibe agent profiles, the way the installed Vibe would treat them.

It runs in one of three modes and says which. `--mode` prints it and exits.

  live-2.5.0   under an interpreter that has Vibe CLI 2.5.0, the release these
               profiles are written for: Vibe's own two loader calls, plus this
               script's rules for the failures that do not raise.
  live-vibe3   under an interpreter that has Vibe 3: what Vibe's own registry
               recorded about each file, plus this script's checks for what it
               does not record. On this repository it exits 1: see README, On
               Vibe 3.
  static       anywhere else, and with --static-only: a mirror of the 2.5.0 rules
               that needs nothing but Python 3.11.

Why 2.5.0 needs a checker at all: it loads an agent profile like this
(core/agents/manager.py, _try_load_agent):

    try:
        agent = AgentProfile.from_toml(agent_file)
        agent.apply_to_config(self._config)
        return agent
    except Exception as e:
        logger.warning("Failed to load agent at %s: %s", agent_file, e)
        return None

A warning in a log file you are not reading is the only sign. The agent simply is
not in the list. Mistral's release notes say that since 2.25.8 an agent file the
harness cannot honor is reported instead of disappearing silently. This script
reproduces those two calls and adds the checks for the failures that do NOT
raise: keys that are dropped, keys that are kept and do nothing, lists that
replace defaults instead of extending them, and path patterns that can never
match.

Run it with an interpreter that has the Vibe you want an answer about. The path
below is where `uv tool install mistral-vibe` keeps its interpreter on macOS and
Linux, whatever the release it installed. The README's section Check before you
ship has the two lines that make a 2.5.0 interpreter beside a newer one.

    ~/.local/share/uv/tools/mistral-vibe/bin/python tools/verify.py

Static-only mode needs nothing but Python 3.11 or newer:

    python3 tools/verify.py --static-only

Exit code 0 means no FAIL in the mode that ran. 1 means at least one FAIL.
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
        f"{sys.version_info.major}.{sys.version_info.minor}. Use an interpreter that "
        "has Vibe CLI 2.5.0, the release these profiles are written for (it needs\n"
        "Python 3.12): the README's section Check before you ship has the two lines "
        "that make one."
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

# What a tool's table can lose in Vibe CLI 2.5.0 when it sets a key and does not restate
# these three. It depends on the config.toml Vibe reads: the user's, or a trusted
# project's own, which 2.5.0 reads instead. The `vibe` command writes every tool's table
# into the user's file at first run (cli/cli.py, bootstrap_config_files), and a profile's
# table merges into that one key by key, so nothing is lost. Where the file Vibe reads
# does not write a value out (no table for the tool, or a table that leaves it out, or no
# file at all, which is how this script runs), ToolManager.get_tool_config merges the
# tool's own defaults with a dump of the merged table, and that table is a BaseToolConfig:
# its dump carries the BASE defaults (permission "ask", empty allowlist, empty denylist)
# for every field nobody wrote, and they overwrite the tool's. Only non-base defaults are
# listed.
FALLBACK_TOOL_DEFAULTS = {
    "ask_user_question": {"permission": "always"},
    "bash": {"permission": "ask", "allowlist": BASH_DEFAULTS["allowlist"],
             "denylist": BASH_DEFAULTS["denylist"]},
    "exit_plan_mode": {"permission": "always"},
    "grep": {"permission": "always"},
    "read_file": {"permission": "always"},
    "task": {"permission": "ask", "allowlist": ["explore"]},
    "todo": {"permission": "always"},
}


class Report:
    def __init__(self) -> None:
        self.fails: list[tuple[str, str]] = []
        self.warns: list[tuple[str, str]] = []
        self.notes: list[str] = []
        # (level, profile, code) for the findings Vibe 3 mode makes. A code is what
        # docs/vibe-3-status.json records and what selftest.py compares, so a
        # reworded message cannot make a recorded finding look new or gone.
        self.codes: list[tuple[str, str, str]] = []
        self.checked = 0

    def fail(self, where: str, msg: str, code: str | None = None) -> None:
        self.fails.append((where, msg))
        if code:
            self.codes.append(("FAIL", where.split(" ")[0].removesuffix(".toml"), code))

    def warn(self, where: str, msg: str, code: str | None = None) -> None:
        self.warns.append((where, msg))
        if code:
            self.codes.append(("WARN", where.split(" ")[0].removesuffix(".toml"), code))


def load_vibe_facts(agent_dirs: list[Path], prompt_dir: Path) -> dict | None:
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

    global LIVE_OFF_REASON
    try:
        from vibe.core.config.harness_files import init_harness_files_manager
        from vibe.core.tools.manager import ToolManager
    except Exception as e:
        # Installed and not importable is a different thing from not installed. Vibe
        # 2.5.0 asks for `mcp>=1.14.0` with no upper bound, and installed with newer
        # dependencies than it was released with it stops at an ImportError.
        try:
            from importlib.metadata import version
            installed = version("mistral-vibe")
        except Exception:
            installed = None
        if installed:
            LIVE_OFF_REASON = (
                f"mistral-vibe {installed} is installed here and does not import\n"
                f"      ({type(e).__name__}: {str(e).splitlines()[0][:150]}).\n"
                "      Live mode is OFF and the static checks below still hold. A 2.5.0\n"
                "      installed with no date limit stopped this way on 23 November 2026,\n"
                "      on a dependency that had moved on: the README's section Check before\n"
                "      you ship has the install that works."
            )
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

    # Live mode reproduces Vibe's own two calls: from_toml, then apply_to_config.
    # 2.25.5 removed apply_to_config, and on that release every profile came back
    # "apply_to_config raises, so Vibe drops it": thirteen confident FAILs about
    # the profiles, caused entirely by this script reaching for an API that no
    # longer exists. A checker that reports the world broken because IT is stale
    # is worse than one that crashes: a crash is obviously the checker's fault,
    # a red run reads as the repo's. So detect the mismatch and say so.
    if not hasattr(AgentProfile, "apply_to_config"):
        LIVE_OFF_REASON = (
            "the installed Vibe has no AgentProfile.apply_to_config, so it is not the\n"
            "      2.5.0 line these profiles are verified against. Live mode is OFF and\n"
            "      the static checks below still hold. Re-verifying this repo against a\n"
            "      newer Vibe is a deliberate job, not a side effect of this script."
        )
        shutil.rmtree(tmp_home, ignore_errors=True)
        return None

    tool_fields: dict[str, set[str]] = {}
    tool_defaults: dict[str, dict] = {}
    try:
        for cls in ToolManager._iter_tool_classes([DEFAULT_TOOL_DIR.path]):
            config_class = cls._get_tool_config_class()
            tool_fields[cls.get_name()] = set(config_class.model_fields)
            default = config_class()
            tool_defaults[cls.get_name()] = {
                "permission": getattr(default.permission, "value", str(default.permission)),
                "allowlist": list(default.allowlist),
                "denylist": list(default.denylist),
            }
    except Exception:
        tool_fields = {}
        tool_defaults = {}

    # Every folder given on the command line, not the first alone: a profile in a
    # second folder is one Vibe was never shown otherwise.
    base = VibeConfig.model_validate({"agent_paths": [str(d) for d in agent_dirs]})

    return {
        "tmp_home": tmp_home,
        "AgentProfile": AgentProfile,
        "builtins": set(BUILTIN_AGENTS),
        "config_keys": set(VibeConfig.model_fields),
        "tool_fields": tool_fields,
        "tool_defaults": tool_defaults,
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


def vibe_major() -> int | None:
    """The major version of the Vibe this interpreter has, or None without one."""
    try:
        from importlib.metadata import version
        return int(version("mistral-vibe").split(".")[0])
    except Exception:
        return None


def load_vibe3_facts(agent_dirs: list[Path], prompt_dir: Path) -> dict | None:
    """Ask an installed Vibe 3 what it does with these folders of agent files.

    Vibe 3 no longer drops a profile in silence. Its own registry records which
    files it cannot use and which settings of a file it ignores, so this mode
    re-implements none of that: it builds Vibe's configuration in an isolated
    VIBE_HOME and HOME, hands the folders to Vibe's AgentManager, and reads what
    Vibe recorded. Nothing is sent anywhere and no session is started. The model
    list it sees is the one built into Vibe: no catalogue is fetched.

    Returns None, with LIVE_OFF_REASON set, when the installed Vibe 3 does not
    have the objects this was written against (3.1.4).
    """
    global LIVE_OFF_REASON
    import asyncio

    tmp_home = Path(tempfile.mkdtemp(prefix="vibe-verify-home-"))
    (tmp_home / "prompts").mkdir(parents=True, exist_ok=True)
    if prompt_dir.is_dir():
        for md in prompt_dir.glob("*.md"):
            shutil.copy2(md, tmp_home / "prompts" / md.name)
    os.environ["VIBE_HOME"] = str(tmp_home)
    # Vibe 3 also reads ~/.agents and other folders of the real home.
    os.environ["HOME"] = str(tmp_home)
    os.environ.setdefault("MISTRAL_API_KEY", "verify-placeholder-not-a-key")

    try:
        from importlib.metadata import version

        from vibe.core.agents.manager import AgentManager
        from vibe.core.agents.models import (
            BUILTIN_AGENTS,
            BUILTIN_APPROVAL_POLICIES,
            RESERVED_AGENT_NAME,
            AgentProfile,
        )
        from vibe.core.config.default_orchestrator import build_default_orchestrator
        from vibe.core.config.harness_files import init_harness_files_manager
        from vibe.core.tools.manager import ToolManager

        init_harness_files_manager("user")
        try:
            # Vibe prints a warning for each file it cannot use while it loads them.
            # Each one comes back below as a FAIL in Vibe's own words.
            import logging
            from vibe.observability.logging import logger as vibe_logger
            vibe_logger.setLevel(logging.ERROR)
        except Exception:
            pass
        orch = asyncio.run(build_default_orchestrator(
            {"agent_paths": [str(d) for d in agent_dirs]}))
        mgr = AgentManager(orch, None)
        config = mgr.config
        tool_manager = ToolManager(lambda: config)
        catalogue = set(tool_manager.available_tools)
        issues: dict[str, list[tuple[str, str]]] = {}
        for issue in mgr.agent_file_issues:
            issues.setdefault(issue.name, []).append((issue.key or issue.code, issue.message))
        failures = {f.name: f.reason for f in mgr.load_failures}
        discovered = dict(mgr._discovered)
        aliases = set(config.models) if isinstance(config.models, dict) else {m.alias for m in config.models}
    except Exception as e:
        LIVE_OFF_REASON = (
            f"this interpreter has Vibe {vibe_major()}.x, and it does not answer the way\n"
            f"      3.1.4 does ({type(e).__name__}: {str(e)[:160]}).\n"
            "      Live mode is OFF and the static rules below are the 2.5.0 ones."
        )
        shutil.rmtree(tmp_home, ignore_errors=True)
        return None

    # Vibe's own tables of names it keeps for old config files and runs no tool for.
    retired: dict[str, str] = {}
    try:
        from vibe.core.config._setting_keys import RETIRED_TOOL_NAMES
        retired = dict(RETIRED_TOOL_NAMES)
    except Exception:
        pass

    # What a subagent's file leaves it, tool by tool, as the session computes it.
    def subagent_ceiling(overrides: dict) -> dict[str, str] | None:
        try:
            from vibe.app_server._runtime import rust_agent_tool_ceiling
            return dict(rust_agent_tool_ceiling(
                set(catalogue),
                lambda name: tool_manager.get_tool_config(name).permission,
                overrides,
            ))
        except Exception:
            return None

    engine_sources: dict[str, set[str]] = {}
    try:
        from vibe.app_server._unified_permissions import RUST_BUILTIN_TOOL_SOURCES
        engine_sources = {k: set(v) for k, v in RUST_BUILTIN_TOOL_SOURCES.items()}
    except Exception:
        pass

    return {
        "tmp_home": tmp_home,
        "version": version("mistral-vibe"),
        "AgentProfile": AgentProfile,
        "builtins": set(BUILTIN_AGENTS),
        "policies": set(BUILTIN_APPROVAL_POLICIES),
        "reserved": RESERVED_AGENT_NAME,
        "issues": issues,
        "failures": failures,
        "discovered": discovered,
        "catalogue": catalogue,
        "retired": retired,
        "aliases": aliases,
        "subagent_ceiling": subagent_ceiling,
        "engine_sources": engine_sources,
        "default_policy": getattr(config, "default_approval_policy", None),
    }


def verify_file_v3(path: Path, facts: dict, rep: Report, *, house: bool,
                   seen_stems: dict[str, Path]) -> None:
    """One profile, as the installed Vibe 3 sees it. Checks 1 and 2 print what
    Vibe's registry recorded, with Vibe's own sentence, except `safety`, which
    main() reports once as a note. The lines about the filename and checks 3 to 5
    are this script's, for what the registry does not record about an agent file."""
    where = path.name
    ver = facts["version"]
    rep.checked += 1

    raw = path.read_bytes()
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except Exception as e:
        rep.fail(where, f"is not valid TOML: {e}", "invalid_toml")
        return

    stem = path.stem
    if not STEM_RE.match(stem):
        rep.fail(where, f"filename stem '{stem}' is not lower-case-kebab, "
                        "and the stem IS the agent name a user types", "stem")
    if stem.casefold() == facts["reserved"]:
        # Vibe 3.1.4 records this one itself, and check 1 prints its words. This line
        # is for a Vibe 3 that does not.
        if stem not in facts["failures"]:
            rep.fail(where, f"stem '{stem}' is reserved for hook matching: Vibe {ver} "
                            "refuses the file", "reserved_stem")
    elif stem in facts["policies"]:
        rep.fail(where, f"stem '{stem}' is the name of an approval policy, so Vibe {ver} "
                        "does not load this file as an agent. In your own agents folder it "
                        "replaces that policy; in a project's folder Vibe ignores it",
                 "policy_stem")
    elif stem in facts["builtins"]:
        if stem in facts["failures"]:
            rep.fail(where, f"stem '{stem}' is the name of a built-in agent. Vibe {ver} "
                            "cannot use this file (next line) and keeps the built-in",
                     "builtin_stem")
        else:
            rep.fail(where, f"stem '{stem}' OVERRIDES the built-in agent of the same name: "
                            f"Vibe {ver} uses this file in its place", "builtin_stem")
    if stem in seen_stems:
        rep.fail(where, f"duplicate stem, already seen at {seen_stems[stem]}. The "
                        "first one wins", "duplicate_stem")
    seen_stems[stem] = path

    if house:
        if not str(data.get("description", "")).strip():
            rep.fail(where, "has no description. It is the text that tells a reader "
                            "what the agent is for")
        if not str(data.get("display_name", "")).strip():
            rep.fail(where, "has no display_name")
        text = raw.decode("utf-8", errors="ignore")
        if DASHES[0] in text:
            rep.fail(where, "contains em dash")
        if DASHES[1] in text:
            rep.fail(where, "contains en dash")

    # 1. Vibe cannot use the file at all. Its own words.
    if stem in facts["failures"]:
        rep.fail(where, f"Vibe {ver} cannot use this profile, and says: "
                        f"{facts['failures'][stem]}", "cannot_load")
    elif (stem not in facts["discovered"] and stem not in facts["policies"]
          and stem.casefold() != facts["reserved"]):
        rep.fail(where, f"Vibe {ver} did not find this profile and recorded no reason",
                 "not_discovered")

    # 2. Settings Vibe drops. Its own list. `safety` is counted once for the whole
    #    folder in main(): it is dropped from every primary agent and gates nothing.
    for key, message in facts["issues"].get(stem, []):
        if key == "safety":
            continue
        rep.fail(where, f"Vibe {ver} ignores '{key}', so the part of this profile "
                        f"written with it does nothing there. Vibe says: {message}",
                 f"ignored:{key}")

    is_subagent = data.get("agent_type") == "subagent"
    catalogue, retired = facts["catalogue"], facts["retired"]

    # 3. Tool names. Vibe 3 says nothing about a name it has no tool for when the
    #    name is in an AGENT file, so these two checks are this script's.
    def name_check(name: str, where_in_file: str, place: str) -> None:
        if not isinstance(name, str) or any(c in name for c in "*?[") or name.startswith("re:"):
            return
        if name in retired:
            rep.fail(where, f"{where_in_file} names '{name}', a former tool name. Vibe "
                            f"{ver} has no tool for it, so naming it matches nothing. "
                            f"Vibe's own note on the name: \"{retired[name]}\"",
                     f"retired_tool:{name}@{place}")
        elif name not in catalogue:
            rep.fail(where, f"{where_in_file} names '{name}'. Vibe {ver} has no tool of "
                            "that name, so naming it matches nothing, and Vibe says "
                            "nothing about it in an agent file",
                     f"no_such_tool:{name}@{place}")

    for listkey in ("enabled_tools", "disabled_tools"):
        entries = data.get(listkey)
        # A value that is not a list is Vibe's to report: check 1 prints its words.
        # Walking a string would name its letters as tools.
        for entry in entries if isinstance(entries, list) else []:
            name_check(entry, listkey, listkey)
    tools = data.get("tools") if isinstance(data.get("tools"), dict) else {}
    for tname in tools:
        name_check(tname, f"[tools.{tname}]", "tools")

    # 3b. Skills are opened with the `skill` tool. A profile that filters skills and
    #     whose tool list leaves that tool out keeps skills it cannot open.
    enabled = data.get("enabled_tools")
    if (not is_subagent and isinstance(enabled, list) and enabled
            and data.get("enabled_skills") and "skill" in catalogue):
        def matches(pattern: object) -> bool:
            if not isinstance(pattern, str):
                return False
            if pattern.startswith("re:"):
                return re.fullmatch(pattern[3:], "skill", re.IGNORECASE) is not None
            return fnmatch.fnmatch("skill", pattern.lower())
        if not any(matches(pat) for pat in enabled):
            rep.fail(where, f"enabled_skills is set, and enabled_tools leaves out 'skill'. "
                            f"Vibe {ver} opens a skill with the skill tool, so this "
                            "profile can open none of the skills it keeps",
                     "skills_unreachable")

    # 4. A model alias the configuration does not have. Vibe 3 does not stop: it
    #    runs its default model and prints one notice.
    alias = data.get("active_model")
    if isinstance(alias, str) and alias and alias not in facts["aliases"]:
        rep.fail(where, f"active_model '{alias}' is not in the model list built into "
                        f"Vibe {ver} ({', '.join(sorted(facts['aliases']))}), which is "
                        "the list this check reads: it fetches no catalogue. Where the "
                        "model is not in the list, Vibe does not stop: it runs its "
                        "default model and prints one notice. Define the model in your "
                        "own config.toml for the profile to run on it",
                 f"model_missing:{alias}")

    # 5. A subagent's tools, as the session computes them. `permission = "never"`
    #    is a ceiling for a subagent, and an allowlist is no exception to it.
    if is_subagent and stem in facts["discovered"] and stem not in facts["failures"]:
        overrides = facts["discovered"][stem].overrides
        ceiling = facts["subagent_ceiling"](overrides)
        if ceiling is None:
            rep.notes.append(f"could not ask Vibe {ver} what '{stem}' leaves its "
                             "subagent session: the tool checks for it were skipped")
        else:
            wanted = {t for t in (data.get("enabled_tools") or []) if isinstance(t, str)}
            for builtin, sources in sorted(facts["engine_sources"].items()):
                if builtin.startswith("process."):
                    continue
                asked_for = sorted(sources & wanted)
                if asked_for and ceiling.get(builtin) == "deny":
                    table = tools.get(asked_for[0]) if isinstance(tools.get(asked_for[0]), dict) else {}
                    tool = asked_for[0]
                    code = f"subagent_denied:{tool}"
                    if table.get("permission") == "never":
                        rep.fail(where, f"Vibe {ver} refuses every call this subagent makes "
                                        f"to '{tool}': its table sets permission = \"never\", "
                                        "which is a ceiling for a subagent, and the allowlist "
                                        "is no exception to it", code)
                    elif tool in (data.get("disabled_tools") or []):
                        rep.fail(where, f"Vibe {ver} refuses every call this subagent makes "
                                        f"to '{tool}': its file names it in enabled_tools and "
                                        "in disabled_tools as well", code)
                    else:
                        rep.fail(where, f"Vibe {ver} refuses every call this subagent makes "
                                        f"to '{tool}', although its file lists it in "
                                        "enabled_tools", code)


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
    tool_defaults = (facts["tool_defaults"] if facts and facts["tool_defaults"]
                     else FALLBACK_TOOL_DEFAULTS)
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
            rep.fail(tw, "is not a table of settings")
            continue
        for k, v in tconf.items():
            if k not in tool_fields[tname]:
                rep.fail(tw, f"key '{k}' is not a field of this tool's config. "
                             "BaseToolConfig allows extra keys, so it is KEPT in "
                             "model_extra and has no effect at all")
            if k == "permission" and v not in PERMISSIONS:
                rep.fail(tw, f"permission '{v}' is not one of {sorted(PERMISSIONS)}; "
                             "validation fails and the whole profile is DROPPED")
        # A table that sets one key and leaves the rest to the defaults depends on the
        # config.toml Vibe reads. Measured on 2.5.0 where that file does not write the
        # value out (no [tools.bash] table, or one that holds only default_timeout): a
        # profile that sets only default_timeout ends up with an empty allowlist and an
        # empty denylist, and one that sets only max_read_bytes in [tools.read_file]
        # turns "always" into "ask". With the first-run config.toml in place both keep
        # their defaults. With permission = "never" the lists are not a loss: nothing
        # runs but what begins with an allowlist entry.
        if tconf:
            defaults = tool_defaults.get(tname) or {}
            default_permission = defaults.get("permission", "ask")
            depends = ("In Vibe CLI 2.5.0 the value then comes from the config.toml Vibe "
                       "reads, if that file writes it out for this tool, as the one the "
                       "`vibe` command writes at first run does. Where it does not")
            # A note, not a WARN: leaving a list to the config.toml Vibe reads is a
            # choice. Restating it would replace whatever the user put in their own list.
            if "permission" not in tconf and default_permission != "ask":
                rep.notes.append(f"{tw}: sets a key without restating 'permission'. "
                                 f"{depends}, permission falls from "
                                 f"'{default_permission}' to 'ask'")
            if tconf.get("permission") != "never":
                for listkey in ("allowlist", "denylist"):
                    dropped = defaults.get(listkey) or []
                    if listkey not in tconf and dropped:
                        rep.notes.append(f"{tw}: sets a key without restating '{listkey}'. "
                                         f"{depends}, the {listkey} is EMPTY and not Vibe's "
                                         f"default. Dropped: {', '.join(dropped)}")
        if tname in PATH_TOOLS:
            for listkey in ("allowlist", "denylist"):
                for pat in tconf.get(listkey) or []:
                    if not isinstance(pat, str):
                        rep.fail(tw, f"{listkey} entry {pat!r} is not a string")
                        continue
                    if (reason := check_path_pattern(pat)) is not None:
                        rep.fail(tw, f"{listkey} pattern '{pat}' cannot match: it {reason}")
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
        entries = data.get(listkey)
        if entries is not None and not isinstance(entries, list):
            rep.fail(where, f"{listkey} is not a list, so Vibe drops the profile when it "
                            "loads")
            continue
        for entry in entries or []:
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
            rep.fail(where, "has no description. Vibe CLI 2.5.0 gives it to the model "
                            "for a subagent and to an editor connected over ACP for a "
                            "primary agent, and it is what a reader chooses by")
        if not str(data.get("display_name", "")).strip():
            rep.fail(where, "has no display_name")
        text = raw.decode("utf-8", errors="ignore")
        if DASHES[0] in text:
            rep.fail(where, "contains em dash")
        if DASHES[1] in text:
            rep.fail(where, "contains en dash")

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
    ap.add_argument("--json", action="store_true",
                    help="print the findings as JSON instead of text")
    ap.add_argument("--record", action="store_true",
                    help="under Vibe 3, rewrite the findings in docs/vibe-3-status.json "
                         "from this run and leave its per-profile lines alone")
    ap.add_argument("--mode", action="store_true",
                    help="print which mode this interpreter gives and exit: "
                         "live-2.5.0, live-vibe3 or static")
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

    # Three modes. Vibe 2.5.0 is asked the 2.5.0 way: its two loader calls plus this
    # script's rules for the failures that do not raise. Vibe 3 is asked what its
    # own registry recorded. Anything else, and --static-only, runs the static
    # mirror of the 2.5.0 rules.
    quiet = args.json or args.mode or args.record
    say = (lambda *a, **k: None) if quiet else print
    facts = None
    facts3 = None
    major = None if args.static_only else vibe_major()
    if major is not None and major >= 3:
        facts3 = load_vibe3_facts(dirs, args.prompts)
        if facts3 is None:
            say(f"note  {LIVE_OFF_REASON}")
    elif not args.static_only:
        facts = load_vibe_facts(dirs, args.prompts)
        if facts is None:
            if LIVE_OFF_REASON:
                say(f"note  {LIVE_OFF_REASON}")
            else:
                say("note  Vibe is not importable here, running static checks only.")
                say("      For the full set, use an interpreter that has Vibe CLI 2.5.0, the")
                say("      release these profiles are written for. The README's section Check")
                say("      before you ship has the two lines that make one.")
    mode = "live-vibe3" if facts3 else "live-2.5.0" if facts else "static"
    if args.mode:
        print(mode)
        for f in (facts, facts3):
            if f:
                shutil.rmtree(f["tmp_home"], ignore_errors=True)
        return 0

    rep = Report()
    seen: dict[str, Path] = {}
    if facts3:
        ver = facts3["version"]
        for f in files:
            verify_file_v3(f, facts3, rep, house=args.house, seen_stems=seen)
        ours = {f.stem for f in files}
        labelled = sorted(n for n in ours
                          if any(k == "safety" for k, _ in facts3["issues"].get(n, [])))
        if labelled:
            rep.notes.append(
                f"Vibe {ver} ignores 'safety' in an agent file, and says so for "
                f"{len(labelled)} of the files here. The label gates nothing on that "
                "release: what runs without asking is the approval policy's")
        # A file Vibe refuses can leave something else under its name in Vibe's list: a
        # broken file named after a built-in agent leaves the built-in there. That is
        # not this file being found.
        found = sorted(n for n in ours if n in facts3["discovered"]
                       and not (n in facts3["builtins"] and n in facts3["failures"]))
        subs = [n for n in found
                if str(facts3["discovered"][n].agent_type).endswith("subagent")]
        unusable = len(ours & set(facts3["failures"]))
        say(f"  live   Vibe {ver} found {len(found)} of the "
            f"{len(ours)} files here, {len(subs)} of them subagents"
            + (f", and cannot use {unusable} of the {len(ours)}" if unusable else ""))
        if facts3["default_policy"]:
            say(f"  live   a fresh Vibe {ver} configuration starts on the approval "
                f"policy '{facts3['default_policy']}'")
    else:
        for f in files:
            verify_file(f, facts, rep, house=args.house, prompt_dir=args.prompts,
                        seen_stems=seen)
        if facts and not rep.fails:
            live_discovery(dirs[0], facts, set(seen), rep)

    for f in (facts, facts3):
        if f:
            shutil.rmtree(f["tmp_home"], ignore_errors=True)

    if args.record:
        import datetime
        import json
        if not facts3:
            print("--record needs an interpreter that has Vibe 3: this run is mode "
                  f"'{mode}', and nothing was written.")
            return 1
        status_file = REPO / "docs" / "vibe-3-status.json"
        status = (json.loads(status_file.read_text(encoding="utf-8"))
                  if status_file.is_file() else {})
        # The findings carry their own release and day. `measured_with` and
        # `measured_on` belong to the per-profile lines, which were seen in sessions
        # and asked of Vibe by hand: this command re-measures none of them, so it must
        # not restamp them.
        status["findings_recorded_with"] = facts3["version"]
        status["findings_recorded_on"] = datetime.date.today().isoformat()
        status["findings"] = [{"level": lv, "profile": pr, "code": cd}
                              for lv, pr, cd in sorted(set(rep.codes))]
        status_file.write_text(json.dumps(status, indent=1, ensure_ascii=False) + "\n",
                               encoding="utf-8")
        print(f"recorded {len(status['findings'])} findings of Vibe {facts3['version']} in "
              f"{status_file.relative_to(REPO)}.")
        if status.get("measured_with") != facts3["version"]:
            print(f"The per-profile lines in that file are still the ones measured with Vibe "
                  f"{status.get('measured_with')} on {status.get('measured_on')}. This command "
                  "did not measure them again: it starts no session, and those lines say "
                  "what was seen in one, or computed, on that release. Re-measure them, or "
                  "say in the README that they are older.")
        else:
            print("Read the per-profile lines in that file against the findings before you "
                  "commit: a finding that changed means a line may no longer be true.")
        return 0

    if args.json:
        import json
        print(json.dumps({
            "vibe": facts3["version"] if facts3 else None,
            "mode": mode,
            "checked": rep.checked,
            "findings": [{"level": lv, "profile": pr, "code": cd}
                         for lv, pr, cd in sorted(set(rep.codes))],
            "fails": [[w, m] for w, m in rep.fails],
            "warns": [[w, m] for w, m in rep.warns],
            "notes": rep.notes,
        }, indent=1))
        return 1 if rep.fails else 0

    print()
    for note in rep.notes:
        print(f"note  {note}")
    for where, msg in rep.warns:
        print(f"WARN  {where}: {msg}")
    for where, msg in rep.fails:
        print(f"FAIL  {where}: {msg}")

    label = {"static": "mode static", "live-2.5.0": "mode live-2.5.0: static + live",
             "live-vibe3": (f"mode live-vibe3: asked Vibe {facts3['version']}"
                            if facts3 else "")}[mode]
    print()
    print(f"{rep.checked} profiles checked ({label}), "
          f"{len(rep.fails)} FAIL, {len(rep.warns)} WARN")
    if facts3:
        failing = len({w.split(" ")[0] for w, _ in rep.fails})
        if rep.fails:
            print(f"This run found something on {failing} of {rep.checked} profiles. Each "
                  f"FAIL line says what it is about on Vibe {facts3['version']}: a file "
                  "Vibe cannot use, a setting it ignores, a name with no tool or model "
                  "behind it, skills that cannot be opened, a tool it refuses, a filename, "
                  "or with --house a rule of this repository. A profile with no FAIL is "
                  "not proven to work: this asks Vibe what it recorded and starts no "
                  "session.")
            return 1
        except_label = " except the label noted above" if labelled else ""
        print(f"Vibe {facts3['version']} recorded no file here that it cannot use, and "
              f"no setting it ignores{except_label}. That is not proof a profile works: "
              "this asks Vibe what it recorded and starts no session.")
        return 0
    if rep.fails:
        print("A FAIL means Vibe would drop the profile, or load it and ignore the "
              "part you wrote it for.")
        return 1
    if facts is None:
        print("Every profile passes the static rules. Nothing here proves a Vibe loads "
              "them: run this again under an interpreter that has Vibe CLI 2.5.0 for "
              "that.")
    else:
        print("Every profile loads in the installed Vibe, and every key in it "
              "does something.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
