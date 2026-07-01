"""Tests for app/scheduler_lock.py."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.scheduler_lock import (
    SchedulerLockResult,
    clear_stale_scheduler_locks_for_master,
    pid_alive,
    read_lock_owner,
    release_scheduler_lock,
    scheduler_lock_path,
    shutdown_worker_scheduler,
    try_acquire_scheduler_lock,
)


@pytest.fixture
def lock_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path))
    return tmp_path


class TestSchedulerLockPath:
    def test_uses_temp_dir(self, lock_dir):
        path = scheduler_lock_path(42)
        assert path == os.path.join(str(lock_dir), 'hdb_scheduler_42.lock')


class TestReadLockOwner:
    def test_reads_valid_pid(self, lock_dir):
        path = scheduler_lock_path(1)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('12345')
        assert read_lock_owner(path) == 12345

    def test_invalid_content_returns_none(self, lock_dir):
        path = scheduler_lock_path(1)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('not-a-pid')
        assert read_lock_owner(path) is None

    def test_missing_file_returns_none(self, lock_dir):
        assert read_lock_owner(scheduler_lock_path(999)) is None


class TestPidAlive:
    def test_current_process_is_alive(self):
        assert pid_alive(os.getpid()) is True

    def test_invalid_pid_is_dead(self):
        assert pid_alive(-1) is False
        assert pid_alive(999999999) is False


class TestTryAcquireSchedulerLock:
    def test_acquires_when_missing(self, lock_dir):
        result = try_acquire_scheduler_lock(1, owner_pid=5001)
        assert result is SchedulerLockResult.ACQUIRED
        assert read_lock_owner(scheduler_lock_path(1)) == 5001

    def test_same_owner_re_acquires(self, lock_dir):
        try_acquire_scheduler_lock(1, owner_pid=5001)
        result = try_acquire_scheduler_lock(1, owner_pid=5001)
        assert result is SchedulerLockResult.ACQUIRED

    def test_live_owner_blocks(self, lock_dir):
        try_acquire_scheduler_lock(1, owner_pid=5001)
        with patch('app.scheduler_lock.pid_alive', return_value=True):
            result = try_acquire_scheduler_lock(1, owner_pid=5002)
        assert result is SchedulerLockResult.HELD_BY_LIVE_OWNER

    def test_reclaims_stale_owner(self, lock_dir):
        path = scheduler_lock_path(1)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('999999999')
        result = try_acquire_scheduler_lock(1, owner_pid=5003)
        assert result is SchedulerLockResult.RECLAIMED_STALE
        assert read_lock_owner(path) == 5003

    def test_reclaims_corrupt_lock(self, lock_dir):
        path = scheduler_lock_path(1)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('corrupt')
        result = try_acquire_scheduler_lock(1, owner_pid=5004)
        assert result is SchedulerLockResult.RECLAIMED_STALE
        assert read_lock_owner(path) == 5004

    def test_filesystem_fallback_when_create_fails(self, lock_dir):
        with patch('app.scheduler_lock.os.open', side_effect=OSError('denied')):
            result = try_acquire_scheduler_lock(1, owner_pid=5005)
        assert result is SchedulerLockResult.FILESYSTEM_FALLBACK


class TestReleaseSchedulerLock:
    def test_release_when_owner_matches(self, lock_dir):
        try_acquire_scheduler_lock(1, owner_pid=6001)
        assert release_scheduler_lock(1, owner_pid=6001) is True
        assert not os.path.exists(scheduler_lock_path(1))

    def test_release_skips_other_owner(self, lock_dir):
        try_acquire_scheduler_lock(1, owner_pid=6001)
        assert release_scheduler_lock(1, owner_pid=6002) is False
        assert read_lock_owner(scheduler_lock_path(1)) == 6001

    def test_release_missing_lock(self, lock_dir):
        assert release_scheduler_lock(1, owner_pid=6001) is False


class TestClearStaleSchedulerLocksForMaster:
    def test_clears_dead_owner(self, lock_dir):
        path = scheduler_lock_path(7)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('999999999')
        assert clear_stale_scheduler_locks_for_master(7) is True
        assert not os.path.exists(path)

    def test_keeps_live_owner(self, lock_dir):
        try_acquire_scheduler_lock(7, owner_pid=os.getpid())
        assert clear_stale_scheduler_locks_for_master(7) is False
        assert os.path.exists(scheduler_lock_path(7))


class TestShutdownWorkerScheduler:
    def test_shuts_down_scheduler_and_releases_lock(self, lock_dir):
        try_acquire_scheduler_lock(1, owner_pid=7001)
        wsgi = MagicMock()
        sched = MagicMock()
        sched.running = True
        wsgi.scheduler = sched

        shutdown_worker_scheduler(wsgi, master_pid=1, worker_pid=7001)

        sched.shutdown.assert_called_once_with(wait=True)
        assert wsgi.scheduler is None
        assert not os.path.exists(scheduler_lock_path(1))

    def test_releases_lock_even_without_scheduler(self, lock_dir):
        try_acquire_scheduler_lock(1, owner_pid=7002)
        shutdown_worker_scheduler(None, master_pid=1, worker_pid=7002)
        assert not os.path.exists(scheduler_lock_path(1))

    def test_does_not_release_other_workers_lock(self, lock_dir):
        try_acquire_scheduler_lock(1, owner_pid=7003)
        shutdown_worker_scheduler(None, master_pid=1, worker_pid=7004)
        assert read_lock_owner(scheduler_lock_path(1)) == 7003
