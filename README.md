# Awesome Mistral Vibe CLI Agents

**A profile fails in three different shapes, and not one of them puts anything on your screen.** Mistral Vibe CLI loads an agent profile inside a `try`. On an exception it writes a single line to the log and returns `None`, so the agent is absent from the list with nothing in the session to say why. Most mistakes never raise at all: a misspelled top-level key is dropped, a misspelled key inside a tool table is *kept* and does nothing, and a path pattern that cannot match leaves you a profile that looks locked down and is not. The third shape is deferred, a bad `active_model` that loads cleanly and fails at the first request. That is why this repository ships a checker next to the profiles, and why the checker has its own test.

> **<!-- n-profiles:start -->17<!-- n-profiles:end --> agent profiles for Mistral Vibe CLI: <!-- n-primary:start -->13<!-- n-primary:end --> you switch into, <!-- n-subagents:start -->4<!-- n-subagents:end --> you delegate to. Copy a file, or point Vibe CLI at the folder. Every one of them prepares work for a person to decide on.**

[![Licence: CC BY-SA 4.0](https://img.shields.io/badge/License-CC%20BY--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-sa/4.0/)
<!-- badge-profiles:start -->[![Profiles](https://img.shields.io/badge/profiles-17-blue)](.vibe/agents/)<!-- badge-profiles:end -->
[![Verified against](https://img.shields.io/badge/verified%20against-mistral--vibe%202.5.0-green)](https://github.com/mistralai/mistral-vibe)

Not affiliated with, or endorsed by, Mistral AI. Every claim below was read from the loader's source or proven by running it. The version is named because these are implementation details, and implementation details move.

---

## What an agent profile actually is

One TOML file. Its **filename** is the agent's name, and `from_toml` pops exactly four keys from the contents:

```toml
display_name = "Humans Decide"     # defaults to the filename, title cased
description  = "..."               # defaults to empty
safety       = "safe"              # safe | neutral | destructive | yolo
agent_type   = "agent"             # agent | subagent
```

**Everything else in the file is a partial `VibeConfig`**, deep merged over your live configuration when you switch into the agent. That is the whole model, and it is why a profile can reach any setting Vibe CLI has: the model, the tools, the permissions, the system prompt, the skills filter, the notifications.

Two consequences worth holding on to:

- A `name = "..."` key does nothing. The name is the filename. The key is read by nothing and reported by nothing.
- The merge is `_deep_merge`, which merges **dicts only**. Any list key replaces the default wholesale. More on that below, because it is the second most expensive mistake in this repository's subject matter.

## Install

Profiles live in `.vibe/agents/`, one level deep, discovered with `glob("*.toml")`.

**In a project**, so the whole team gets them:

```bash
git clone https://github.com/kesslernity/awesome-mistral-vibe-agents.git /tmp/amva
mkdir -p .vibe/agents .vibe/prompts
cp /tmp/amva/.vibe/agents/*.toml .vibe/agents/
cp /tmp/amva/.vibe/prompts/*.md  .vibe/prompts/
```

**For yourself, everywhere:**

```bash
git clone https://github.com/kesslernity/awesome-mistral-vibe-agents.git /tmp/amva
mkdir -p ~/.vibe/agents ~/.vibe/prompts
cp /tmp/amva/.vibe/agents/*.toml ~/.vibe/agents/
cp /tmp/amva/.vibe/prompts/*.md  ~/.vibe/prompts/
```

**Without copying**, by naming the clone in `~/.vibe/config.toml`:

```toml
agent_paths = ["/absolute/path/to/awesome-mistral-vibe-agents/.vibe/agents"]
```

Copy the prompts anyway. `agent_paths` moves the profiles and nothing else, and the four subagents here name their own system prompts.

Then confirm what Vibe CLI actually sees:

```bash
vibe            # Tab cycles the primary agents; the task tool lists the subagents
cd /tmp/amva && ~/.local/share/uv/tools/mistral-vibe/bin/python tools/verify.py
```

Full detail, including every search path in order and what happens when two profiles share a name, is in [`docs/INSTALL.md`](docs/INSTALL.md).

### Three install traps, all silent

**A project folder has to be trusted.** `.vibe/agents`, `.vibe/prompts` and `.vibe/skills` are read only when Vibe CLI's trusted-folders manager says the working directory is trusted. In an untrusted folder every project directory resolves to empty, with no message. Your profiles are not broken, they were never looked for.

**`agent_paths` does not expand `~`.** `skill_paths` and `tool_paths` do, through a validator. `agent_paths` has none, so `"~/.vibe/agents"` is taken literally, matches nothing, and says nothing. Absolute paths only.

**Project prompts are root only.** Vibe CLI *walks* the project tree for agents, skills and tools, pruning 26 well-known directory names. For prompts it does not walk: the only project prompt directory is `<workdir>/.vibe/prompts`. A prompt in a subproject is not found.

## Eight ways a profile fails, proven

Every row was produced by loading a deliberately broken profile into the shipping 2.5.0 interpreter, not by reading documentation.

| What is wrong in the TOML | What Vibe CLI does |
|---|---|
| Misspelled top-level key | **Loads.** `VibeConfig` is `extra="ignore"`, so the key is dropped and the thing you wrote it for never happens |
| Misspelled key inside `[tools.bash]` | **Loads.** `BaseToolConfig` is `extra="allow"`, so the key is *kept* in `model_extra` and has no effect whatsoever |
| Bad `permission` value, bad `safety`, bad `agent_type` | **Dropped.** The exception is caught, one log line, the agent is absent |
| Bad `system_prompt_id` | **Dropped at load.** `_check_system_prompt` is a model validator that touches the property, so the id is resolved while the profile loads |
| Bad `active_model` | **Loads, then crashes later.** The key check swallows the error at load time, and the failure surfaces when something asks for the active model |
| `enabled_tools = ["no_such_tool"]` | **Loads, and the agent gets zero tools.** Nothing is logged |
| `[tools.no_such_tool]` | **Loads and does nothing** |
| `install_required = true` | **Loads.** It is not a profile key, so it lands in the config overrides, stays `False`, and does nothing |

Two of those rows drop the profile, and they are the closest thing to a loud failure here: the exception is caught, the log line goes to a file, and the agent is missing from the list. One defers, and surfaces at the first request. The other five load, answer, and quietly are not the agent you wrote.

## The allowlist trap

This is the one worth the whole repository. A profile that writes only into `drafts/` looks like this, and is wrong:

```toml
[tools.write_file]
permission = "never"
allowlist = ["drafts/*"]     # matches nothing, ever, silently
```

`resolve_path_permission` runs `fnmatch` against the **resolved absolute path**. The candidate is `/Users/you/project/drafts/note.md`, so `drafts/*` cannot match it. Nor can `./drafts/*`. Nor can `~/drafts/*`, because a tool pattern is not tilde expanded. All three were tested. All three match nothing, and the permission stays `never`, so the agent cannot write at all and never says why.

The portable form starts at the root:

```toml
[tools.write_file]
permission = "never"
allowlist = ["*/drafts/*"]   # fnmatch's * crosses /, so this also matches drafts/sub/a.md
```

Vibe CLI's own `plan` profile avoids the trap by interpolating `str(PLANS_DIR.path / "*")` in Python at runtime. A static TOML file cannot do that, which is why every path pattern in this repository begins with `*/` or `/`, and why `tools/verify.py` fails any that does not.

Worth being precise about the mechanism, because it is useful: `permission = "never"` plus a **matching** allowlist resolves to `always`. The allowlist is not a softening of `never`, it is the exception that overrides it. A non-matching path falls through to `never`. So the pair is a whitelist: deny everything, permit exactly these.

## Lists replace, they do not merge

`_deep_merge` recurses into dicts and assigns anything else. Every list key in a profile therefore **replaces** Vibe CLI's default rather than extending it:

```toml
[tools.bash]
denylist = ["curl"]     # you now have a one-entry denylist
```

Vibe CLI's default bash denylist is not about destruction, it is about commands that hang a non-interactive shell: `gdb`, `pdb`, `passwd`, the editors, `bash -i` and friends, `screen`, `tmux`. The snippet above deletes all of them. Worse, the defaults are chosen **per platform** at import time, so a list written on macOS silently removes the Windows entries (`cmd /k`, `powershell -NoExit`, `pwsh -NoExit`, `notepad`) for anyone on Windows.

So every profile here that touches a bash list restates the union of both platforms' defaults before adding anything, with a comment saying why. `verify.py` warns when a list drops a default, naming each one.

Same mechanism, three more places it bites:

- `models = [...]` replaces the model list, so `devstral-2` and `devstral-small` stop existing.
- `providers = [...]` replaces the providers.
- `tools.task.allowlist` ships as exactly `["explore"]`. Set it to your own subagent and Vibe CLI's explore agent starts asking permission every time. Restate `explore`.
- `tools.grep.exclude_patterns` replaces 23 default excludes, which is how `node_modules` comes back.

And a piece of good news in the same area: a subagent that is not in `tools.task.allowlist` is **not blocked**. The allowlist returns `always` on a match, and a miss falls through to `permission = "ask"`. Unlisted subagents prompt. They work.

## Check before you ship

```bash
VIBE=~/.local/share/uv/tools/mistral-vibe/bin/python

$VIBE tools/verify.py                 # the profiles in this repository
$VIBE tools/verify.py DIR             # any other agents directory
$VIBE tools/verify.py --house         # plus this repository's own conventions
$VIBE tools/verify.py --static-only   # no Vibe CLI needed, Python 3.11 or newer
$VIBE tools/selftest.py               # 23 cases proving the checker rejects what it claims to
```

`verify.py` reproduces the two calls inside the loader's `try` block, `AgentProfile.from_toml` then `apply_to_config`, so a profile Vibe CLI would silently drop fails here loudly instead. That covers the two rows that raise, and nothing more. The quiet rows have no exception to catch, so their checks are mine rather than the loader's: unknown top-level keys, unknown keys inside a tool table, tables for tools that do not exist, `enabled_tools` entries that match no tool, an `active_model` that is not in the merged model list, path patterns that cannot match an absolute path, a stem that collides with a built-in agent, a `name` key that does nothing, and a custom `system_prompt_id` with no prompt file behind it. It finishes by instantiating the real `AgentManager` and printing what it actually loaded.

Asked for a tool set it cannot reach, it degrades out loud. Without Vibe CLI importable it runs the static rules against a mirror of the same constraints and says which mode ran, because "every profile passes" and "every profile loads in the installed Vibe CLI" are different claims.

`selftest.py` is the control. A checker for a runtime that fails silently is worth nothing if it fails silently too, so every rule gets a deliberately broken profile it has to reject, and the repository's own profiles have to pass clean.

## The profiles

Switch into a primary agent with Tab, or `/agent <name>`. Delegate to a subagent with the task tool.

### Primary

<!-- primary-table:start -->
| Profile | What it does | Keys it sets |
|---|---|---|
| [`cheap`](.vibe/agents/cheap.toml) | Switches the active model to devstral-small, the 24B Apache 2.0 model already present in Vibe CLI's default model list, and changes nothing else. | `active_model` |
| [`commit-ready`](.vibe/agents/commit-ready.toml) | Stages and commits without stopping to ask. The denylist is checked before the allowlist, so git push, git remote and the destructive resets are refused even though git is otherwise open. | `tools.bash` |
| [`docs-only`](.vibe/agents/docs-only.toml) | Edits prose and nothing else. write_file and search_replace are denied by default and allowed only on .md, .mdx, .rst and .txt files. No shell, so no build step can be run to check the result. | `enabled_tools`, `tools.search_replace`, `tools.write_file` |
| [`humans-decide`](.vibe/agents/humans-decide.toml) | Reads anything in the tree and writes only into a drafts folder. No shell, no network, no delegation. | `enabled_tools`, `tools.search_replace`, `tools.write_file` |
| [`local-only`](.vibe/agents/local-only.toml) | Points the active model at the llamacpp provider on 127.0.0.1:8080 and denies the two network tools. | `active_model`, `tools.web_fetch`, `tools.web_search` |
| [`no-network`](.vibe/agents/no-network.toml) | Keeps the work local. web_fetch and web_search are denied and the shell denylist blocks the usual ways out. | `tools.bash`, `tools.web_fetch`, `tools.web_search` |
| [`quiet-context`](.vibe/agents/quiet-context.toml) | Drops the project context block, the prompt detail and the model info from what is sent, and turns desktop notifications off. | `enable_notifications`, `include_model_info`, `include_project_context`, `include_prompt_detail` |
| [`read-only`](.vibe/agents/read-only.toml) | Searches and reads, and does nothing else. | `enabled_tools` |
| [`review-only`](.vibe/agents/review-only.toml) | Read-only tools, and only the review skills. | `enabled_skills`, `enabled_tools` |
| [`skills-off`](.vibe/agents/skills-off.toml) | Loads no skills at all. disabled_skills is a case-insensitive glob list and "*" matches every name. | `disabled_skills` |
| [`slow-build`](.vibe/agents/slow-build.toml) | Raises the shell timeout from 300 seconds to 30 minutes and the captured output ceiling from 16 kB to 64 kB. | `tools.bash` |
| [`subagents-ready`](.vibe/agents/subagents-ready.toml) | Pre-approves this repo's four subagents on the task tool, so delegating to them stops prompting. | `tools.task` |
| [`test-runner`](.vibe/agents/test-runner.toml) | Runs the suite and reads the code. Its own edit tools are off, so it cannot rewrite a failing test to make it pass, though an allowlisted test runner can still do whatever that runner does. | `system_prompt_id`, `tools.bash`, `tools.search_replace`, `tools.write_file` |
<!-- primary-table:end -->

### Subagents

Each one carries its own system prompt in [`.vibe/prompts/`](.vibe/prompts/). Copy those too, or the profile is dropped at load.

<!-- subagent-table:start -->
| Profile | What it does | Keys it sets |
|---|---|---|
| [`change-summariser`](.vibe/agents/change-summariser.toml) | Subagent. Reads a diff and reports what changed, what it touches and what it does not cover, with file and line references. Delegate to it with the task tool. It reports; it does not approve a change. | `enabled_tools`, `system_prompt_id`, `tools.bash` |
| [`codebase-cartographer`](.vibe/agents/codebase-cartographer.toml) | Subagent. Walks an unfamiliar tree and returns a map: entry points, module boundaries, where configuration and tests live, and the parts it could not account for. | `enabled_tools`, `system_prompt_id` |
| [`dependency-auditor`](.vibe/agents/dependency-auditor.toml) | Subagent. Reads the manifests and lock files in a tree and reports declared dependencies, declared licences, version ranges that float, and the places where the lock and the manifest disagree. | `enabled_tools`, `system_prompt_id`, `tools.bash` |
| [`source-collector`](.vibe/agents/source-collector.toml) | Subagent. Collects and quotes the sources for a question, each with its URL and the date shown on the page, and separates what a source states from what it implies. | `enabled_tools`, `system_prompt_id` |
<!-- subagent-table:end -->

## What these profiles will not do for you

**A restrictive profile is not a sandbox.** `no-network` denies `web_fetch` and `web_search` and puts curl, wget, nc, ssh, scp, rsync, the git remote verbs and the package installers on the bash denylist. Those are string prefix rules applied to the parsed command, so a determined command still reaches the network. The profile removes the easy path, not the capability. Anything stronger belongs to the operating system: a container, a network namespace, a firewall.

**`humans-decide` constrains the tools, not the judgement, and it is the 2.5.0 answer.** It is the house doctrine in the only form that version can express, given it has no hook to attach a rule to: an `enabled_tools` whitelist, `permission = "never"`, and an allowlist as the exception to it. Vibe CLI 2.25.5 does have hooks, and they do not replace this profile: read the next section before you move the rule onto one.

It cannot make a model careful. What it does is narrow the routes to two and put a rule on both. The tools it enables are grep, read_file, todo, ask_user_question, write_file and search_replace, and `enabled_tools` is applied by the tool manager to everything it knows about, MCP tools included, so there is no shell and no server can add one later. Both write tools carry `permission = "never"` with `allowlist = ["*/drafts/*"]`.

Read that pattern before you trust it. `fnmatch` does not treat the separator specially, so `*/drafts/*` matches any directory called drafts that the agent can resolve a path to, not specifically the one in your project. If that difference matters where you work, put the absolute path in: `allowlist = ["/Users/you/project/drafts/*"]`. It is still not a sandbox. It is a small surface, described honestly.

**Nothing here is a safety authorisation.** No profile in this repository, and nothing an agent running under one produces, approves a permit to work, an isolation, a confined space entry, a job safety analysis, an incident classification or an inspection sign-off. AI prepares, a qualified human decides.

**Mistral Vibe CLI 2.5.0 has no hook system to attach any of this to. Vibe CLI 2.25.5 does, and it fails open.** In 2.5.0 a search of the package for the word finds one match, an unrelated environment variable, so the answer in that version is a restrictive profile and that is what these are.

Vibe CLI 2.25.5 added three hook types, `pre_tool`, `post_tool` and `post_agent`, read from `.vibe/hooks.toml` in the project root or `~/.vibe/hooks.toml` for the user. Know what that buys before you move a policy check onto one. The project file is only read in a directory you have trusted, so in an untrusted directory it is never opened at all. A hook that times out, exits non-zero or prints something the parser cannot read is recorded as a warning and the tool call proceeds anyway, unless that hook sets `strict = true`. Denial is a channel, not an exit code: a hook denies by printing `{"decision": "deny"}` on stdout, and `exit 1` is a broken hook rather than a refusal. A profile that never enables the tool is still the stronger statement, because it removes the route instead of policing it.

**On 2.25.5 the edit tool is called `edit`, not `search_replace`.** Every profile here is written against 2.5.0, where the tool is `search_replace`, and that name does not exist in 2.25.5: asking the current release for its tool list returns `edit` and no `search_replace` at all. Four profiles name it. In `docs-only` and `humans-decide` it sits in `enabled_tools`, in `test-runner` it is a `[tools.search_replace]` section, and in `read-only` it appears only in the description. Nothing about that is loud. If you are on 2.25.5 and an agent from this repository will not edit a file, that is the first thing to check, and `tools/verify.py` will tell you which profiles name it. The repository stays pinned to 2.5.0 until it is re-verified end to end against a newer release, because a badge that moves ahead of its measurements is worth less than no badge.

## Reference

- [`docs/INSTALL.md`](docs/INSTALL.md): every search path in order, the trusted folder precondition, what happens when two profiles share a name, and how to install the prompts.
- [`docs/OVERRIDE-REFERENCE.md`](docs/OVERRIDE-REFERENCE.md): the legal override surface. Per tool fields and defaults, the three different meanings of the word allowlist, the bash defaults on both platforms, and the table of keys that load and do nothing.
- [`CONTRIBUTING.md`](CONTRIBUTING.md): the loop, and the rule that a new check ships with the case that proves it fires.
- [`MANIFEST.json`](MANIFEST.json): every profile with its keys, its prompt and its sha256, generated by `tools/manifest.py`.

## Related

- [awesome-mistral-vibe-skills](https://github.com/kesslernity/awesome-mistral-vibe-skills?utm_source=github&utm_medium=repo&utm_campaign=amv_agents) is 137 skills in the format Vibe CLI reads. `review-only` here is built to pair with its review skills.
- [awesome-mistral-vibe-prompts](https://github.com/kesslernity/awesome-mistral-vibe-prompts?utm_source=github&utm_medium=repo&utm_campaign=amv_agents) is 49 prompts for Vibe Work, scheduled tasks and Chat, including the ones these profiles are meant to be pointed at.
- [mistral-vibe](https://github.com/mistralai/mistral-vibe) is the CLI itself, Apache 2.0.
- The same work on the Microsoft side, five repositories: [agent skills](https://github.com/kesslernity/awesome-copilot-agent-skills?utm_source=github&utm_medium=repo&utm_campaign=amv_agents), [Cowork skills](https://github.com/kesslernity/awesome-copilot-cowork-skills?utm_source=github&utm_medium=repo&utm_campaign=amv_agents), [Copilot Chat agents](https://github.com/kesslernity/awesome-copilot-chat-agents?utm_source=github&utm_medium=repo&utm_campaign=amv_agents), [Copilot Studio agents](https://github.com/kesslernity/awesome-copilot-studio-agents?utm_source=github&utm_medium=repo&utm_campaign=amv_agents), [M365 Copilot prompts](https://github.com/kesslernity/awesome-microsoft-copilot-prompts?utm_source=github&utm_medium=repo&utm_campaign=amv_agents). Two runtimes, one set of rules about what an agent is allowed to decide.
- More on how these are built and why: [kesslernity.com](https://www.kesslernity.com/?utm_source=github&utm_medium=repo&utm_campaign=amv_agents).

## Licence

CC BY-SA 4.0. Use them, change them, ship them in your own repository. Keep the licence and say where they came from.
