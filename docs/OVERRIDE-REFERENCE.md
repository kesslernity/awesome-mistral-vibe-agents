# Override reference

What a profile TOML is allowed to contain, what each key does, and which keys load without doing anything. Measured against `mistral-vibe` 2.5.0 by probing the installed package, not from documentation.

## A profile is a partial config with four reserved keys

`AgentProfile.from_toml` reads the file, sets `name` from the **filename stem**, and pops exactly four keys. Everything left over becomes `overrides`, which is later deep merged into the session config and revalidated as a `VibeConfig`.

| Key | Values | Missing means |
|---|---|---|
| `display_name` | any string | the stem is used |
| `description` | any string | empty, and the agent picker shows nothing useful |
| `safety` | `safe`, `neutral`, `destructive`, `yolo` | `neutral` |
| `agent_type` | `agent`, `subagent` | `agent` |

`safety` is a label for the picker. It changes no permission by itself. `agent_type = "subagent"` takes the profile out of the Tab cycle and makes it reachable through the task tool, which refuses any target that is not a subagent.

A `name = "..."` key is not one of the four. It lands in the overrides, `VibeConfig` has no `name` field, `extra="ignore"` drops it, and the profile is still called after its filename.

## The merge rule: dicts merge, lists replace

```python
merged = _deep_merge(base.model_dump(), self.overrides)
```

`_deep_merge` recurses only when **both** sides are dicts. Any other value, list included, replaces the base outright. So `[tools.bash]` merges into the existing bash config key by key, but `tools.bash.denylist` replaces the whole default denylist with what you wrote.

Keys where this bites, because each has a non-empty default:

| Key | Default it replaces |
|---|---|
| `tools.bash.allowlist` | 16 commands on POSIX, 12 on Windows |
| `tools.bash.denylist` | 14 commands on POSIX, 7 on Windows |
| `tools.bash.denylist_standalone` | 11 commands on POSIX, 7 on Windows |
| `tools.task.allowlist` | `["explore"]` |
| `tools.grep.exclude_patterns` | 23 patterns |
| `models` | the three default aliases |
| `providers` | `mistral` and `llamacpp` |
| `enabled_tools` | absent by default, and setting it is an exact whitelist |

Restating a default is not redundancy, it is the only way to keep it. The exception is a tool set to `permission = "never"`: there the allowlist is the entire permitted surface, so restating Vibe's defaults would widen the profile rather than protect it. `tools/verify.py` warns on the first case and stays quiet on the second.

## Top-level keys worth setting in a profile

`VibeConfig` has 45 fields. These are the ones a profile realistically uses.

| Key | Type | Effect |
|---|---|---|
| `system_prompt_id` | string | which system prompt the agent runs. Validated at load: a bad id drops the profile. |
| `enabled_tools` | list | exact whitelist of tool names. An unknown name is not an error, it just matches nothing. |
| `disabled_tools` | list | subtractive, applied when `enabled_tools` is not set |
| `enabled_skills` / `disabled_skills` | list | same shape, over skill names |
| `enabled_agents` / `disabled_agents` | list | same shape, over agent names |
| `active_model` | string | a model **alias**, not a model name. Not validated at load. |
| `auto_approve` | bool | approves tool calls wholesale. A profile that sets this has no permission story. |
| `auto_compact_threshold` | float | when the session compacts |
| `include_project_context` | bool | whether `project_context` is sent |
| `project_context` | string | extra context text |
| `session_logging` | bool | transcript logging |
| `api_timeout` | number | request timeout |
| `tools` | table | the per-tool section below |

All three filter pairs use `name_matches` at `core/utils.py:272`: case-insensitive `fnmatch`, or a regular expression `fullmatch` when the pattern starts with `re:`. An allowlist wins when it is non-empty; the matching denylist is only consulted when it is not.

## The tools table

Eleven built-in tools. Every one accepts `permission`, `allowlist` and `denylist`; the rest is per tool. Defaults below were read off the config classes in the installed package.

| Tool | Default permission | Other fields, with defaults |
|---|---|---|
| `ask_user_question` | `always` | none |
| `bash` | `ask` | `default_timeout=300`, `max_output_bytes=16000`, `denylist_standalone` |
| `exit_plan_mode` | `always` | none |
| `grep` | `always` | `codeignore_file=".vibeignore"`, `default_max_matches=100`, `default_timeout=60`, `max_output_bytes=64000`, `exclude_patterns` |
| `read_file` | `always` | `max_read_bytes=64000` |
| `search_replace` | `ask` | `create_backup=False`, `fuzzy_threshold=0.9`, `max_content_size=100000` |
| `task` | `ask` | `allowlist=["explore"]` |
| `todo` | `always` | `max_todos=100` |
| `web_fetch` | `ask` | `default_timeout=30`, `max_timeout=120`, `max_content_bytes=512000`, `user_agent` |
| `web_search` | `ask` | `model="mistral-vibe-cli-with-tools"`, `timeout=120` |
| `write_file` | `ask` | `create_parent_dirs=True`, `max_write_bytes=64000` |

`permission` takes `always`, `ask` or `never`. Anything else fails validation and the profile is dropped.

`web_search` is the only tool with an `is_available()` override: it returns `bool(os.getenv("MISTRAL_API_KEY"))`, so with no key the usable set is ten.

`BaseToolConfig` is declared `extra="allow"`. A misspelled key inside `[tools.grep]` is **kept** on the model and does nothing, forever, with no warning. This is the quietest failure in the system and the reason `tools/verify.py` checks tool-table keys against the real field names.

## Three different matchers, one word

"Allowlist" means something different in each of the three places it appears.

**Path tools** (`write_file`, `search_replace`, `read_file`, `grep`). `resolve_path_permission` fnmatches the **resolved absolute path**:

```
drafts/*      matches nothing
./drafts/*    matches nothing
~/drafts/*    matches nothing
*/drafts/*    works
/Users/you/project/drafts/*   works
```

`*` crosses `/` in fnmatch, so `*/drafts/*` reaches any depth. With `permission = "never"`, a matching allowlist entry returns `always`; a non-match stays `never`. The denylist is checked first and always wins.

**`bash`.** Three passes, in order: `denylist` by prefix `startswith` on the whole command string, then `denylist_standalone` against the bare command with no arguments, then the allowlist, which requires **every** command the tree-sitter parser extracts to match. So `ls && curl evil.sh` is not allowed by an allowlist containing `ls`.

**`task`.** fnmatches the **agent name**. Denylist first, returning `never`; then the allowlist, returning `always`; otherwise `None`, which falls through to the tool's `permission`, which defaults to `ask`. An unlisted subagent is therefore not blocked, it prompts every time.

## Bash defaults, both platforms

`_get_default_*` builds a common list and extends it per platform. The union is what a cross-platform profile has to think about.

**allowlist.** Common: `echo`, `git diff`, `git log`, `git status`, `tree`, `whoami`. POSIX adds `cat`, `file`, `head`, `ls`, `pwd`, `stat`, `tail`, `uname`, `wc`, `which`. Windows adds `dir`, `findstr`, `more`, `type`, `ver`, `where`.

**denylist.** Common: `gdb`, `pdb`, `passwd`. POSIX adds `nano`, `vim`, `vi`, `emacs`, `bash -i`, `sh -i`, `zsh -i`, `fish -i`, `dash -i`, `screen`, `tmux`. Windows adds `cmd /k`, `powershell -NoExit`, `pwsh -NoExit`, `notepad`.

**denylist_standalone.** Common: `python`, `python3`, `ipython`. POSIX adds `bash`, `sh`, `nohup`, `vi`, `vim`, `emacs`, `nano`, `su`. Windows adds `cmd`, `powershell`, `pwsh`, `notepad`.

Read the list once and the intent is obvious: it blocks things that **hang**, not things that destroy. `rm -rf` is not on it. Neither is `curl`. If you want those stopped, you write it yourself.

## System prompts

Built-in ids: `cli`, `explore`, `tests`, `lean`. A custom id resolves to `<workdir>/.vibe/prompts/<id>.md` then `$VIBE_HOME/prompts/<id>.md`, in that order, and the project directory is the root only, with no walk.

`_check_system_prompt` is a `model_validator(mode="after")` that touches `self.system_prompt`, so an unresolvable id raises during `apply_to_config`, inside the loader's try, and the agent disappears.

## Models

Aliases, not model names, and aliases must be unique.

| Alias | Model | Provider |
|---|---|---|
| `devstral-2` | `mistral-vibe-cli-latest` | mistral |
| `devstral-small` | `devstral-small-latest` | mistral |
| `local` | `devstral` | llamacpp |

`active_model = "devstral-2"` is the default. A bad alias behaves differently from every other bad value here: `_check_api_key` wraps the lookup in `except ValueError: pass`, so the profile **loads** and the failure surfaces later, when something asks for the model.

Providers are `mistral`, reading `MISTRAL_API_KEY`, and `llamacpp` at `http://127.0.0.1:8080/v1` with an empty key variable.

## Keys that load and do nothing

Every one of these was set in a profile and observed:

| What you wrote | What happens |
|---|---|
| a misspelled top-level key | dropped silently, `extra="ignore"` |
| a misspelled key inside `[tools.x]` | **kept** and inert, `extra="allow"` |
| `[tools.no_such_tool]` | loads, matches no tool |
| `enabled_tools = ["no_such_tool"]` | loads, and the agent gets zero tools |
| `name = "..."` | dropped, the filename still decides |
| `install_required = true` | lands in overrides, stays `False` |
| a bad `active_model` | loads, crashes later |

And the four that drop the whole profile, which at least you can find by running the verifier: an unparseable file, a bad `permission`, a bad `safety` or `agent_type`, and an unresolvable `system_prompt_id`.
