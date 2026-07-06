"""Security · Dependency Security & secret hygiene (MASTER_PLAN §25.9.5).

`pip-audit` and `bandit` run as CI jobs (asserted below). These tests guard the
static invariants those scans assume: dependencies are pinned exactly, secrets are
git-ignored, and no real `.env` is committed.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _pyproject() -> dict[str, object]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)


def test_runtime_dependencies_pinned_exactly() -> None:
    project = _pyproject()["project"]
    assert isinstance(project, dict)
    deps = project["dependencies"]
    assert isinstance(deps, list)
    assert deps, "expected pinned runtime dependencies"
    for dep in deps:
        assert isinstance(dep, str)
        # Section 6.4: exact pins only. Reject ranges / compatible-release operators.
        assert "==" in dep, f"dependency not exactly pinned: {dep!r}"
        for loose in (">=", "<=", "~=", ">", "<", "*"):
            assert loose not in dep.split("==", 1)[1], f"loose specifier in {dep!r}"


def test_env_is_gitignored() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    rules = {line.strip() for line in gitignore}
    assert ".env" in rules
    # The example template is explicitly NOT ignored (operators copy it).
    assert "!.env.example" in rules


def test_no_real_env_committed() -> None:
    # A local untracked .env is fine (and gitignored); a *committed* one is not.
    # Only the placeholder-only templates may be tracked: `.env.example` and
    # `.env.production.example` (Sprint 12 A2 — both carry sentinels, never secrets).
    allowed = {".env.example", ".env.production.example"}
    git = shutil.which("git")
    if git is None:  # pragma: no cover - git always present in CI / dev
        pytest.skip("git not available")
    result = subprocess.run(  # noqa: S603 - fixed args, no shell, tests excluded from bandit
        [git, "ls-files", ".env", ".env.*"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    assert tracked <= allowed, f"unexpected tracked env files: {tracked - allowed}"
    assert (REPO_ROOT / ".env.example").exists()


def test_pip_audit_and_bandit_wired_in_ci() -> None:
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pip-audit" in ci, "pip-audit must run as a CI gate (§25.9.5)"
    assert "bandit" in ci, "bandit must run as a CI gate (§25.9.5)"
