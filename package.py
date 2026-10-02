#!/usr/bin/env python3
"""Generate host metadata and clean plugin archives. Python 3.9+, no packages."""

import argparse
import json
from pathlib import Path
import re
import sys
import zipfile

import install


ROOT = Path(__file__).resolve().parent
COMMON = ("README.md", "LICENSE", "install.py", "skills/root/SKILL.md",
          "skills/root/agents/openai.yaml")
FORMATS = {
    "agent": ("plugin.json", "hooks/codex.json", "hooks/context.cjs",
              "com.github.copilot/hooks/hooks.json"),
    "claude": (".claude-plugin/plugin.json", "hooks/claude.json", "hooks/context.cjs"),
    "cursor": (".cursor-plugin/plugin.json", "rules/root.mdc"),
    "copilot": ("plugin.json", "com.github.copilot/hooks/hooks.json", "hooks/context.cjs",
                "hooks/codex.json"),
    "gemini": ("gemini-extension.json",),
    "opencode": ("package.json", "hooks/opencode.mjs", "hooks/context.cjs"),
}


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def launcher(event):
    # Resolve paths inside Node so the shell never interprets an installed path.
    return ("node -e \"require(require('node:path').join(process.env.PLUGIN_ROOT || "
            "process.env.COPILOT_PLUGIN_ROOT || process.env.CLAUDE_PLUGIN_ROOT, "
            f"'hooks', 'context.cjs')).emit('{event}')\"")


def generated():
    manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    if (manifest.get("name") != "root"
            or not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", manifest["version"])):
        raise ValueError("plugin.json: expected root and a three-part release version")
    identity = {key: manifest[key] for key in
                ("name", "version", "description", "author", "homepage", "repository", "license")}
    claude = {**identity, "hooks": "./hooks/claude.json"}
    claude_hooks = {}
    codex_hooks = {}
    for event in ("SessionStart", "SubagentStart"):
        claude_hooks[event] = [{"hooks": [{
            "type": "command", "command": "node",
            "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/context.cjs", event], "timeout": 5,
        }]}]
        codex_hooks[event] = [{"hooks": [{
            "type": "command", "command": launcher(event), "timeout": 5,
            "additionalContextLimit": 0,  # The hook enforces an 8 KiB body cap.
        }]}]
    copilot_hooks = {event: [{"type": "command", "bash": launcher("copilot"),
                             "powershell": launcher("copilot"), "timeoutSec": 5}]
                     for event in ("sessionStart", "subagentStart")}
    data = {
        ".claude-plugin/plugin.json": claude,
        ".claude-plugin/marketplace.json": {
            "name": "root", "owner": manifest["author"],
            "plugins": [{"name": "root", "source": "./", "description": manifest["description"]}],
        },
        ".agents/plugins/marketplace.json": {
            "name": "root", "plugins": [{"name": "root",
                "source": {"source": "local", "path": "./"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Productivity"}],
        },
        ".cursor-plugin/plugin.json": {**identity, "skills": "./skills/", "rules": "./rules/"},
        "gemini-extension.json": {"name": "root", "version": manifest["version"],
                                  "contextFileName": "skills/root/SKILL.md"},
        "hooks/claude.json": {"hooks": claude_hooks},
        "hooks/codex.json": {"hooks": codex_hooks},
        "com.github.copilot/hooks/hooks.json": {"version": 1, "hooks": copilot_hooks},
        "package.json": {
            "name": "@lvlify/root", "version": manifest["version"],
            "description": manifest["description"], "type": "module",
            "main": "./hooks/opencode.mjs",
            "exports": {".": "./hooks/opencode.mjs", "./server": "./hooks/opencode.mjs"},
            "files": ["skills/", "hooks/context.cjs", "hooks/opencode.mjs", "LICENSE", "README.md"],
            "repository": {"type": "git", "url": manifest["repository"] + ".git"},
            "license": manifest["license"], "engines": {"node": ">=22"},
        },
    }
    result = {name: encoded(value) for name, value in data.items()}
    result["rules/root.mdc"] = install.render(b"", ROOT / "rules/root.mdc", "cursor")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", action="store_true", help="refresh generated files in this checkout")
    parser.add_argument("--check", action="store_true", help="report stale generated files without writing")
    parser.add_argument("--format", choices=tuple(FORMATS), default="agent")
    parser.add_argument("--output", type=Path, help="write a new ZIP containing a root/ plugin directory")
    args = parser.parse_args()
    if not (args.sync or args.check or args.output):
        parser.error("choose --sync, --check, or --output PATH")
    if args.sync and args.check:
        parser.error("--sync and --check are mutually exclusive")
    files = generated()
    if args.check:
        stale = [name for name, data in files.items()
                 if not (ROOT / name).is_file() or (ROOT / name).read_bytes() != data]
        if stale:
            print("Stale generated files: " + ", ".join(stale), file=sys.stderr)
            return 1
        print("Generated files match the canonical skill and plugin manifest.")
    if args.sync:
        for name, data in files.items():
            destination = ROOT / name
            if destination.is_symlink():
                raise ValueError(f"{destination}: symbolic link; refusing to generate over it")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists() or destination.read_bytes() != data:
                destination.write_bytes(data)
        print("Generated host files from plugin.json and skills/root/SKILL.md.")
    if args.output:
        output = args.output.expanduser().absolute()
        names = COMMON + FORMATS[args.format]
        payload = {}
        for name in names:
            path = ROOT / name
            if name in files:
                payload[name] = files[name]
            else:
                if path.is_symlink():
                    raise ValueError(f"{path}: symbolic link; refusing to package it")
                payload[name] = path.read_bytes()
        output.parent.mkdir(parents=True, exist_ok=True)
        stream = output.open("xb")
        try:
            with stream, zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in sorted(payload.items()):
                    archive.writestr("root/" + name, data)
        except BaseException:
            output.unlink()
            raise
        print(f"Packaged {args.format}: {output}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, UnicodeError, ValueError, KeyError) as error:
        print(f"root: {error}", file=sys.stderr)
        sys.exit(2)
