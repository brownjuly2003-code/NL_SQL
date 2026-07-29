"""No-network tests for the clean-clone-safe HF deploy script."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from scripts import deploy_hf

# ---------------------------------------------------------------------------
# Prefix + hygiene filtering
# ---------------------------------------------------------------------------


def test_filter_publish_paths_drops_exclude_prefixes() -> None:
    paths = [
        "app/streamlit_app.py",
        "tests/test_foo.py",
        "tests/scripts/test_deploy_hf.py",
        ".github/workflows/ci.yml",
        "docs/research/recon_2026-05-25/note.md",
        "reviews/codex_review.md",
        "eval/baselines/reproducible_n200.json",
        "eval/reports/2026-05-11/G.json",
        "scripts/autotune/run_cycle.py",
        "scripts/deploy_hf.py",
        "src/nl_sql/__init__.py",
    ]
    got = deploy_hf.filter_publish_paths(paths)
    assert "app/streamlit_app.py" in got
    assert "src/nl_sql/__init__.py" in got
    for banned in (
        "tests/test_foo.py",
        "tests/scripts/test_deploy_hf.py",
        ".github/workflows/ci.yml",
        "docs/research/recon_2026-05-25/note.md",
        "reviews/codex_review.md",
        "eval/baselines/reproducible_n200.json",
        "eval/reports/2026-05-11/G.json",
        "scripts/autotune/run_cycle.py",
        "scripts/deploy_hf.py",
    ):
        assert banned not in got


def test_filter_publish_paths_drops_hygiene_and_readme() -> None:
    paths = [
        "README.md",  # bulk-excluded; frontmatter version uploaded separately
        "audit_codex_12_05_26.md",
        "plan_for_pres.md",
        "_NEXT_SESSION.md",
        "docs/NEXT_SESSION.md",
        "27_05_26.md",
        "_ref_presentation3.html",
        "Dockerfile",
        "app/streamlit_app.py",
    ]
    got = deploy_hf.filter_publish_paths(paths)
    assert got == ["Dockerfile", "app/streamlit_app.py"]
    assert "README.md" not in got


def test_filter_publish_paths_drops_marker_bearing_deploy_metadata() -> None:
    paths = [
        "README.md",
        "DEPLOY.md",
        "docs/PROJECT_CLOSURE.md",
        "scripts/deploy_hf.py",
        "Dockerfile",
        "app/streamlit_app.py",
    ]

    assert deploy_hf.filter_publish_paths(paths) == [
        "Dockerfile",
        "app/streamlit_app.py",
    ]


def test_is_excluded_prefix_matches_directory_and_children() -> None:
    assert deploy_hf.is_excluded_prefix("tests/foo.py")
    assert deploy_hf.is_excluded_prefix("scripts/autotune/colab/x.ipynb")
    assert not deploy_hf.is_excluded_prefix("scripts/deploy_hf.py")
    assert not deploy_hf.is_excluded_prefix("app/streamlit_app.py")


# ---------------------------------------------------------------------------
# Expected remote paths
# ---------------------------------------------------------------------------


def test_expected_remote_paths_includes_generated_and_dockerfile(
    tmp_path: Path,
) -> None:
    publish = ["app/streamlit_app.py", "requirements.txt"]
    remote = deploy_hf.expected_remote_paths(publish, root=tmp_path, has_gitattributes=False)
    assert "README.md" in remote
    assert "Dockerfile" in remote
    assert "app/streamlit_app.py" in remote
    assert "requirements.txt" in remote
    assert ".gitattributes" not in remote


def test_expected_remote_paths_includes_gitattributes_when_present(
    tmp_path: Path,
) -> None:
    (tmp_path / ".gitattributes").write_text("* text=auto\n", encoding="utf-8")
    remote = deploy_hf.expected_remote_paths(["app/x.py"], root=tmp_path, has_gitattributes=None)
    assert ".gitattributes" in remote


def test_safety_gate_requires_tracked_deploy_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "streamlit_app.py").write_text("# app\n", encoding="utf-8")
    monkeypatch.setattr(
        deploy_hf,
        "tracked_files",
        lambda *, root=None: ["README.md", "app/streamlit_app.py"],
    )

    failures = deploy_hf.run_safety_gate(root=tmp_path)

    assert any("Dockerfile" in failure and "tracked" in failure for failure in failures)
    assert any("scripts/deploy_hf.py" in failure and "tracked" in failure for failure in failures)


# ---------------------------------------------------------------------------
# Tunnel markers (every marker + chunk-boundary split)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("marker", deploy_hf.TUNNEL_MARKERS)
def test_every_tunnel_marker_is_detected(tmp_path: Path, marker: bytes) -> None:
    path = tmp_path / "payload.bin"
    # Mixed case to exercise IGNORECASE.
    mixed = bytes(b ^ 0x20 if 65 <= b <= 90 else b for b in marker)  # flip A-Z case
    # Prefer lowercase marker with surrounding noise when flip is a no-op.
    body = b"prefix-" + marker.upper() + b"-suffix"
    path.write_bytes(body)
    assert deploy_hf.file_has_tunnel_marker(path), marker
    # Also confirm the case-flipped form when it differs.
    if mixed != marker:
        path.write_bytes(b"xx" + mixed + b"yy")
        assert deploy_hf.file_has_tunnel_marker(path), mixed


def test_tunnel_marker_split_across_chunk_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Marker straddling two read() windows must still be caught."""
    marker = b"cloudflared"
    # Force tiny chunks so the marker necessarily spans a boundary.
    monkeypatch.setattr(deploy_hf, "_CHUNK_SIZE", 4)
    monkeypatch.setattr(deploy_hf, "_CHUNK_OVERLAP", len(marker))

    # 6 bytes of noise + marker → with chunk size 4 the marker crosses boundaries.
    payload = b"ABCDEF" + marker + b"ZZZZ"
    path = tmp_path / "split.bin"
    path.write_bytes(payload)
    assert deploy_hf.file_has_tunnel_marker(path)


def test_tunnel_hits_returns_only_matching_paths(tmp_path: Path) -> None:
    clean = tmp_path / "clean.txt"
    dirty = tmp_path / "dirty.txt"
    clean.write_text("hello world", encoding="utf-8")
    dirty.write_bytes(b"uses ngrok for something")
    hits = deploy_hf.tunnel_hits(["clean.txt", "dirty.txt"], root=tmp_path)
    assert hits == ["dirty.txt"]


# ---------------------------------------------------------------------------
# HF frontmatter
# ---------------------------------------------------------------------------


def test_hf_readme_frontmatter_contents() -> None:
    text = deploy_hf.hf_readme_frontmatter()
    assert text.startswith("---\n")
    assert "sdk: docker" in text
    assert "app_port: 7860" in text
    assert "license: mit" in text
    assert "61.5%" in text
    assert len(deploy_hf.SHORT_DESCRIPTION) <= 60
    assert text.rstrip().endswith("---") or text.endswith("---\n")


def test_build_hf_readme_prepends_frontmatter(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Body\n", encoding="utf-8")
    full = deploy_hf.build_hf_readme(root=tmp_path)
    assert full.startswith("---\n")
    assert "sdk: docker" in full
    assert "# Body" in full
    # Frontmatter block ends before body.
    assert full.index("---\n") < full.index("# Body")


def test_build_hf_readme_sanitizes_tunnel_markers(tmp_path: Path) -> None:
    markers = " ".join(marker.decode("ascii") for marker in deploy_hf.TUNNEL_MARKERS)
    (tmp_path / "README.md").write_text(
        f"# Deployment status\n\nBlocked for: {markers}\n",
        encoding="utf-8",
    )

    full = deploy_hf.build_hf_readme(root=tmp_path)

    assert deploy_hf._TUNNEL_RE.search(full.encode("utf-8")) is None
    assert "tunnel-client rule" in full


def test_root_dockerfile_matches_space_runtime_contract() -> None:
    dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")

    assert "FROM python:3.13-slim" in text
    assert "libgomp1" in text
    assert "COPY requirements.txt" in text
    assert "PYTHONPATH=/app/src" in text
    assert '"--server.port=7860"' in text
    assert '"--server.address=0.0.0.0"' in text


# ---------------------------------------------------------------------------
# Local-only CLI modes
# ---------------------------------------------------------------------------


def _configure_minimal_local_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM python:3.13-slim\n", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "streamlit_app.py").write_text("# app\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "deploy_hf.py").write_text("# deploy\n", encoding="utf-8")
    monkeypatch.setattr(deploy_hf, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        deploy_hf,
        "tracked_files",
        lambda *, root=None: [
            "README.md",
            "Dockerfile",
            "app/streamlit_app.py",
            "scripts/deploy_hf.py",
        ],
    )


def test_self_test_is_local_and_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--self-test`` must not import huggingface_hub or read credentials."""
    _configure_minimal_local_repo(tmp_path, monkeypatch)
    real_import = __import__

    def guard_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "huggingface_hub" or name.startswith("huggingface_hub."):
            raise AssertionError("self-test must not import huggingface_hub")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guard_import)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    # Safety gate uses the real repo; should pass on a clean tree.
    rc = deploy_hf.main(["--self-test"])
    assert rc == 0


def test_dry_run_is_local_and_passes(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_minimal_local_repo(tmp_path, monkeypatch)
    real_import = __import__

    def guard_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "huggingface_hub" or name.startswith("huggingface_hub."):
            raise AssertionError("dry-run must not import huggingface_hub")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guard_import)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    rc = deploy_hf.main(["--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "no network" in out.lower() or "safety gate OK" in out


def test_no_flags_prints_usage_and_returns_nonzero(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = __import__

    def guard_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "huggingface_hub" or name.startswith("huggingface_hub."):
            raise AssertionError("no-flag mode must not import huggingface_hub")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guard_import)
    rc = deploy_hf.main([])
    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "--apply" in combined
    assert "--self-test" in combined


# ---------------------------------------------------------------------------
# Fully mocked --apply (env-only secrets)
# ---------------------------------------------------------------------------


def test_apply_uses_env_secrets_only_and_skips_existing_space(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--apply`` reads secrets only from the environment; never file paths."""
    # Minimal fake tree for the gate + upload.
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM python:3.13-slim\n", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "streamlit_app.py").write_text("# app\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "deploy_hf.py").write_text("# deploy\n", encoding="utf-8")

    monkeypatch.setattr(deploy_hf, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        deploy_hf,
        "tracked_files",
        lambda *, root=None: [
            "README.md",
            "Dockerfile",
            "app/streamlit_app.py",
            "scripts/deploy_hf.py",
        ],
    )
    # Gate would plant a probe under root; keep real run_safety_gate but
    # with our tmp root so tunnel probe is local.
    monkeypatch.setenv("HF_TOKEN", "hf_test_token_not_a_real_secret")
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral_test_key_not_a_real_secret")

    # Ensure no credential-path env vars are consulted.
    for banned in (
        "HF_TOKEN_PATH",
        "MISTRAL_API_KEY_PATH",
        "MISTRAL_KEY_FILE",
    ):
        monkeypatch.delenv(banned, raising=False)

    api = MagicMock()
    api.repo_exists.return_value = True
    api.list_repo_files.return_value = [
        "README.md",
        "Dockerfile",
        "app/streamlit_app.py",
        "stale/leftover.txt",  # must be pruned
    ]

    # Inject a fake huggingface_hub module for the lazy imports inside apply.
    import sys

    fake_hub = SimpleNamespace(
        HfApi=MagicMock(return_value=api),
        CommitOperationDelete=lambda path_in_repo: SimpleNamespace(path_in_repo=path_in_repo),
    )
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)

    path_reads: list[str] = []
    real_open = Path.open

    def tracking_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        path_reads.append(self.as_posix())
        # Block any attempt to open well-known local credential paths.
        lowered = self.as_posix().lower()
        for needle in ("mistral_api", "hf_token", "vacancyradar", "/txt/"):
            if needle in lowered and self.suffix in {".txt", ".env", ""}:
                raise AssertionError(f"must not open credential path: {self}")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)

    rc = deploy_hf.apply_deploy(root=tmp_path)
    assert rc == 0

    fake_hub.HfApi.assert_called_once_with(token="hf_test_token_not_a_real_secret")
    api.create_repo.assert_not_called()
    api.add_space_secret.assert_called_once_with(
        repo_id=deploy_hf.REPO_ID,
        key="MISTRAL_API_KEY",
        value="mistral_test_key_not_a_real_secret",
    )
    api.upload_folder.assert_called_once()
    api.upload_file.assert_called_once()
    # README upload carries frontmatter bytes, not a secret.
    upload_kwargs = api.upload_file.call_args.kwargs
    assert upload_kwargs["path_in_repo"] == "README.md"
    payload = upload_kwargs["path_or_fileobj"]
    assert isinstance(payload, (bytes, bytearray))
    assert b"sdk: docker" in payload
    assert b"mistral_test_key" not in payload

    api.create_commit.assert_called_once()
    ops = api.create_commit.call_args.kwargs["operations"]
    assert len(ops) == 1
    assert ops[0].path_in_repo == "stale/leftover.txt"


def test_apply_requires_mistral_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "README.md").write_text("# x\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM x\n", encoding="utf-8")
    monkeypatch.setattr(deploy_hf, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(deploy_hf, "tracked_files", lambda *, root=None: ["Dockerfile"])
    monkeypatch.setattr(deploy_hf, "run_safety_gate", lambda *, root=None: [])
    monkeypatch.setenv("HF_TOKEN", "hf_test_token")
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
        deploy_hf.apply_deploy(root=tmp_path)


def test_apply_requires_hf_token_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(deploy_hf, "run_safety_gate", lambda *, root=None: [])
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral_test")
    monkeypatch.delenv("HF_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="HF_TOKEN"):
        deploy_hf.apply_deploy(root=tmp_path)


def test_main_apply_returns_nonzero_when_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(deploy_hf, "run_safety_gate", lambda *, root=None: [])
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    rc = deploy_hf.main(["--apply"])
    assert rc == 1


def test_main_apply_aborts_on_failed_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deploy_hf, "run_safety_gate", lambda *, root=None: ["planted failure"])
    # Even with env set, gate failure must win before any hub import.
    monkeypatch.setenv("HF_TOKEN", "t")
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    real_import = __import__

    def guard_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "huggingface_hub" or name.startswith("huggingface_hub."):
            raise AssertionError("failed gate must not import huggingface_hub")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guard_import)
    rc = deploy_hf.main(["--apply"])
    assert rc == 1


def test_require_env_rejects_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_TOKEN", "   ")
    with pytest.raises(RuntimeError, match="HF_TOKEN"):
        deploy_hf._require_env("HF_TOKEN")
    # Sanity: real value works.
    monkeypatch.setenv("HF_TOKEN", "ok")
    assert deploy_hf._require_env("HF_TOKEN") == "ok"
    assert "HF_TOKEN" in os.environ
