# root

**Trace causes. Choose what the evidence supports.**

Root is a small reasoning skill for agents and models. It guides the agent to
trace important causes, compare credible approaches, and challenge its choice.
The goal and constraints determine the strongest answer. Simple tasks stay direct.

Root applies across coding, research, planning, design, and other domains.
It preserves uncertainty. It adds no fixed output style, required model, or service.

## Install

Choose **one loading path per host**: native instructions or a plugin.
Both use [the same skill](skills/root/SKILL.md). Neither needs a manual invocation
for each session after setup. Start a new session after installation.

### Native instructions

```sh
git clone https://github.com/lvlify/root.git
cd root
```

Use Python 3.9 or later. No packages are required.
On Windows, replace `python3` with `py -3`.
Replace `/path/to/project` with an existing project.

| Environment | Install |
| --- | --- |
| Claude Code | `python3 install.py install claude --global` |
| Codex | `python3 install.py install codex --global` |
| Cursor | `python3 install.py install cursor --project /path/to/project` |
| OpenCode | `python3 install.py install opencode --global` |
| GitHub Copilot | `python3 install.py install copilot --project /path/to/project` |
| Antigravity | `python3 install.py install antigravity --global` |
| Gemini CLI | `python3 install.py install gemini --global` |

Use `--project /path/to/project` with any agent for project scope.
Codex and OpenCode share project `AGENTS.md`. Antigravity and Gemini share
`GEMINI.md`, including their global file. Installing into a shared file twice
keeps one root block. Removing that block affects both readers.

For **Cursor across projects**, run `python3 install.py print` and paste the output
into **Customize > Rules > User Rules**. These rules apply to Agent Chat;
they do not configure Tab or Inline Edit.

For **Copilot CLI across projects**, use `python3 install.py install copilot --global`.
This configures the CLI only. For an IDE or repository session, use project scope
and enable repository instructions in the client. Feature support varies.

The installer respects `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, `XDG_CONFIG_HOME` for
OpenCode, and `COPILOT_HOME`. It selects a nonempty Codex `AGENTS.override.md`
when present. Install on the machine where the agent runs. Custom context
filenames and managed policies can change which file loads. Keep `GEMINI.md`
enabled in Gemini's `context.fileName`, or export root into the file you use.

### Plugins and packages

Hook plugins need **Node.js 22 or later on `PATH`**. They use built-in modules only.
Gemini context and Cursor rules need no hook process.

**Claude Code**

```sh
claude plugin marketplace add lvlify/root
claude plugin install root@root
```

**Codex**

```sh
codex plugin marketplace add lvlify/root
```

Open `/plugins` and install `root` from the `root` marketplace.
Open `/hooks` and review and trust root's hooks. Enabled plugins do not run
untrusted hooks. Local command hooks do not run under cloud orchestration.
Root uses `.codex-plugin/plugin.json` because Codex CLI 0.160.0 skips hooks
in portable Agent Plugins packages. Its plugin details should list
`SessionStart (1), SubagentStart (1)`.
[Codex packaging](https://developers.openai.com/plugins/build/plugins),
[hook trust and execution](https://learn.chatgpt.com/docs/hooks).

**Gemini CLI**

```sh
gemini extensions install https://github.com/lvlify/root
```

The extension loads the canonical skill as context.
[Gemini extensions](https://geminicli.com/docs/extensions/reference/).

**Copilot CLI**

```sh
copilot plugin install lvlify/root
```

This plugin's context output targets Copilot CLI and Copilot Agent Host.
Use native repository instructions for VS Code Local sessions. The CLI's
built-in `general-purpose` agent does not emit subagent startup hooks.
[Copilot plugins](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference),
[hook limits](https://docs.github.com/en/copilot/reference/hooks-reference).

**Cursor**

Build the native Cursor package from this checkout:

```sh
python3 package.py --format cursor --output /tmp/root-cursor.zip
```

On Windows, choose a ZIP path outside the checkout.
Extract the archive's `root/` folder into `~/.cursor/plugins/local/`.
Reload Cursor. Confirm root's rule is **Always Apply** in Customize.
This package contains Cursor's native manifest and always applied rule.
Local plugin imports must be allowed by your organization.
[Cursor plugin formats and installation](https://cursor.com/docs/plugins).

**OpenCode**

Native `AGENTS.md` is the default path. For plugin use, add this entry to the
`plugin` array in your OpenCode configuration. Use an absolute file URL:

```json
{"plugin": ["file:///absolute/path/to/root/hooks/opencode.mjs"]}
```

Keep existing entries. Restart OpenCode. This adapter uses the current server
plugin API and an experimental system-context hook. For older clients or pure
mode, use native instructions. The npm package form is prepared; no npm release
is claimed. [OpenCode plugins](https://opencode.ai/docs/plugins/).

Antigravity uses its native `GEMINI.md` path. Root does not claim a separate
Antigravity plugin format.

Before switching paths, remove root's native block or disable its plugin.
Do not combine a plugin, global instructions, project rules, and manual skill
invocation for the same session. Hosts can also read another tool's files.
Inspect the loaded context when several agents share a project.

## How it works

Root defines success, traces mechanisms, compares meaningful alternatives,
and checks the strongest objection. It stops when further work has no useful
benefit within the task's limits. It never treats confidence as evidence.

For example, a slow page may suggest a cache. If an upload causes most of the
delay, root directs attention to that path before changing the database.
The solution must still preserve the upload and fit the user's constraints.

Native installation writes the complete body into a startup file or rule.
That text has no runtime dependency on this checkout. Plugins read the same
canonical skill. Claude and Codex hooks supply it before the first model request,
after supported resume or compaction events, and at worker startup. Copilot
uses its supported session and worker events. Cursor uses an always applied rule.
OpenCode supplies one copy when it builds each system prompt. Gemini loads extension context.

The body has an **8 KiB limit**. There are no prompt-by-prompt reminder hooks,
mode flags, accounts, telemetry, network calls, or background services.
Hosts control retention, instruction priority, worker inheritance, and policies.
Root cannot guarantee identical behavior across all clients or session types.

## Confirm loading

For native installation, replace `AGENT` with the ID used in your install command:

```sh
python3 install.py status AGENT --global
```

Use the same scope as installation. `Current` checks the file, not model delivery.
Exit codes are `0` for success, `1` for missing or outdated status, and `2` for an error.
Confirm loading in a fresh session through the client:

| Environment | Native file and loading check |
| --- | --- |
| Claude Code | `~/.claude/CLAUDE.md` or project `CLAUDE.md`; inspect `/memory` or `/context`. [Memory](https://code.claude.com/docs/en/memory). |
| Codex | `~/.codex/AGENTS.md` or project `AGENTS.md`, with override precedence; inspect active files or `/hooks` for plugin mode. [Instructions](https://developers.openai.com/codex/guides/agents-md). |
| Cursor | `.cursor/rules/root.mdc`, plugin rule, or User Rules; confirm **Always Apply**. [Rules](https://cursor.com/docs/rules). |
| OpenCode | Global or project `AGENTS.md`; inspect active rules and plugin configuration. [Rules](https://opencode.ai/docs/rules/). |
| GitHub Copilot | Project `.github/copilot-instructions.md`; inspect Chat references. CLI uses `~/.copilot/copilot-instructions.md` and `/instructions`. [Instructions](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions). |
| Antigravity | `~/.gemini/GEMINI.md` or project `GEMINI.md`; inspect **Customizations > Rules**. [Rules](https://antigravity.google/docs/rules/). |
| Gemini CLI | `~/.gemini/GEMINI.md`, project context, or extension context; inspect `/memory show`. [Context](https://geminicli.com/docs/cli/gemini-md/). |

A client showing loaded instructions is stronger evidence than a model saying
root is active. File limits still apply. For example, Codex defaults to a 32 KiB
combined project instruction limit. Supply `python3 install.py print` to a custom
worker or API session that does not inherit root through its host.

**Verification status:** Paths and plugin contracts were researched from official
documentation on 2026-10-01 and 2026-10-02. Codex CLI 0.160.0's plugin reader
detects both startup hooks in version 0.1.1. The runnable checks have not been
executed. Fresh-session delivery, Windows behavior, and reasoning gains remain unverified.
Root does not claim universal optimality or measured improvement.

## Update or remove

For native installation, run `git pull --ff-only`, review the changes, and repeat
your original install command. It updates only root's marked block.
Use a reviewed commit or release tag when you need a fixed version.

For plugins, use the host's update manager. Claude uses
`claude plugin update root@root`. Codex can refresh the catalog with
`codex plugin marketplace upgrade root`; inspect the plugin and review changed hooks.
Gemini uses `gemini extensions update root`. Copilot uses `copilot plugin update root`.
Replace a local Cursor package or update the OpenCode checkout used by its file URL.
Restart after any update.

To remove native guidance, use the original environment and scope:

```sh
python3 install.py uninstall AGENT --global
```

For Cursor User Rules, remove the pasted text in the UI. For plugins, use the
host's uninstall or disable action. Remove an OpenCode file-URL entry when unused.
A conversation request to pause root does not remove installed guidance;
a new session or compaction can load it again.

The native installer preserves other text. It keeps a first snapshot beside an
existing file as `FILENAME.root-backup`. It never replaces that snapshot or
restores it automatically. Uninstall removes the marked block and an empty owned
file. It keeps directories and your later edits outside the block.
Malformed markers, non-UTF-8 input, symbolic file links, and unmanaged Cursor
rules cause an error. A retained Cursor rule becomes user-owned after removal;
move it to another rule name before reinstalling. Preview with `--dry-run`.
Close other editors during installation. The edit check does not lock other writers.

## Skill use and other models

`skills/root/` follows the Agent Skills format. Copy that folder into a supported
skill directory for explicit skill use. Skill discovery alone does not ensure
startup loading. Use native instructions or a supported plugin for session guidance.

For another harness, run `python3 install.py print`. Add the plain body to its
permitted startup instructions. No particular model or tool is required.

## Maintain and release

Use a Git checkout for this workflow. Clean plugin archives contain runtime files
and the native installer, not the package builder or checks.

Edit `skills/root/SKILL.md` for behavior and `.codex-plugin/plugin.json` for
package identity and version. Host files and the required Cursor rule derive
from these two files.
Do not edit generated files by hand.

```sh
python3 package.py --sync
python3 check.py
```

The one check uses temporary folders. It checks installation, preservation,
removal, exports, generated metadata, and package contents. With Node available,
it also checks hook output and the OpenCode adapter. It does not change your
agent settings or prove live client loading.

GitHub Actions runs this same check on Linux, macOS, and Windows. The workflow
has read-only repository access. It does not publish packages.

Build a clean package with `python3 package.py --format codex --output /tmp/root.zip`.
Formats are `codex`, `claude`, `cursor`, `copilot`, `gemini`, and `opencode`.
The file list is explicit. Archives do not copy unrelated checkout files.
Cursor exports use only the native manifest. Existing archives are not overwritten.
Copilot uses `.plugin/plugin.json` to select its own hook format.
The checkout has no root portable manifest because Codex CLI 0.160.0 would
select it and skip startup hooks. All host manifests use the same skill body.

Before a GitHub release, inspect `git diff --check` and the selected files.
Run the check on Linux, macOS, and Windows before claiming those platforms were tested.
Record host versions and confirm live loading separately. Test reasoning quality
with isolated control runs before claiming a gain. Retain failures and raw evidence.
Publish from the reviewed commit. npm and public plugin directories are separate
publication steps; their manifests do not establish a live listing.

Report problems through [GitHub issues](https://github.com/lvlify/root/issues).

## License

[MIT](LICENSE).
