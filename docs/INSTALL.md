# Install, and where Vibe actually looks

Everything here was read from `mistral-vibe` 2.5.0's own source, or produced by running it. Paths and precedence are implementation details, so check them again on a new version.

## The three places a profile can live

`AgentManager._compute_search_paths` builds the list in this order, and the order matters:

1. **`config.agent_paths`**, each entry included only if `path.is_dir()` at the time the manager is built.
2. **Project agent directories**, which is every `.vibe/agents` found by walking the trusted working directory.
3. **User agent directory**, which is `$VIBE_HOME/agents`, defaulting to `~/.vibe/agents`.

Duplicates are removed after resolving, so listing the same folder twice is harmless.

Inside each directory: `base.glob("*.toml")`. One level. A `.vibe/agents/review/strict.toml` is not found, and nothing says so.

## Precedence, which is asymmetric

Two rules, and they do not behave the same way:

- **A custom profile whose filename matches a built-in replaces the built-in.** Vibe logs `Custom agent '%s' overrides builtin agent` at info level and carries on. Name a file `plan.toml` and Plan mode is now yours, including whatever you forgot to set. The built-in names are `default`, `plan`, `accept-edits`, `auto-approve`, `explore` and `lean`.
- **Custom against custom, the first one found wins.** The later one is skipped with a debug-level log line. Since `agent_paths` is searched before the project directory and the project before the user directory, a profile in your `~/.vibe/agents` is shadowed by a same-named profile in the repository you happen to be in.

`tools/verify.py` fails any profile whose filename collides with a built-in, and any duplicate stem within the directories you pass it.

## Project directories need a trusted folder

`HarnessFilesManager.project_agents_dirs` walks `trusted_workdir`. If the trusted-folders manager does not consider the current directory trusted, `trusted_workdir` is `None` and the walk returns three empty tuples. Every project agent, skill and tool directory is then empty, silently.

Vibe asks about trust when you first start it in a folder. If the profiles you just copied do not appear, that is the first thing to check, not the TOML.

The walk uses `os.walk(..., topdown=True)` and prunes 26 directory names as it goes:

```
.cache .git .idea .mypy_cache .next .nuxt .nyc_output .pytest_cache .ruff_cache
.tox .uv-cache .venv .vscode __pycache__ coverage deps dist htmlcov logs
node_modules target temp third_party tmp vendor venv
```

A `.vibe/agents` under any of those is invisible. The result is cached for the process, so one scan per session.

## Prompts are not walked

The four subagents in this repository set `system_prompt_id` to a custom id, and `_check_system_prompt` resolves that id **while the profile loads**. A missing prompt file is not a deferred problem, it is a dropped agent.

Resolution order, from `VibeConfig.system_prompt`:

1. The built-in ids: `cli`, `explore`, `tests`, `lean`.
2. `project_prompts_dirs`, which is exactly `<workdir>/.vibe/prompts`, and only when the folder is trusted. **There is no walk here.** Agents, skills and tools are found anywhere in the tree; prompts are found at the root or not at all.
3. `user_prompts_dirs`, which is `$VIBE_HOME/prompts`, defaulting to `~/.vibe/prompts`.

So: copy `.vibe/prompts/*.md` wherever you copy the profiles, and if you install the profiles through `agent_paths` from a clone somewhere else, copy the prompts to `~/.vibe/prompts` because `agent_paths` carries profiles only.

## `agent_paths` does not expand `~`

```toml
# ~/.vibe/config.toml

agent_paths = ["~/code/awesome-mistral-vibe-agents/.vibe/agents"]   # finds nothing
agent_paths = ["/Users/you/code/awesome-mistral-vibe-agents/.vibe/agents"]   # works
```

`skill_paths` and `tool_paths` each have a before-validator that runs `Path(p).expanduser().resolve()`. `agent_paths` has none. The literal string `~/...` is not a directory, `is_dir()` is False, the path is dropped from the search list, and nothing is logged. Proven: the field round-trips as `PosixPath('~/.vibe/agents')`.

## Filtering what shows up

Two config keys, both real, both glob filters over agent names:

```toml
enabled_agents  = ["read-only", "humans-decide", "*-collector"]   # allowlist, wins if set
disabled_agents = ["cheap"]                                       # only consulted if enabled_agents is empty
```

Matching is `name_matches`: case-insensitive `fnmatch`, or a regular expression `fullmatch` when the pattern starts with `re:`. `"*"` matches everything.

A third key, `installed_agents`, exists for profiles marked `install_required`. Only the built-in `lean` uses it, which is why a stock Vibe lists five agents rather than six. Setting `install_required` in your own profile does nothing at all: it is not one of the four keys `from_toml` reads, so it lands in the config overrides and stays `False`.

## Verify, then trust

```bash
VIBE=~/.local/share/uv/tools/mistral-vibe/bin/python

$VIBE tools/verify.py                      # this repository
$VIBE tools/verify.py ~/.vibe/agents       # wherever you installed them
$VIBE tools/verify.py ~/.vibe/agents --prompts ~/.vibe/prompts
$VIBE tools/selftest.py                    # prove the checker still rejects things
```

The verifier runs against an isolated `VIBE_HOME` in a temporary directory so your own `~/.vibe/config.toml` cannot change the verdict, and it sets a placeholder `MISTRAL_API_KEY` only when the variable is unset, because `VibeConfig` has a validator that raises when the active model's provider has no key. It reads no real key, prints none, and writes none.

With the profiles installed, the check that matters is in the session:

```
vibe
```

Tab cycles the primary agents. `get_agent_order` puts `default`, `plan`, `accept-edits` and `auto-approve` first, in that fixed order, then every custom primary alphabetically. `explore` is not in the cycle because it is a subagent, and `lean` is not because it is `install_required`. Subagents are not in the cycle by design: they are reached through the task tool, and the tool refuses a profile whose `agent_type` is not `subagent`, which is how Vibe prevents recursive spawning.

## Uninstall

```bash
rm ~/.vibe/agents/{read-only,humans-decide,docs-only,cheap,quiet-context,skills-off}.toml
# and so on, or remove the agent_paths line from ~/.vibe/config.toml
```

Nothing here writes outside the directories you copy into. No profile in this repository sets `installed_agents`, `mcp_servers`, or anything that reaches a network.
