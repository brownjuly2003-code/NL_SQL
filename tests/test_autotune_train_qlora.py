"""Guards for the trl-signature probe in scripts/autotune/train_qlora.py.

Two Kaggle GPU sessions died on `SFTConfig(max_seq_length=...)` after trl
renamed the field to `max_length`. The probe that replaced the hard-coded name
is only worth anything if it survives every signature shape trl has shipped, so
it is pinned here rather than in a comment.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "autotune" / "train_qlora.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("autotune_train_qlora", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def train_qlora() -> Any:
    return _load_module()


@dataclasses.dataclass
class _NewStyleConfig:
    """trl >= 0.12: dataclass, field renamed to max_length."""

    output_dir: str = ""
    max_length: int = 0
    fp16: bool = False


@dataclasses.dataclass
class _OldStyleConfig:
    """trl < 0.12: dataclass, legacy max_seq_length."""

    output_dir: str = ""
    max_seq_length: int = 0
    fp16: bool = False


class _OpaqueConfig:
    def __init__(self, **kwargs: Any) -> None:  # pragma: no cover - shape only
        self.kwargs = kwargs


class _ExplicitTrainer:
    def __init__(self, model: Any = None, processing_class: Any = None) -> None:
        self.model = model
        self.processing_class = processing_class


def test_dataclass_fields_are_discovered(train_qlora: Any) -> None:
    assert train_qlora.accepted_kwargs(_NewStyleConfig) == {"output_dir", "max_length", "fp16"}


def test_legacy_dataclass_reports_legacy_name(train_qlora: Any) -> None:
    keys = train_qlora.accepted_kwargs(_OldStyleConfig)
    assert keys is not None
    assert "max_seq_length" in keys
    assert "max_length" not in keys


def test_opaque_kwargs_signature_is_undiscoverable(train_qlora: Any) -> None:
    # None means "pass everything through" — filtering here would drop every
    # option and silently train with defaults.
    assert train_qlora.accepted_kwargs(_OpaqueConfig) is None


def test_plain_class_signature_excludes_self(train_qlora: Any) -> None:
    assert train_qlora.accepted_kwargs(_ExplicitTrainer) == {"model", "processing_class"}
