# Contributing

Short version: **a claim in this repository has to have been measured.** Not read in documentation, not remembered, not inferred from a function name. Run it, then write it down.

## The loop

```bash
VIBE=~/.local/share/uv/tools/mistral-vibe/bin/python

$VIBE tools/verify.py --house     # every profile, static rules plus a real load
$VIBE tools/selftest.py           # the checker's own test
$VIBE tools/manifest.py           # regenerate MANIFEST.json and the README tables
$VIBE tools/manifest.py --check   # exits 1 if either is stale
```

Use an interpreter that has Vibe CLI 2.5.0 for `verify.py`. The path above is where `uv tool install mistral-vibe` keeps its interpreter on macOS and Linux, whatever the release it installed, and the README's section Check before you ship has the two lines that make a 2.5.0 interpreter beside a newer Vibe. On any other Python 3.11 or newer it still runs, prints `static`, and says in its closing line that nothing was loaded. On Python 3.10 or older it exits with an explanation, because there is no `tomllib`.

Under an interpreter that has Vibe 3 it asks Vibe 3 what it recorded about each file, and on this repository it exits 1: that is the measured state, kept in `docs/vibe-3-status.json`. After a new Vibe 3 release, `tools/verify.py --record` rewrites the findings in that file and stamps them with the release and the day. It does not touch the per-profile lines or their own stamp: those say what was seen in a session, or computed, on the release named there, and a new release means measuring them again, not restamping them.

Commit `MANIFEST.json`, `README.md` and `docs/vibe-3-status.json` alongside whatever you changed. The first two are generated, and `manifest.py --check` is the reason a stale one cannot ship.

## Adding a profile

1. Write `.vibe/agents/<kebab-name>.toml`. The filename is the agent name, so choose it carefully: it is what `vibe --agent` takes, what `enabled_agents` patterns match, and what the task tool allowlist matches for a subagent.
2. Set all four reserved keys: `display_name`, `description`, `safety`, `agent_type`. The description is not decoration. For a subagent it is what Vibe CLI 2.5.0 tells the delegating model about it, and it is what this repository's tables and its site print for every profile.
3. Say in the description **what the profile changes and what it does not**. "Read only" is a promise; name the tools it leaves enabled.
4. If the profile sets `system_prompt_id`, the prompt goes in `.vibe/prompts/<id>.md` in the same commit. In Vibe CLI 2.5.0 a missing prompt puts nothing in the session: one warning goes to the log file and the agent is absent from the list.
5. Comment the traps in the file itself. Anyone who copies one profile out of this repository takes the comments with them and leaves the README behind.
6. Add the profile's line to `docs/vibe-3-status.json`, under `profiles`: what Vibe 3 does with it, how you saw it (`session` or `asked`), and a label of a few words. `manifest.py` stops until the line is there. If you did not measure it on Vibe 3, the line says exactly that.
7. If you have Vibe 3, run `tools/verify.py --record` under it. It rewrites the recorded findings, and the count of them in the README is written by `manifest.py`, so this comes before the loop.
8. Run the loop above under a Vibe CLI 2.5.0 interpreter. `verify.py` must report the profile with no FAIL and no WARN. A `note` is not a fault: it says what the profile leaves to the `config.toml` Vibe reads.
9. If you have Vibe 3, run `tools/selftest.py` under it too. It holds the recorded findings.

## Adding a rule to the checker

**Add its case to `tools/selftest.py` in the same commit.** The selftest builds a small profile for each case in a temporary directory, most of them deliberately broken, runs `verify.py` as a subprocess, and asserts both the exit code and a marker string on a line of the right kind. A rule with no failing case is a rule nobody has proven runs, which is worse than no rule at all when the failures it exists for are the silent ones. The selftest holds you to a floor. It reads `verify.py` and knows a rule by its spelling: a call to `rep.fail`, `rep.warn` or `rep.notes.append` inside a top-level `def`, with the message as a positional argument. Such a call fails the selftest when its message is not written out in the call, when the fixed text of the message is shorter than eight characters, or when that text shows in no case and has no entry in `NO_CASE`, each looked for in the mode that can print it. A rule recorded another way may not be read at all, and then nothing holds you to its case. So record a rule that way, and give its message words no other message has.

A 2.5.0 rule earns its place by catching something that is **silent** in Vibe CLI 2.5.0, the release these profiles are written for. Its loader catches every exception from `from_toml` and `apply_to_config`, logs a warning, and returns `None`. Pydantic's `extra="ignore"` on the config and `extra="allow"` on tool configs mean a typo produces no error anywhere. Those are the failures worth a rule. A 2.5.0 rule that only restates what Vibe already refuses loudly is noise. The Vibe 3 mode is the other way round on purpose: Vibe 3 records what it drops, so the mode repeats Vibe's record for a folder of files, and adds a rule only for what that record leaves out.

A FAIL is a profile that does not get what its file asks for. A WARN is for a correct file that is probably not what you meant: a list that replaces a default, a task allowlist that drops `explore`. A note is for a choice the reader should know about and the author may have made on purpose: a tool table that leaves a list to the `config.toml` Vibe reads, or, under Vibe 3, the `safety` label that Vibe ignores in every primary agent's file. If a WARN fires on a file that is right, the rule is wrong. That already happened once here: the bash allowlist warning had to learn that `permission = "never"` inverts its meaning, because with `never` the allowlist is the whole permitted surface rather than a widening of the default.

## What the tools own

| File | Owns |
|---|---|
| `tools/verify.py` | the rules, the live load, the verdict |
| `tools/selftest.py` | the cases, the reading of `verify.py` for a line with no case, and the repository itself: clean under 2.5.0, and under Vibe 3 exactly the findings recorded in `docs/vibe-3-status.json` |
| `tools/manifest.py` | `MANIFEST.json` and the README tables between their markers, the Vibe 3 one from `docs/vibe-3-status.json` |

Do not hand edit `MANIFEST.json`, and do not hand edit the README between any pair of `<!-- ...:start -->` and `<!-- ...:end -->` markers: the two tables of profiles, the Vibe 3 table and the counts. The Vibe 3 table is written from `docs/vibe-3-status.json`, whose per-profile lines ARE written by hand: change a line there, then run `manifest.py`. The tables are filled between markers rather than by substituting placeholder tokens, because a placeholder is consumed on the first run and the second run writes the literal token into the page.

## House rules the profiles keep

Three of these are not style preferences, and a pull request that breaks one will be asked to change.

- **Nothing here is a safety authorisation.** No profile, and nothing an agent running under one produces, approves a permit to work, an isolation, a confined space entry, a job safety analysis, an incident classification or an inspection sign-off. AI prepares, a qualified human decides.
- **A subagent reports, it does not rule.** The four system prompts in `.vibe/prompts` all end with a version of the same line: the output is a draft for a reviewer, and it never says approved, ready or safe.
- **Missing information is named.** Every prompt has a section for what it could not establish, and an empty one is treated as suspicious rather than clean.
- **No em dashes**, in profiles, prompts, documentation or code comments. `verify.py` fails a profile that contains one.

## Versions

The profiles are written for one version, and the badge, the README and `MANIFEST.json` all say which. When Vibe changes, the honest move is to re-run the probes, not to assume the behaviour survived. The profiles were measured on one later release, 3.1.4, in sessions and by asking its own code, and the result is the section On Vibe 3 of the README: the number did not move, because the profiles do not pass there. The interesting facts in this repository are implementation details: what the loader catches, which defaults are lists, which validators run at load. None of them are contractual.

## Licence

Contributions are accepted under CC BY-SA 4.0, the licence this repository ships under.
