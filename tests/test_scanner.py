import subprocess
from pathlib import Path

from cointent.scanner import scan_repository, snapshot_diff


def run(root: Path, *args: str) -> None:
    subprocess.run(args, cwd=root, check=True, capture_output=True)


def test_scanner_is_tracked_only_and_finds_package_dependencies(tmp_path: Path) -> None:
    run(tmp_path, "git", "init", "-q")
    run(tmp_path, "git", "config", "user.email", "test@example.com")
    run(tmp_path, "git", "config", "user.name", "Test")
    (tmp_path / "src/a").mkdir(parents=True)
    (tmp_path / "src/b").mkdir(parents=True)
    (tmp_path / "src/a/main.py").write_text("from b import value\n", encoding="utf-8")
    (tmp_path / "src/b/__init__.py").write_text("value = 1\n", encoding="utf-8")
    run(tmp_path, "git", "add", ".")
    run(tmp_path, "git", "commit", "-qm", "initial")
    (tmp_path / "untracked.secret").write_text("do not scan", encoding="utf-8")

    first = scan_repository(tmp_path, "demo")
    assert "untracked.secret" not in {item.path for item in first.artifacts}
    assert any(item.source == "src/a/main.py" and item.target == "src/b/__init__.py" for item in first.relations)

    (tmp_path / "src/b/__init__.py").write_text("value = 2\n", encoding="utf-8")
    second = scan_repository(tmp_path, "demo")
    assert snapshot_diff(first, second)["modified"] == ["src/b/__init__.py"]
