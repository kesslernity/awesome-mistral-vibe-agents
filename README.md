# Awesome Mistral Vibe CLI Agents

**In Mistral Vibe CLI 2.5.0 a profile fails in three different shapes, and not one of them puts anything on your screen.** That version loads an agent profile inside a `try`. On an exception it writes a single line to the log and returns `None`, so the agent is absent from the list with nothing in the session to say why. Most mistakes never raise at all: a misspelled top-level key is dropped, a misspelled key inside a tool table is *kept* and does nothing, and a path pattern that cannot match leaves you a profile that looks locked down and is not. The third shape is deferred, a bad `active_model` that loads cleanly and fails at the first request. That is why this repository ships a checker next to the profiles, and why the checker has its own test.

> **<!-- n-profiles:start -->17<!-- n-profiles:end --> agent profiles for Mistral Vibe CLI: <!-- n-primary:start -->13<!-- n-primary:end --> you switch into, <!-- n-subagents:start -->4<!-- n-subagents:end --> you delegate to. Copy a file, or point Vibe CLI at the folder. Every one of them prepares work for a person to decide on.**

[![Licence: CC BY-SA 4.0](https://img.shields.io/badge/License-CC%20BY--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-sa/4.0/)
<!-- badge-profiles:start -->[![Profiles](https://img.shields.io/badge/profiles-17-blue)](.vibe/agents/)<!-- badge-profiles:end -->
[![Verified against](https://img.shields.io/badge/verified%20against-mistral--vibe%202.5.0-green)](https://github.com/mistralai/mistral-vibe)

Not affiliated with, or endorsed by, Mistral AI. Every claim below was read from the loader's source or proven by running it, unless it says it comes from Mistral's release notes. The version is named because these are implementation details, and implementation details move.

**Written for Vibe CLI 2.5.0, and measured on 3.1.4: do not use these profiles there as they are.** Every profile here passes `tools/verify.py` against the 2.5.0 loader, last run on 23 November 2026. On Vibe CLI 3.1.4, measured the same day with its built-in model list and no network, not one of the 17 did all of what its file says. Two cannot be chosen at all. The others load and lose all or part of what they were written for. Three of them were seen, in a session, to lose a protection. Under `local-only`, Vibe printed a notice that `local` is not available and addressed the request to its default model, Mistral Large 4, on its built-in `mistral` provider: the model list built into 3.1.4 has no `local`. Vibe's source gives that provider the address of Mistral's hosted API. The test pointed it at a stand-in on the same machine, so no request left it. And `no-network` and `commit-ready` no longer refuse `curl` or `git push`: Vibe asks about them instead, and under the auto-approve policy both ran. [On Vibe 3](#on-vibe-3) has a line for every profile and says how each was seen. There is more than one cause. In 3.1.4 the file of a primary agent may no longer decide what runs without asking, which belongs to the approval policy, so Vibe ignores every allowlist and denylist in it. A `[tools.bash]` table that sets `default_timeout` without `max_timeout_seconds` makes Vibe refuse the file. The built-in model list changed. Tools were renamed or retired, and a skill is now opened with a `skill` tool that a profile's tool list has to name. And a subagent's `permission = "never"` became a ceiling with no exception.

Everything from here down to On Vibe 3 describes Vibe CLI 2.5.0.

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

These profiles are for Vibe CLI 2.5.0. If `vibe --version` prints a 3, read [On Vibe 3](#on-vibe-3) before you copy anything: under Vibe CLI 3.1.4 the checker below prints a FAIL for all but one of them, and that is the right answer.

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
vibe --agent read-only    # starts in a primary agent by name
cd /tmp/amva && ~/.local/share/uv/tools/mistral-vibe/bin/python tools/verify.py
```

That path is where `uv tool install mistral-vibe` keeps its interpreter on macOS and Linux, whatever the release it installed, and the checker says which mode it ran in. Under 2.5.0 it prints how many primary agents and subagents Vibe loaded. For the 2.5.0 answer beside a newer Vibe, [Check before you ship](#check-before-you-ship) has the two lines that make a 2.5.0 interpreter.

Full detail, including every search path in order and what happens when two profiles share a name, is in [`docs/INSTALL.md`](docs/INSTALL.md).

### Three install traps, all silent

**A project folder has to be trusted.** `.vibe/agents`, `.vibe/prompts` and `.vibe/skills` are read only when Vibe CLI's trusted-folders manager says the working directory is trusted. In an untrusted folder every project directory resolves to empty, with no message. Your profiles are not broken, they were never looked for.

**`agent_paths` does not expand `~`.** `skill_paths` and `tool_paths` do, through a validator. `agent_paths` has none, so `"~/.vibe/agents"` is taken literally, matches nothing, and says nothing. Absolute paths only.

**Project prompts are root only.** Vibe CLI *walks* the project tree for agents, skills and tools, pruning 26 well-known directory names. For prompts it does not walk: the only project prompt directory is `<workdir>/.vibe/prompts`. A prompt in a subproject is not found.

## Eight ways a profile fails, proven

Every row was produced by loading a deliberately broken profile into the Vibe CLI 2.5.0 interpreter, not by reading documentation.

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

Two of those rows drop the profile, and in 2.5.0 they are the closest thing to a loud failure: the exception is caught, the log line goes to a file, and the agent is missing from the list. One defers, and surfaces at the first request. The other five load, answer, and quietly are not the agent you wrote.

## The allowlist trap

This section describes 2.5.0. In the file of a primary agent, Vibe CLI 3.1.4 ignores an `allowlist` and records that it did. In a subagent's file it keeps the list, records nothing, and where the table also says `never` refuses the tool all the same: see [On Vibe 3](#on-vibe-3).

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

Vibe CLI's own `plan` profile avoids the trap by interpolating `str(PLANS_DIR.path / "*")` in Python at runtime. A static TOML file cannot do that, which is why every path pattern in this repository begins with `*` or `/`, and why `tools/verify.py` fails any that does not.

Worth being precise about the mechanism, because it is useful: `permission = "never"` plus a **matching** allowlist resolves to `always`. The allowlist is not a softening of `never`, it is the exception that overrides it. A non-matching path falls through to `never`. So the pair is a whitelist: deny everything, permit exactly these.

## Lists replace, they do not merge

`_deep_merge` recurses into dicts and assigns anything else. Every list key in a profile therefore **replaces** Vibe CLI's default rather than extending it:

```toml
[tools.bash]
denylist = ["curl"]     # you now have a one-entry denylist
```

Vibe CLI's default bash denylist is not about destruction, it is about commands that hang a non-interactive shell: `gdb`, `pdb`, `passwd`, the editors, `bash -i` and friends, `screen`, `tmux`. The snippet above deletes all of them. Worse, the defaults are chosen **per platform** at import time, so a list written on macOS silently removes the Windows entries (`cmd /k`, `powershell -NoExit`, `pwsh -NoExit`, `notepad`) for anyone on Windows.

So every profile here that sets a bash list restates the union of both platforms' defaults before adding anything, with a comment saying why. One kind of list is left alone on purpose: the allowlist of the two subagents whose table says `never`. There the allowlist is everything that runs, and restating the defaults would widen it. `verify.py` warns when a list drops a default, naming each one.

**What a table leaves alone depends on which `config.toml` Vibe reads.** In 2.5.0, once a `[tools.bash]` table exists, in the `config.toml` Vibe reads or in a profile, `permission`, `allowlist` and `denylist` are what is written out and nothing else: a list nobody wrote is empty, not Vibe's default. The `vibe` command writes every tool's table, lists included, into `~/.vibe/config.toml` the first time it runs, before it loads anything. On an install that still has that file, a profile's table merges into it key by key, and a list the profile does not set stays as you have it. Two files leave a list out. One is a `config.toml` written by hand or trimmed, whether it has no `[tools.bash]` table or one that sets something else: with only `default_timeout` in that table, `git status` asks and `vim notes.txt` asks under the default agent too. The other is the `.vibe/config.toml` of a trusted project, when it does not write the list out: 2.5.0 reads that file instead of yours, not on top of it. Three profiles here leave a list to the file Vibe reads: `slow-build` sets neither list, `test-runner` sets no denylist, `no-network` sets no allowlist. Where that file does not write the list out, `slow-build` and `test-runner` run with an empty denylist, so `vim notes.txt` asks instead of being refused, and `slow-build` and `no-network` run with an empty allowlist, so `git status` asks. They are left that way because restating a list in the profile would replace the entries you put in yours. `verify.py` prints a note for each list such a table leaves out, four for these three profiles, and it sees the empty case itself: it uses Vibe's classes without the `vibe` command, so no first-run file is written for it. Each case was measured with the real agent loop.

Same mechanism, four more places it bites:

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
$VIBE tools/selftest.py               # the checker's own test
```

`$VIBE` has to be an interpreter that has Vibe CLI 2.5.0 for the 2.5.0 answer. The path above is where `uv tool install mistral-vibe` keeps its interpreter on macOS and Linux, whatever the release it installed: `verify.py --mode` prints which mode an interpreter gives and nothing else, and an ordinary run names its mode in the line that counts the profiles, just above its closing line. To make a 2.5.0 interpreter beside a newer Vibe:

```bash
uv venv --python 3.12 /tmp/vibe250
uv pip install --python /tmp/vibe250/bin/python --exclude-newer 2026-03-20T00:00:00Z 'mistral-vibe==2.5.0'
VIBE=/tmp/vibe250/bin/python
```

The date matters. 2.5.0 asks for `mcp>=1.14.0` with no upper bound, and installed with today's dependencies it gets an `mcp` 2 that no longer has a function 2.5.0 imports. On 23 November 2026 `vibe --version` on such an install stopped with an ImportError, and the checker said so and ran its static rules only. With the date, the install got `mcp` 1.26.0 and the checker ran in its 2.5.0 mode.

Under Vibe CLI 2.5.0, `verify.py` reproduces the two calls inside the loader's `try` block, `AgentProfile.from_toml` then `apply_to_config`, so a profile Vibe CLI 2.5.0 would silently drop fails here loudly instead. That covers the two rows that raise, and nothing more. The quiet rows have no exception to catch, so their checks are mine rather than the loader's: unknown top-level keys, unknown keys inside a tool table, tables for tools that do not exist, `enabled_tools` entries that match no tool, an `active_model` that is not in the merged model list, path patterns that cannot match an absolute path, a stem that collides with a built-in agent, a `name` key that does nothing, and a custom `system_prompt_id` with no prompt file behind it. It finishes by instantiating the real `AgentManager` and printing what it actually loaded.

Under an interpreter that has Vibe 3, the same command asks a different question, because Vibe 3.1.4 does not drop a profile in silence: its own registry records which files it cannot use and which settings it ignores. So the checker builds Vibe's configuration in an isolated home, hands it the folders, and reports what Vibe's registry recorded: a file it cannot use, with Vibe's reason, and each setting it ignores, with Vibe's own sentence. The one exception is `safety`, which every primary profile here sets and Vibe ignores: the checker reports it once, as a note. It adds checks of its own for what that registry does not record about an agent file: a tool name Vibe has no tool for, a model that is not in the list built into Vibe, a skill filter in a file whose tool list leaves out the tool that opens a skill, a tool a subagent lists and is refused, and a filename that is not lower-case kebab or that Vibe takes for something else, which is an approval policy, a built-in agent, or a file it has already seen under that name. It starts no session, so a profile with no FAIL is not proven to work. On this repository it exits 1 under 3.1.4, and `docs/vibe-3-status.json` records what it finds. Under a Vibe 3 interpreter `selftest.py` compares a fresh run with that record, and fails if the Vibe 3 mode does not load, so a Vibe 3 release that changes one finding fails the self-test first.

Asked for a tool set it cannot reach, it degrades out loud. Without Vibe CLI importable it runs the static rules against a mirror of the same constraints and says which mode ran, because "every profile passes" and "every profile loads in the installed Vibe CLI" are different claims.

`selftest.py` is the control. A checker for silent failures is worth nothing if it fails silently too, so the self-test runs a small profile for each case, most of them deliberately broken, and holds the checker to the exit code and to the line. It also reads `verify.py` itself, as a floor under the cases: each place where the checker records a FAIL, a WARN or a note has to show its fixed text in the output of some case, or stand in the self-test's `NO_CASE` list with the reason nothing provokes it, and a place whose message the reading cannot read fails it. It is a floor, not a proof: places that print the same words count as one, and the self-test's docstring says what else the reading does not see. And the repository's own profiles have to give what is expected of them: clean under 2.5.0, the recorded findings under Vibe 3.

## The profiles

On Vibe CLI 2.5.0, start in a primary agent with `vibe --agent <name>`, and delegate to a subagent with the task tool. In the interactive terminal, 2.5.0's source binds Shift+Tab to the cycle through the primary agents: that was read in the source, and the terminal was not run here. The two tables describe 2.5.0. For 3.1.4, see [On Vibe 3](#on-vibe-3).

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
| [`test-runner`](.vibe/agents/test-runner.toml) | Runs the suite and reads the code. Its own edit tools are off, which is not a lock on the tests: a redirect after an allowlisted command still writes a file, and so can a test runner. | `system_prompt_id`, `tools.bash`, `tools.search_replace`, `tools.write_file` |
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

## On Vibe 3

Measured on Vibe CLI 3.1.4 on 23 November 2026, by running it, with no network: the model list was the one built into 3.1.4. The last column says how the line's main statement was seen. **Session**: a real `vibe -p` session ran with the profile, a local stand-in answering in place of the model, and the result was observed. **Asked**: Vibe 3.1.4's own code was run on the file with no session, which gives what its registry records, the configuration it merges and the answer of its approval gate. Where a line marked session says more than the session showed, it says how that part is known. A `vibe -p` session has nobody to ask: where a line says a call was asked about, Vibe stopped it with "needs approval, which a headless run cannot give".

In 3.1.4 the file of a primary agent may set fifteen keys, all about what the agent is: its models and providers, its tool and skill filters, its system prompt, when it compacts, and for a tool its timeouts and a `permission` of `ask` or `never`. It may narrow, never loosen. Any other setting Vibe knows is ignored when the file is read, and Vibe records each one it ignores: an `allowlist`, a `denylist`, `permission = "always"`, `safety`, and settings such as `include_project_context`. The file on disk is left as it is. A subagent's file is not filtered that way, and nothing is recorded for it. Its `permission = "never"` is a ceiling instead, and an allowlist is no exception to it. Tool names moved too. The edit tool is now called `edit`, and an agent file that still says `search_replace` names nothing, with no word from Vibe. `grep`, `task`, `web_fetch` and `web_search` are former tool names: Vibe 3.1.4 has no tool for them, and a tool filter that names one matches nothing. Its own notes on them say the agent searches through the shell, subagents are started with `agents.spawn`, and pages are fetched and the web is searched by connector tools.

<!-- vibe3-table:start -->
| Profile | On Vibe CLI 3.1.4 | How |
|---|---|---|
| [`cheap`](.vibe/agents/cheap.toml) | Runs on another model where `devstral-small` is not in the model list. In our runs, with the list built into 3.1.4 and no network, Vibe printed one notice and ran its default model, Mistral Large 4. With the model defined in your own `config.toml`, the profile ran on it. Whether a signed-in session's model catalogue offers `devstral-small` was not established. | session |
| [`commit-ready`](.vibe/agents/commit-ready.toml) | Keeps neither of its promises. Vibe ignores both lists, and says so when the session starts. `git add` was asked about, and `git push` is no longer refused: it was asked about, and under the auto-approve policy the push ran. | session |
| [`docs-only`](.vibe/agents/docs-only.toml) | Cannot write anything. The exception for prose files is ignored, so the write tool stays refused for every file: a write to a Markdown file was refused under the default policy and under auto-approve. The edit tool is now called `edit`, a name the profile does not list, and a call to it was refused. | session |
| [`humans-decide`](.vibe/agents/humans-decide.toml) | Cannot write its drafts. The exception that allowed the drafts folder is ignored, and the write to it was refused under the default policy and under auto-approve. Computed, not seen in a session: a subagent can still be started under it, so its promise of no delegation does not hold either. | session |
| [`local-only`](.vibe/agents/local-only.toml) | Does not keep the model local where no model called `local` is defined. In our run, with the model list built into 3.1.4, Vibe printed one notice and addressed the request to its default model, Mistral Large 4, on its built-in `mistral` provider. Vibe's source gives that provider the address of Mistral's hosted API, and the test pointed it at a stand-in on the same machine. With a model called `local` defined in your own `config.toml`, the request went to the local provider. Read in Vibe's own table and not seen in a session: the two web tools the profile refuses are former tool names. | session |
| [`no-network`](.vibe/agents/no-network.toml) | No longer refuses a network command. Vibe ignores the shell denylist, so `curl` was asked about, and under the auto-approve policy it ran. Read in Vibe's own table and not seen in a session: the two web tools the profile refuses are former tool names, and Vibe's notes on them say pages are fetched by one connector tool and the web is searched by another. The profile names neither. | session |
| [`quiet-context`](.vibe/agents/quiet-context.toml) | Does nothing. Vibe ignores all four settings in an agent file, and 3.1.4 marks two of them, `include_prompt_detail` and `include_model_info`, as no longer used in any config file. | asked |
| [`read-only`](.vibe/agents/read-only.toml) | Reads, and has lost its search tool. A shell call and a write were each refused under the default policy and under auto-approve, and a read ran. Read in Vibe's own table and not seen in a session: the search tool it lists is a former tool name, and Vibe's note on it says the agent searches through the shell, which this profile refuses. The model is still offered the shell and the write tools, and others the profile does not list. None of those others was called under this profile, and what one of them, `run_typescript`, can reach there was not measured. | session |
| [`review-only`](.vibe/agents/review-only.toml) | Opens none of the review skills it is there to keep. With two skills on the path whose names match its filter, neither was named to the model and loading one failed, because 3.1.4 opens a skill with the `skill` tool, which the profile does not list: with `skill` added to the list in a test copy, both were named and one loaded. The five skills that ship with Vibe were still named. Its tool list is the one of `read-only`: that its shell and write calls are refused the same way was computed here, not seen in a session. | session |
| [`skills-off`](.vibe/agents/skills-off.toml) | Drops your skills, and leaves the five that ship with Vibe 3.1.4: the model is still told about `vibe:create-plugin`, `vibe:import`, `vibe:skill-creator`, `vibe:vibe` and `vibe:worktree`. | session |
| [`slow-build`](.vibe/agents/slow-build.toml) | Cannot be chosen. Vibe refuses the file, "default_timeout is set without max_timeout_seconds. Set both, or neither.", and the session exits with a config error. Asked of Vibe's own code, not shown by that session: it also records that it ignores the output ceiling the file sets. | session |
| [`subagents-ready`](.vibe/agents/subagents-ready.toml) | Does nothing. `task` is a former tool name, because 3.1.4 starts a subagent with `agents.spawn`, and Vibe ignores the allowlist. | asked |
| [`test-runner`](.vibe/agents/test-runner.toml) | Cannot be chosen. Vibe refuses the file, "default_timeout is set without max_timeout_seconds. Set both, or neither.", and the session exits with a config error. | session |
| [`change-summariser`](.vibe/agents/change-summariser.toml) | Can be started, and cannot read a diff through its shell. In the sessions that started it, its read ran, and its shell was refused outright, `git diff` and `git status` included: for a subagent `permission = "never"` is a ceiling, allowlist or not. It was offered tools its file does not list. One of them, the write tool, was called and refused. The others were not called: `edit`, which Vibe's own code, asked, refuses for it as well, and `run_typescript`, `search_tool_functions`, `wait` and `skill`, of which what they can reach in a subagent was not measured. Read in Vibe's own table and not seen in a session: the search tool it lists is a former tool name. | session |
| [`codebase-cartographer`](.vibe/agents/codebase-cartographer.toml) | Registered as a subagent, and left with reading. Its shell, write and edit tools are refused, and the search tool it relies on is a former tool name, so it can read a file it is given the path of and has no search tool of its own. Computed from Vibe's own code, not seen in a session, and what the other tools a subagent is offered can reach was not measured. | asked |
| [`dependency-auditor`](.vibe/agents/dependency-auditor.toml) | Registered as a subagent, and its shell is refused outright: for a subagent `permission = "never"` is a ceiling, allowlist or not, so `ls`, `cat` and `git log` do not run. Computed from Vibe's own code, not seen in a session. | asked |
| [`source-collector`](.vibe/agents/source-collector.toml) | Registered as a subagent, and cut off from what it is for. `web_fetch` and `web_search` are former tool names, and Vibe's code gives a subagent defined by a file no connector tools. Computed and read in Vibe's source, not seen in a session, and what the tools it is still offered can reach was not measured. | asked |
<!-- vibe3-table:end -->

[`docs/vibe-3-status.json`](docs/vibe-3-status.json) holds these lines and the <!-- n-vibe3-findings:start -->41<!-- n-vibe3-findings:end -->  findings `tools/verify.py` makes on this repository under 3.1.4, one for each FAIL line it prints. `tools/selftest.py` compares a fresh run with those findings, so a later Vibe 3 release that changes one of them fails a test.

**What a restriction is worth on 3.1.4.** Three of its four approval policies were run in sessions: `ask`, `accept-edits` and `auto-approve`. `smart-approve` was not. A fresh configuration starts on `accept-edits`, under which a write to a file in the working directory ran without asking. Under `auto-approve` a denylist in your own `config.toml` is not consulted: with `denylist = ["curl"]` there, `curl` was refused under `ask` and under `accept-edits`, and ran under `auto-approve`. And `permission = "never"` on the write tool in your own `config.toml` held under `ask` alone of the three: under `accept-edits` and under `auto-approve` the file was written. The refusals that held under both `accept-edits` and `auto-approve` were the ones an agent file makes, by leaving a tool out of its list or by setting it to `never`, as `docs-only`, `read-only`, `humans-decide` and the subagent that was started do.

**Not established.** Every session was `vibe -p`: what the interactive terminal shows was not observed. Every run, on 2.5.0 and on 3.1.4, was made on macOS: Linux and Windows were not run, and Vibe's default lists differ per platform. 3.1.4 runs a session in a compiled engine, and what was read and run is the Python around it. The `smart-approve` policy was run in no session. In every session that ran, under nine primary profiles and in the one subagent that was started, the model was still offered `run_typescript`, `search_tool_functions`, `wait` and `skill`, which no profile lists. Under a restricted profile one of them was called: `skill`, under `review-only`, and the tool answered that the skill is not available. What the other three can reach under a restricted profile or in a subagent was not measured. That a tool list does not take delegation away on 3.1.4, and that a subagent started by a restricted agent stays inside that agent's limits, were computed from Vibe's code and not seen in a session. One subagent, `change-summariser`, was started in sessions, six of them, by the default agent. Why the five skills that ship with Vibe stay under `skills-off` and `review-only` was not established. Whether a signed-in session's model catalogue offers `devstral-small`, whether it offers web connector tools under these profiles, and whether starting a subagent asks the user were not established.

This repository stays a 2.5.0 library.

## What these profiles will not do for you


**A restrictive profile is not a sandbox, on 2.5.0 either.** There `no-network` denies `web_fetch` and `web_search` and puts curl, wget, nc, ssh, scp, rsync, the git remote verbs and the package installers on the bash denylist. Those are string prefix rules applied to each command the parser extracts, so a command the denylist does not spell is not refused by it: `npm ci` is asked about, and a command that begins like an entry of the allowlist the profile leaves in place, `tailscale` after `tail`, runs without a question. On 2.5.0 the profile removes the easy path, not the capability, and on 3.1.4 Vibe ignores that denylist: see the table above. Anything stronger belongs to the operating system: a container, a network namespace, a firewall.

**On 2.5.0 an allowlist entry is a string prefix, and that is no promise about which program runs or what it writes.** Vibe CLI 2.5.0 takes each command the shell parser extracts, keeps its name and its plain arguments, and tests whether that text begins with an entry. There is no word boundary. So `ls` also lets through `lsof`, and `git diff` lets through every command that begins with those eight characters, `git difftool` included, which exists to start another program. A redirect is not part of the text that is tested, and neither is a variable set in front of the command: `git log > out.txt` is tested as `git log`, and a variable in front of a listed command is passed to it unseen, which with some commands starts another program. An option that writes a file passes like any other argument: `git diff --output=x` begins with `git diff`. `echo` is on Vibe's own default list, so `echo text > notes.txt` runs without asking and writes the file under the default agent, and under any profile here that keeps that list: `test-runner` is one, so its edit tools being off is not a lock on the tests. No list can refuse a redirect or a leading variable, because neither is in the text the lists are tested on, and a denylist entry refuses a spelling, not an option: `git diff --output` on a denylist refuses `git diff --output=x` and lets `git diff --stat --output=x` through.

**So an allowlist on 2.5.0 says which beginnings run without a question. It does not confine a shell.** The two subagents that keep one, `change-summariser` and `dependency-auditor`, run it with `permission = "never"` and an allowlist: a command that begins with no entry is refused, and one that does runs with whatever plain arguments follow it. A command written inside an argument, as in `$(...)`, is extracted and tested like any other. Three things were done about it, and none of them confines the shell. The denylist is tested before the allowlist, so both subagents now carry a denylist entry for `git difftool`: that command is refused and `git diff` runs as before. `dependency-auditor` no longer lists `find`, which the same rule turned into permission for `find . -delete`. And their prompts tell the model which forms not to use, which is an instruction to a model and not a lock. What still passes: a redirect, a variable set in front of a listed command, an option that writes a file, any other command that begins like an entry, and `git difftool` itself where quotes are written inside the word, because the test reads the text as written and the text then no longer begins with the denylist entry. A trailing space in an allowlist entry would give it a word boundary, and the allowlists of these two are left without one, for what it would cost: the bare command is refused with it, `git diff` with no argument included, and an argument that is a bare number is not part of the text that is tested, so `head -20` at the end of a pipe would be refused too. On Vibe CLI 3.1.4 the default agent's own lists answer differently. Asked of its resolver under the `ask` and `accept-edits` policies, `lsof`, `git difftool`, the redirect, the writing option and the leading variable were each asked about, where `ls` and `git diff` ran. Under `auto-approve` all of them run, and `smart-approve` hands the call to a model that was not run. That is the answer of Vibe 3.1.4's own code, not something seen in a session.

**`humans-decide` constrains the tools, not the judgement, and it is the 2.5.0 answer.** It is the house doctrine in the only form that version can express, given it has no hook to attach a rule to: an `enabled_tools` whitelist, `permission = "never"`, and an allowlist as the exception to it. Vibe CLI 2.25.5 does have hooks, and they do not replace this profile: read the next section before you move the rule onto one.

It cannot make a model careful. What it does is narrow the routes to two and put a rule on both. The tools it enables are grep, read_file, todo, ask_user_question, write_file and search_replace, and `enabled_tools` is applied by the tool manager to everything it knows about, MCP tools included, so there is no shell and no server can add one later. Both write tools carry `permission = "never"` with `allowlist = ["*/drafts/*"]`.

Read that pattern before you trust it. `fnmatch` does not treat the separator specially, so `*/drafts/*` matches any directory called drafts that the agent can resolve a path to, not specifically the one in your project. If that difference matters where you work, put the absolute path in: `allowlist = ["/Users/you/project/drafts/*"]`. It is still not a sandbox. It is a small surface, described honestly.

**Nothing here is a safety authorisation.** No profile in this repository, and nothing an agent running under one produces, approves a permit to work, an isolation, a confined space entry, a job safety analysis, an incident classification or an inspection sign-off. AI prepares, a qualified human decides.

**Mistral Vibe CLI 2.5.0 has no hook system to attach any of this to. Vibe CLI 2.25.5 does, and it fails open.** In 2.5.0 a search of the package for the word finds one match, an unrelated environment variable, so the answer in that version is a restrictive profile and that is what these are.

Vibe CLI 2.25.5 has three hook types, `pre_tool`, `post_tool` and `post_agent`, read from `.vibe/hooks.toml` in the project root or `~/.vibe/hooks.toml` for the user. Mistral's release notes introduce an experimental hooks system in 2.9.0, add `before_tool` and `after_tool` hooks in 2.15.0, and make `hooks.toml` stable in 2.21.0. Know what that buys before you move a policy check onto one. The project file is only read in a directory you have trusted, so in an untrusted directory it is never opened at all. A hook that times out, exits non-zero or prints something the parser cannot read is recorded as a warning and the tool call proceeds anyway, unless that hook sets `strict = true`. Denial is a channel, not an exit code: a hook denies by printing `{"decision": "deny"}` on stdout, and `exit 1` is a broken hook rather than a refusal. A profile that never enables the tool is still the stronger statement, because it removes the route instead of policing it.

**On 2.25.5 the edit tool is called `edit`, not `search_replace`.** Every profile here is written against 2.5.0, where the tool is `search_replace`, and that name does not exist in 2.25.5: asking that release for its tool list returns `edit` and no `search_replace` at all. Four profiles name it. `docs-only` and `humans-decide` list it in `enabled_tools` and give it a `[tools.search_replace]` table, `test-runner` gives it a table, and `read-only` names it only in its description. Nothing about that is loud. If you are on 2.25.5 and an agent from this repository will not edit a file, that is the first thing to check. Under Vibe 3, `tools/verify.py` names the three whose settings use the old name, once for each place. The repository stays pinned to 2.5.0 until it is re-verified end to end against a newer release and passes there, because a badge that moves ahead of its measurements is worth less than no badge. The run of 23 November 2026 on 3.1.4, in On Vibe 3 above, is not that verification: its lines rest on `vibe -p` runs for twelve profiles, two of which did not start, and on Vibe's own code for the other five, with no interactive terminal, and the profiles do not pass it.

## Reference

- [`docs/INSTALL.md`](docs/INSTALL.md): every search path in order, the trusted folder precondition, what happens when two profiles share a name, and how to install the prompts.
- [`docs/OVERRIDE-REFERENCE.md`](docs/OVERRIDE-REFERENCE.md): the legal override surface. Per tool fields and defaults, the three different meanings of the word allowlist, the bash defaults on both platforms, and the table of keys that load and do nothing.
- [`CONTRIBUTING.md`](CONTRIBUTING.md): the loop, and the rule that a new check ships with the case that proves it fires.
- [`MANIFEST.json`](MANIFEST.json): every profile with its keys, its prompt and its sha256, generated by `tools/manifest.py`.

## Related

- [awesome-mistral-vibe-skills](https://github.com/kesslernity/awesome-mistral-vibe-skills?utm_source=github&utm_medium=repo&utm_campaign=amv_agents) is 137 skills in the Agent Skills format, which both Vibe CLI and the Vibe web interface read. `review-only` here is built to pair with its review skills.
- [awesome-mistral-vibe-prompts](https://github.com/kesslernity/awesome-mistral-vibe-prompts?utm_source=github&utm_medium=repo&utm_campaign=amv_agents) is 49 prompts for Vibe Work, scheduled tasks and the legacy Chat tab, including the ones these profiles are meant to be pointed at.
- [mistral-vibe](https://github.com/mistralai/mistral-vibe) is the CLI itself, Apache 2.0.
- The same work on the Microsoft side, five repositories: [agent skills](https://github.com/kesslernity/awesome-copilot-agent-skills?utm_source=github&utm_medium=repo&utm_campaign=amv_agents), [Cowork skills](https://github.com/kesslernity/awesome-copilot-cowork-skills?utm_source=github&utm_medium=repo&utm_campaign=amv_agents), [Copilot Chat agents](https://github.com/kesslernity/awesome-copilot-chat-agents?utm_source=github&utm_medium=repo&utm_campaign=amv_agents), [Copilot Studio agents](https://github.com/kesslernity/awesome-copilot-studio-agents?utm_source=github&utm_medium=repo&utm_campaign=amv_agents), [M365 Copilot prompts](https://github.com/kesslernity/awesome-microsoft-copilot-prompts?utm_source=github&utm_medium=repo&utm_campaign=amv_agents). Two runtimes, one set of rules about what an agent is allowed to decide.
- More on how these are built and why: [kesslernity.com](https://www.kesslernity.com/?utm_source=github&utm_medium=repo&utm_campaign=amv_agents).

## Licence

CC BY-SA 4.0. Use them, change them, ship them in your own repository. Keep the licence and say where they came from.
