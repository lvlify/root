# Benchmarks

These checks measure a fixed task set. They do not prove that root improves
all tasks, models, or agents. The skill was not changed during the evaluation.

## Reproduce

Use Linux, Python 3.9 or later, and a signed-in Codex CLI. This run used
Codex 0.160.0, Python 3.14.7, and Node.js 26.10.0.

```sh
codex login
python3 benchmarks/run.py --self-check
python3 benchmarks/run.py --output /tmp/root-new-run.jsonl --trials 3 --workers 4
```

The runner uses **`gpt-6-luna` at `max` reasoning effort**.
It makes 144 fresh sessions and 156 model turns. It uses your Codex subscription;
usage limits apply. A run takes about 10–30 minutes, subject to service latency.
It does not read or publish your sign-in credentials. It uses a temporary link
to the existing Codex sign-in file.

To recalculate scores from saved responses, without more model calls:

```sh
python3 benchmarks/run.py --summarize benchmarks/gpt-6-luna-max.jsonl
```

For the plugin startup check, first review this checkout's hook code. This
command bypasses hook trust only inside temporary automation sessions. It does
not change trust in your usual Codex installation. It makes three model calls.

```sh
python3 benchmarks/run.py --loading-check /tmp/root-loading.json
```

For installers, hook output contracts, and package contents:

```sh
python3 check.py
```

[The loading result](loading.json) confirms one canonical body before any model
output in each fresh Codex plugin session. Other host clients were not tested
live. Cross-platform CI did not run. Windows and macOS remain unverified.

## Method

[The tasks](tasks.json) contain 24 cases, with four in each group: cause tracing,
quantitative decisions, hard constraints, uncertainty, Python code, and direct
answers or session retention. Each condition runs each case three times.
The seeded schedule mixes both conditions. The seed controls order, not model
sampling. Each session has a separate temporary workspace and `CODEX_HOME`.

The baseline uses the native Codex instructions. The root condition adds the
unchanged canonical skill body to project `AGENTS.md`. Both conditions retain
the same native host instructions. User config, other skill catalogs, plugins,
apps, memories, web search, and shell execution are disabled. The model writes
answers and code; it does not run commands or edit a project.

Saved session records confirm the exact model and effort on every turn.
They also confirm no root body in baseline context, and one body in root context.
Two cases resume the same session for a second turn. Their usage counters are
cumulative; the runner subtracts the first turn to avoid counting it twice.

The primary score is **fully correct sessions**, including the required JSON
fields and labels. Numerical answers allow relative error `1e-3` or absolute
error `1e-6`. Extra fields fail direct-answer cases. Code must pass every
published edge case and 100 seeded cases per function, without changing inputs.
The four functions have 105, 107, 104, and 105 checks. Code runs in a restricted
Python child process with time and memory limits. Imports and unsafe attributes
are blocked. This evaluator is not a general-purpose security sandbox.

There is no model judge. These checks score fields and program behavior; they do
not score the quality of free-form explanations. Errors and timeouts count as
failures. The runner does not retry or discard responses.

The summary reports wins, losses, and ties for paired sessions. Its 95% interval
resamples all trials together by task, with 10,000 seeded samples. It describes
variation in these authored cases. It is not a guarantee about unknown tasks.
Latency is wall time with four benchmark workers. Auxiliary plugin checks briefly
overlapped collection. Cache use is recorded.
Output tokens include the reported reasoning tokens; do not add them again.
Neither latency nor subscription tokens are a direct API bill.

## Evidence and limits

The JSONL file keeps model answers, CLI events, token counters, initial grades,
context checks, schedule, and source hashes. The summary contains corrected
grades and the full list of changed grades. User IDs and sign-in data are omitted.
Codex warned that `skip_host_skill_discovery` is experimental. Temporary plugin
checks also warned that helper aliases could not be created under `/tmp`.
Neither warning blocked the run. The evidence retains these warnings.

The first grader rejected ordinary rounding and omitted Python's `divmod` and `type` from
its allowed built-ins. Both were evaluator errors. The corrected rules apply
to every saved response in both conditions. Original grades remain in the raw
file. No prompt, response, or skill was changed to improve a score. The collection
runner hash therefore differs from the corrected scoring runner hash.

This is a small, newly authored suite, not an external standard benchmark.
Two tasks were also used for an operational pilot before collection. Scores
can have a ceiling on easy cases. Three trials do not establish statistical
power for small gains. No conclusion covers tool-using coding work, long
sessions, compaction, live worker startup, other models, or other host clients.

[OpenAI's evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
explains why fixed criteria, reproducible checks, and task coverage matter.
[The model reference](https://developers.openai.com/api/docs/models/gpt-6-luna)
lists the supported reasoning settings.
