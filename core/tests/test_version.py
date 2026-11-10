"""The package version has one source, tradingagents.__version__, which the build reads."""

import re
from pathlib import Path

import pytest

import core

_p1 = Path(__file__).resolve().parents[1] / "pyproject.toml"
_p2 = Path(__file__).resolve().parents[2] / "pyproject.toml"
PYPROJECT_PATH = _p1 if _p1.exists() else _p2
PYPROJECT = PYPROJECT_PATH.read_text(encoding="utf-8") if PYPROJECT_PATH.exists() else ""


@pytest.mark.unit
def test_the_build_reads_the_version_from_the_package():
    assert core.__version__
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+|rc\d+)?", core.__version__)
