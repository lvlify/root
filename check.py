"""Check portable installation in temporary folders: python3 check.py."""

import importlib.util
import json
import os
from pathlib import Path
import stat
import shutil
import subprocess
import sys
import tempfile
import zipfile
from unittest.mock import patch

import package as packaging


def command(*args, expected=0, program=None):
    result = subprocess.run([sys.executable, str(program or script), *map(str, args)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == expected, (args, result.returncode, result.stdout, result.stderr)
    return result


with tempfile.TemporaryDirectory(prefix="root-check-") as directory:
    sandbox = Path(directory)
    product = sandbox / "product"
    product.mkdir()
    script = product / "install.py"
    checkout = Path(__file__).resolve().parent
    generated = packaging.generated()
    for name, data in generated.items():
        assert (checkout / name).read_bytes() == data, f"Stale generated file: {name}"
    names = set(packaging.COMMON) | set(generated) | {"package.py", packaging.MANIFEST}
    names.update(name for files in packaging.FORMATS.values() for name in files)
    for name in names:
        destination = product / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(checkout / name, destination)
    spec = importlib.util.spec_from_file_location("root_install", script)
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    for agent in installer.PROJECT_FILES:
        project = sandbox / agent
        project.mkdir()
        destination = installer.target(agent, project)
        destination.parent.mkdir(parents=True, exist_ok=True)
        original = b"" if agent == "cursor" else "# Existing\r\nKeep this: λ.\r\n".encode()
        if agent != "cursor":
            destination.write_bytes(original)
            destination.chmod(0o640)
        command("install", agent, "--project", project, "--dry-run")
        assert destination.exists() == (agent != "cursor")
        if destination.exists():
            assert destination.read_bytes() == original
        command("install", agent, "--project", project)
        installed = destination.read_bytes()
        assert installed.count(installer.BEGIN) == 1
        assert installer.body() in installed.replace(b"\r\n", b"\n")
        command("status", agent, "--project", project)
        command("install", agent, "--project", project)
        assert destination.read_bytes() == installed
        stale = installed.replace(b"# root", b"# Old root", 1)
        destination.write_bytes(stale)
        command("status", agent, "--project", project, expected=1)
        command("install", agent, "--project", project)
        assert destination.read_bytes() == installed
        if agent != "cursor":
            backup = destination.with_name(destination.name + ".root-backup")
            assert backup.read_bytes() == original
            if os.name != "nt":  # Windows permissions do not use POSIX mode bits.
                assert stat.S_IMODE(backup.stat().st_mode) == 0o600
                assert stat.S_IMODE(destination.stat().st_mode) == 0o640
        manual = b"\n# Added later\nKeep this too.\n"
        destination.write_bytes(installed + manual)
        command("install", agent, "--project", project)
        assert destination.read_bytes() == installed + manual
        command("uninstall", agent, "--project", project)
        remainder = destination.read_bytes()
        expected = original + manual
        if agent == "cursor":
            expected = installer.CURSOR_HEADER.rstrip(b"\n") + manual
        assert remainder == expected, (agent, remainder, expected)
        command("status", agent, "--project", project, expected=1)
        command("uninstall", agent, "--project", project)
        assert destination.read_bytes() == expected
        print(f"PASS {agent}: preview, install, status, repeat, preserve, remove")

    for agent in installer.PROJECT_FILES:
        project = sandbox / (agent + "-empty")
        project.mkdir()
        destination = installer.target(agent, project)
        command("install", agent, "--project", project)
        command("uninstall", agent, "--project", project)
        assert not destination.exists()

    mixed = sandbox / "mixed.md"
    original = b"Existing text.\n"
    installed = installer.render(original, mixed, "codex") + b"\r\nLater CRLF text.\r\n"
    installed = installer.render(installed, mixed, "codex")
    assert installer.render(installed, mixed, "codex", True) == original + b"\r\nLater CRLF text.\r\n"

    virtual_home = sandbox / "user"
    with patch.object(Path, "home", return_value=virtual_home), patch.dict(os.environ, {}, clear=True):
        expected = {
            "claude": ".claude/CLAUDE.md", "codex": ".codex/AGENTS.md",
            "opencode": ".config/opencode/AGENTS.md", "copilot": ".copilot/copilot-instructions.md",
            "antigravity": ".gemini/GEMINI.md", "gemini": ".gemini/GEMINI.md",
        }
        for agent, relative in expected.items():
            destination = installer.target(agent, None)
            assert destination == virtual_home / relative
            original, existed = installer.read(destination)
            installed = installer.render(original, destination, agent)
            installer.write(destination, original, existed, installed)
            assert installer.render(installed, destination, agent) == installed
        try:
            installer.target("cursor", None)
            raise AssertionError("Cursor global file installation must be refused")
        except ValueError:
            pass

    project = sandbox / "override"
    project.mkdir()
    base = project / "AGENTS.md"
    override = project / "AGENTS.override.md"
    base.write_text("Base stays intact.\n")
    override.write_text("Active override.\n")
    command("install", "codex", "--project", project)
    assert installer.BEGIN in override.read_bytes() and installer.BEGIN not in base.read_bytes()

    bad = sandbox / "invalid"
    bad.mkdir()
    destination = bad / "AGENTS.md"
    for invalid in (installer.BEGIN, installer.END, installer.END + b"\n" + installer.BEGIN,
                    installer.BEGIN + b"junk\n" + installer.END,
                    installer.BEGIN + b"\ntext " + installer.END, b"\xff"):
        destination.write_bytes(invalid)
        command("install", "codex", "--project", bad, expected=2)
        assert destination.read_bytes() == invalid
    destination.unlink()
    real = bad / "real.md"
    real.write_text("Do not touch.\n")
    try:
        destination.symlink_to(real)
    except OSError:
        print("SKIP symbolic link check: this platform does not permit creation")
    else:
        command("install", "codex", "--project", bad, expected=2)
        assert real.read_text() == "Do not touch.\n"

    raced = sandbox / "race.md"
    raced.write_bytes(b"Edited elsewhere.")
    try:
        installer.write(raced, b"Earlier content.", True, b"Replacement")
        raise AssertionError("Concurrent change must be refused")
    except ValueError:
        assert raced.read_bytes() == b"Edited elsewhere."
    assert not list(sandbox.glob(".root-*"))

    failed = sandbox / "backup-failure.md"
    failed.write_bytes(b"Keep the original.")
    backup = failed.with_name(failed.name + ".root-backup")
    with patch.object(installer.os, "fsync", side_effect=OSError("backup write failed")):
        try:
            installer.write(failed, failed.read_bytes(), True, b"Replacement")
            raise AssertionError("A failed backup must stop installation")
        except OSError:
            assert failed.read_bytes() == b"Keep the original."
            assert not backup.exists()
    backup.mkdir()
    try:
        installer.write(failed, failed.read_bytes(), True, b"Replacement")
        raise AssertionError("A foreign backup directory must be refused")
    except ValueError:
        assert failed.read_bytes() == b"Keep the original."

    project = sandbox / "cursor-conflict"
    project.mkdir()
    destination = installer.target("cursor", project)
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"User's existing rule.\n")
    command("install", "cursor", "--project", project, expected=2)
    command("status", "cursor", "--project", project, expected=1)
    command("uninstall", "cursor", "--project", project)
    assert destination.read_bytes() == b"User's existing rule.\n"

    assert command("print").stdout.encode() == installer.body() + b"\n"
    command("install", "codex", expected=2)
    command("print", "codex", expected=2)
    command("install", "cursor", "--global", expected=2)

    packager = product / "package.py"
    command("--check", program=packager)
    for format_name, extra in packaging.FORMATS.items():
        archive_path = sandbox / (format_name + ".zip")
        command("--format", format_name, "--output", archive_path, program=packager)
        with zipfile.ZipFile(archive_path) as archive:
            assert set(archive.namelist()) == {"root/" + name for name in packaging.COMMON + extra}
            assert archive.read("root/skills/root/SKILL.md") == installer.SOURCE.read_bytes()
            if format_name == "cursor":
                assert "root/plugin.json" not in archive.namelist()
                assert installer.body() in archive.read("root/rules/root.mdc")
            consumer = sandbox / (format_name + "-consumer")
            archive.extractall(consumer)
        assert command("print", program=consumer / "root/install.py").stdout.encode() == installer.body() + b"\n"
        original = archive_path.read_bytes()
        command("--output", archive_path, program=packager, expected=2)
        assert archive_path.read_bytes() == original

    manifest = product / "hooks/codex.json"
    current = manifest.read_bytes()
    manifest.write_bytes(current + b"\n")
    command("--check", program=packager, expected=1)
    command("--sync", program=packager)
    assert manifest.read_bytes() == current

    node = shutil.which("node")
    if node:
        hook = product / "hooks/context.cjs"
        for event in ("SessionStart", "SubagentStart", "copilot"):
            result = subprocess.run([node, str(hook), event], capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stderr
            context = installer.body().decode()
            expected = ({"additionalContext": context} if event == "copilot" else
                        {"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}})
            assert json.loads(result.stdout) == expected
        module_url = (product / "hooks/opencode.mjs").as_uri()
        probe = ("const plugin=(await import(" + json.dumps(module_url) + ")).default;"
                 "const hooks=await plugin.server();const output={system:[]};"
                 "await hooks['experimental.chat.system.transform']({},output);"
                 "await hooks['experimental.chat.system.transform']({},output);"
                 "process.stdout.write(JSON.stringify(output.system));")
        result = subprocess.run([node, "--input-type=module", "-e", probe],
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == [installer.body().decode()]
        print("PASS shared hook output and one OpenCode context copy")
    else:
        print("SKIP hooks and OpenCode adapter: Node is unavailable")

    canonical = installer.SOURCE.read_bytes()
    installer.SOURCE.write_bytes(canonical + b"x" * 8193)
    command("print", expected=2)
    if node:
        result = subprocess.run([node, str(hook), "SessionStart"],
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 2 and not result.stdout
    installer.SOURCE.write_bytes(canonical)
print("PASS safety, global paths, overrides, empty removal, and export")
print("PASS generated metadata, six clean archives, stale detection, and context cap")
print("Native client loading and model behavior are not tested by this check.")
