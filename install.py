#!/usr/bin/env python3
"""Install root in native instruction files. Python 3.9+, standard library only."""

import argparse
import os
from pathlib import Path
import re
import stat
import sys
import tempfile


SOURCE = Path(__file__).resolve().parent / "skills" / "root" / "SKILL.md"
BEGIN = b"<!-- root:begin -->"
END = b"<!-- root:end -->"
CURSOR_HEADER = b"---\ndescription: root reasoning guidance\nalwaysApply: true\n---\n\n"
PROJECT_FILES = {
    "claude": "CLAUDE.md",
    "codex": "AGENTS.md",
    "cursor": ".cursor/rules/root.mdc",
    "opencode": "AGENTS.md",
    "copilot": ".github/copilot-instructions.md",
    "antigravity": "GEMINI.md",
    "gemini": "GEMINI.md",
}


def body():
    text = SOURCE.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"{SOURCE}: missing skill frontmatter")
    metadata, content = text[4:].split("\n---\n", 1)
    if not re.search(r"^name: root$", metadata, re.MULTILINE) or not content.strip():
        raise ValueError(f"{SOURCE}: expected a nonempty root skill")
    result = content.strip().encode("utf-8")
    if len(result) > 8192:
        raise ValueError(f"{SOURCE}: root body exceeds the 8 KiB context limit")
    return result


def config_dir(variable, default):
    value = os.environ.get(variable)
    return Path(value).expanduser().absolute() if value else default


def target(agent, project):
    if project is not None:
        base = project.expanduser().absolute()
        if not base.is_dir():
            raise ValueError(f"{base}: project directory does not exist")
        path = base / PROJECT_FILES[agent]
    else:
        home = Path.home()
        paths = {
            "claude": config_dir("CLAUDE_CONFIG_DIR", home / ".claude") / "CLAUDE.md",
            "codex": config_dir("CODEX_HOME", home / ".codex") / "AGENTS.md",
            "opencode": config_dir("XDG_CONFIG_HOME", home / ".config") / "opencode" / "AGENTS.md",
            "copilot": config_dir("COPILOT_HOME", home / ".copilot") / "copilot-instructions.md",
            "antigravity": home / ".gemini" / "GEMINI.md",
            "gemini": home / ".gemini" / "GEMINI.md",
        }
        if agent == "cursor":
            raise ValueError("Cursor global rules use its UI. Run 'print' and paste into Customize > Rules > User Rules, or use --project PATH.")
        path = paths[agent]
    if agent == "codex":
        override = path.with_name("AGENTS.override.md")
        if override.is_file() and override.stat().st_size:
            path = override
    return path


def read(path):
    if path.is_symlink():
        raise ValueError(f"{path}: symbolic link; edit the intended file manually")
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return b"", False
    data.decode("utf-8")  # Refuse binary or non-UTF-8 instruction files.
    return data, True


def span(data, path):
    if BEGIN not in data and END not in data:
        return None
    if data.count(BEGIN) != 1 or data.count(END) != 1:
        raise ValueError(f"{path}: invalid or duplicate root markers; repair them before installing")
    start = data.index(BEGIN)
    end = data.index(END) + len(END)
    begin_tail = data[start + len(BEGIN):]
    end_start = data.index(END)
    if (start > end or (start and data[start - 1:start] != b"\n")
            or not begin_tail.startswith((b"\n", b"\r\n"))
            or data[end_start - 1:end_start] != b"\n"):
        raise ValueError(f"{path}: misplaced root markers; repair them before installing")
    tail = data[end:]
    if tail and not tail.startswith((b"\n", b"\r\n")):
        raise ValueError(f"{path}: root end marker must be on its own line")
    if tail.startswith(b"\r\n"):
        end += 2
    elif tail.startswith(b"\n"):
        end += 1
    return start, end


def render(data, path, agent, remove=False):
    bounds = span(data, path)
    if remove and bounds is None:
        return data
    if agent == "cursor" and data:
        # This dedicated rule must remain always applied. Keep other text intact.
        if not data.replace(b"\r\n", b"\n").startswith(CURSOR_HEADER) or bounds is None:
            raise ValueError(f"{path}: existing rule is not managed by root; move it or use another rule name")
    if bounds and remove:
        start, end = bounds
        # The installer owns two separator newlines, even after line-ending edits.
        for separator in (b"\r\n\r\n", b"\n\n"):
            if data[:start].endswith(separator):
                start -= len(separator)
                break
        result = data[:start] + data[end:]
        if agent == "cursor" and result.replace(b"\r\n", b"\n") == CURSOR_HEADER.rstrip(b"\n"):
            return b""
        return result
    newline = b"\r\n" if b"\r\n" in data else b"\n"
    block = BEGIN + newline + body().replace(b"\n", newline) + newline + END + newline
    if bounds:
        start, end = bounds
        return data[:start] + block + data[end:]
    if agent == "cursor":
        return CURSOR_HEADER + block
    return data + (newline * 2 if data else b"") + block


def write(path, original, existed, updated):
    """Keep the first original snapshot and replace the file in one operation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + ".root-backup")
    if existed:
        try:
            descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if backup.is_symlink() or not backup.is_file():
                raise ValueError(f"{backup}: backup is not a regular file; move it before retrying")
            pass  # Never replace the initial snapshot, even on an update.
        else:
            try:
                with os.fdopen(descriptor, "wb") as saved:
                    saved.write(original)
                    saved.flush()
                    os.fsync(saved.fileno())
            except BaseException:
                backup.unlink()
                raise
    mode = stat.S_IMODE(path.stat().st_mode) if existed else 0o600
    descriptor, temporary = tempfile.mkstemp(prefix=".root-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(updated)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        current, present = read(path)
        # ponytail: detects edits before replacement; close other editors during install.
        if current != original or present != existed:
            raise ValueError(f"{path}: changed during install; retry after the other editor finishes")
        if updated:
            os.replace(temporary, path)
        elif existed:
            path.unlink()
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "uninstall", "status", "print"))
    parser.add_argument("agent", nargs="?", choices=tuple(PROJECT_FILES))
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--global", dest="global_scope", action="store_true", help="all projects for this user")
    scope.add_argument("--project", type=Path, metavar="PATH", help="an existing project root")
    parser.add_argument("--dry-run", action="store_true", help="show the target without writing")
    args = parser.parse_args()
    if args.action == "print":
        if args.agent or args.global_scope or args.project is not None or args.dry_run:
            parser.error("print takes no agent or options")
        sys.stdout.buffer.write(body() + b"\n")
        return 0
    if args.agent is None or not (args.global_scope or args.project is not None):
        parser.error("choose an agent and either --global or --project PATH")
    path = target(args.agent, args.project)
    original, existed = read(path)
    if args.action == "status":
        current = (existed and span(original, path) is not None
                   and render(original, path, args.agent) == original)
        print(f"{'Current' if current else 'Missing or outdated'}: {path}")
        print("This checks the file. Confirm loading in a new agent session.")
        return 0 if current else 1
    updated = render(original, path, args.agent, args.action == "uninstall")
    if original == updated:
        print(f"Unchanged: {path}")
    elif args.dry_run:
        print(f"Would {'remove' if args.action == 'uninstall' else 'install'} root: {path}")
    else:
        write(path, original, existed, updated)
        print(f"{'Removed' if args.action == 'uninstall' else 'Installed'} root: {path}")
        if existed:
            print(f"Initial backup: {path.name}.root-backup")
    if not args.dry_run:
        print("Start a new agent session for the change to take effect.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, UnicodeError, ValueError) as error:
        print(f"root: {error}", file=sys.stderr)
        sys.exit(2)
