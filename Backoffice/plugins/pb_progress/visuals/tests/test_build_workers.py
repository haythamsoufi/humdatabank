"""Tests for build worker cap resolution."""

from __future__ import annotations

import os

import pytest

from pb_figures.config import build_workers, default_worker_cap


@pytest.mark.unit
def test_build_workers_single_job_is_always_one(monkeypatch) -> None:
    monkeypatch.delenv("PB_BUILD_WORKERS", raising=False)
    assert build_workers(1) == 1


@pytest.mark.unit
def test_build_workers_respects_env_cap(monkeypatch) -> None:
    monkeypatch.setenv("PB_BUILD_WORKERS", "2")
    assert build_workers(10) == 2


@pytest.mark.unit
def test_build_workers_never_exceeds_job_count(monkeypatch) -> None:
    monkeypatch.setenv("PB_BUILD_WORKERS", "8")
    assert build_workers(3) == 3


@pytest.mark.unit
def test_default_worker_cap_local(monkeypatch) -> None:
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    assert default_worker_cap() == 4


@pytest.mark.unit
def test_default_worker_cap_conservative(monkeypatch) -> None:
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    assert default_worker_cap(conservative=True) == 2
