# Contributing

Short version: **a claim in this repository has to have been measured.** Not read in documentation, not remembered, not inferred from a function name. Run it, then write it down.

## The loop

```bash
VIBE=~/.local/share/uv/tools/mistral-vibe/bin/python

$VIBE tools/verify.py --house     # every profile, static rules plus a real load
$VIBE tools/selftest.py           # every rule in verify.py, proven to fire
$VIBE tools/manifest.py           # regenerate MANIFEST.json and the README tables
$VIBE tools/manifest.py --check   # exits 1 if either is stale
```

Use Vibe's own interpreter for `verify.py`. On any other Python 3.11 or newer it still runs, prints `static only`, and says in its closing line that nothing was loaded. On Python 3.10 or older it exits with an explanation, because there is no `tomllib`.

Commit `MANIFEST.json` and `README.md` alongside whatever you changed. Both are generated, and `manifest.py --check` is the reason a stale one cannot ship.

## Adding a profile

1. Write `.vibe/agents/<kebab-name>.toml`. The filename is the agent name, so choose it carefully: it is what appears in the picker, what `enabled_agents` patterns match, and what the task tool allowlist matches for a subagent.
2. Set all four reserved keys: `display_name`, `description`, `safety`, `agent_type`. The description is not decoration. It is the only thing a user reads before choosing the agent, and for a subagent it is most of what the delegating model has to go on.
3. Say in the description **what the profile changes and what it does not**. "Read only" is a promise; name the tools it leaves enabled.
4. If the profile sets `system_prompt_id`, the prompt goes in `.vibe/prompts/<id>.md` in the same commit. A missing prompt does not warn, it deletes the agent.
5. Comment the traps in the file itself. Anyone who copies one profile out of this repository takes the comments with them and leaves the README behind.
6. Run the loop above. `verify.py` must report the profile with no FAIL and no WARN.

## Adding a rule to the checker

**Add its case to `tools/selftest.py` in the same commit.** The selftest builds a deliberately broken profile per rule in a temporary directory, runs `verify.py` as a subprocess, and asserts both the exit code and a marker string in the output. A rule with no failing case is a rule nobody has proven runs, which on a loader that swallows exceptions is worse than no rule at all.

A rule earns its place by catching something that is **silent** in Vibe. The loader catches every exception from `from_toml` and `apply_to_config`, logs a warning, and returns `None`. Pydantic's `extra="ignore"` on the config and `extra="allow"` on tool configs mean a typo produces no error anywhere. Those are the failures worth a rule. A rule that only restates what Vibe already refuses loudly is noise.

A WARN is for a correct file that is probably not what you meant: a list that replaces a default, a task allowlist that drops `explore`. If a WARN fires on a file that is right, the rule is wrong. That already happened once here: the bash allowlist warning had to learn that `permission = "never"` inverts its meaning, because with `never` the allowlist is the whole permitted surface rather than a widening of the default.

## What the tools own

| File | Owns |
|---|---|
| `tools/verify.py` | the rules, the live load, the verdict |
| `tools/selftest.py` | one broken profile per rule, plus one clean repository |
| `tools/manifest.py` | `MANIFEST.json` and the two README tables between their markers |

Do not hand edit `MANIFEST.json`, and do not hand edit the README between `<!-- primary-table:start -->` and `<!-- subagent-table:end -->`. The tables are filled between markers rather than by substituting placeholder tokens, because a placeholder is consumed on the first run and the second run writes the literal token into the page.

## House rules the profiles keep

Three of these are not style preferences, and a pull request that breaks one will be asked to change.

- **Nothing here is a safety authorisation.** No profile, and nothing an agent running under one produces, approves a permit to work, an isolation, a confined space entry, a job safety analysis, an incident classification or an inspection sign-off. AI prepares, a qualified human decides.
- **A subagent reports, it does not rule.** The four system prompts in `.vibe/prompts` all end with a version of the same line: the output is a draft for a reviewer, and it never says approved, ready or safe.
- **Missing information is named.** Every prompt has a section for what it could not establish, and an empty one is treated as suspicious rather than clean.
- **No em dashes**, in profiles, prompts, documentation or code comments. `verify.py` fails a profile that contains one.

## Versions

Everything here is measured against one version, and the badge, the README and `MANIFEST.json` all say which. When Vibe changes, the honest move is to re-run the probes and change the number, not to assume the behaviour survived. The interesting facts in this repository are implementation details: what the loader catches, which defaults are lists, which validators run at load. None of them are contractual.

## Licence

Contributions are accepted under CC BY-SA 4.0, the licence this repository ships under.
