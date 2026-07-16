"""Tests for the top-level scheduler_lock module (re-exported as app.scheduler_lock).

Platform notes:
- The flock implementation only runs on POSIX (Linux CI); those tests skip on
  this Windows dev machine.
- The hardened PID-file fallback (Windows production path) is exercised on all
  platforms by forcing ``scheduler_lock.fcntl = None``.
"""

import os
import sys
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

import scheduler_lock
from scheduler_lock import (
    SchedulerLockResult,
    pid_alive,
    read_lock_owner,
    release_scheduler_lock,
    scheduler_lock_path,
    shutdown_scheduler_bounded,
    shutdown_worker_scheduler,
    sweep_stale_scheduler_locks,
    try_acquire_scheduler_lock,
)

_HAS_FCNTL = scheduler_lock.fcntl is not None

DEAD_PID = 999999999


@pytest.fixture
def lock_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def _clean_held_locks():
    """Release any flocks a test left behind so tests stay independent."""
    yield
    with scheduler_lock._held_locks_guard:
        leftovers = dict(scheduler_lock._held_locks)
        scheduler_lock._held_locks.clear()
    for fd, _owner in leftovers.values():
        try:
            os.close(fd)
        except OSError:
            pass


@pytest.fixture
def pidfile_mode(monkeypatch):
    """Force the Windows/PID-file fallback regardless of platform."""
    monkeypatch.setattr(scheduler_lock, 'fcntl', None)


def _write_lock(path, content):
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(content)


class TestSchedulerLockPath:
    def test_uses_temp_dir(self, lock_dir):
        path = scheduler_lock_path(42)
        assert path == os.path.join(str(lock_dir), 'hdb_scheduler_42.lock')


class TestReadLockOwner:
    def test_reads_valid_pid(self, lock_dir):
        path = scheduler_lock_path(1)
        _write_lock(path, '12345')
        assert read_lock_owner(path) == 12345

    def test_invalid_content_returns_none(self, lock_dir):
        path = scheduler_lock_path(1)
        _write_lock(path, 'not-a-pid')
        assert read_lock_owner(path) is None

    def test_missing_file_returns_none(self, lock_dir):
        assert read_lock_owner(scheduler_lock_path(999)) is None


class TestPidAlive:
    def test_current_process_is_alive(self):
        assert pid_alive(os.getpid()) is True

    def test_invalid_pid_is_dead(self):
        assert pid_alive(-1) is False
        assert pid_alive(DEAD_PID) is False

    @pytest.mark.skipif(os.name == 'nt', reason='POSIX pid_alive semantics')
    def test_posix_eperm_means_alive(self):
        with patch('scheduler_lock.os.kill', side_effect=PermissionError):
            assert scheduler_lock._pid_alive_posix(1) is True


class TestPidAliveWindows:
    """_pid_alive_windows with a mocked ctypes module (runs on any platform)."""

    STILL_ACTIVE = 259
    ERROR_ACCESS_DENIED = 5

    def _mock_ctypes(self, *, open_result, exit_code=0, last_error=0, exit_call_ok=True):
        mock_ctypes = MagicMock()
        kernel32 = MagicMock()
        mock_ctypes.WinDLL.return_value = kernel32
        kernel32.OpenProcess.return_value = open_result
        mock_ctypes.get_last_error.return_value = last_error

        code_holder = MagicMock()
        code_holder.value = exit_code
        mock_ctypes.c_ulong.return_value = code_holder
        kernel32.GetExitCodeProcess.return_value = 1 if exit_call_ok else 0
        return mock_ctypes, kernel32

    def _call(self, mock_ctypes, pid=1234):
        with patch.dict(sys.modules, {'ctypes': mock_ctypes}):
            return scheduler_lock._pid_alive_windows(pid)

    def test_running_process_is_alive(self):
        mock_ctypes, kernel32 = self._mock_ctypes(open_result=111, exit_code=self.STILL_ACTIVE)
        assert self._call(mock_ctypes) is True
        kernel32.CloseHandle.assert_called_once_with(111)

    def test_exited_process_is_dead(self):
        mock_ctypes, kernel32 = self._mock_ctypes(open_result=111, exit_code=0)
        assert self._call(mock_ctypes) is False
        kernel32.CloseHandle.assert_called_once_with(111)

    def test_access_denied_counts_as_alive(self):
        mock_ctypes, _ = self._mock_ctypes(open_result=0, last_error=self.ERROR_ACCESS_DENIED)
        assert self._call(mock_ctypes) is True

    def test_open_failure_other_error_is_dead(self):
        mock_ctypes, _ = self._mock_ctypes(open_result=0, last_error=87)
        assert self._call(mock_ctypes) is False

    def test_get_exit_code_failure_assumes_alive(self):
        mock_ctypes, _ = self._mock_ctypes(open_result=111, exit_call_ok=False)
        assert self._call(mock_ctypes) is True

    def test_never_uses_os_kill(self):
        """os.kill on Windows would TERMINATE the probed process."""
        mock_ctypes, _ = self._mock_ctypes(open_result=111, exit_code=self.STILL_ACTIVE)
        with patch('scheduler_lock.os.kill') as mock_kill:
            self._call(mock_ctypes)
        mock_kill.assert_not_called()


# ---------------------------------------------------------------------------
# PID-file fallback (Windows production path; forced on all platforms)
# ---------------------------------------------------------------------------

class TestTryAcquirePidfileFallback:
    def test_acquires_when_missing(self, lock_dir, pidfile_mode):
        result = try_acquire_scheduler_lock(1, owner_pid=5001)
        assert result is SchedulerLockResult.ACQUIRED
        assert read_lock_owner(scheduler_lock_path(1)) == 5001

    def test_no_tmp_files_left_behind(self, lock_dir, pidfile_mode):
        try_acquire_scheduler_lock(1, owner_pid=5001)
        leftovers = [name for name in os.listdir(str(lock_dir)) if name.endswith('.tmp')]
        assert leftovers == []

    def test_same_owner_re_acquires(self, lock_dir, pidfile_mode):
        try_acquire_scheduler_lock(1, owner_pid=5001)
        result = try_acquire_scheduler_lock(1, owner_pid=5001)
        assert result is SchedulerLockResult.ACQUIRED

    def test_live_owner_blocks(self, lock_dir, pidfile_mode):
        try_acquire_scheduler_lock(1, owner_pid=5001)
        with patch('scheduler_lock.pid_alive', return_value=True):
            result = try_acquire_scheduler_lock(1, owner_pid=5002)
        assert result is SchedulerLockResult.HELD_BY_LIVE_OWNER

    def test_reclaims_stale_owner(self, lock_dir, pidfile_mode):
        path = scheduler_lock_path(1)
        _write_lock(path, str(DEAD_PID))
        result = try_acquire_scheduler_lock(1, owner_pid=5003)
        assert result is SchedulerLockResult.RECLAIMED_STALE
        assert read_lock_owner(path) == 5003

    def test_reclaims_corrupt_lock(self, lock_dir, pidfile_mode):
        path = scheduler_lock_path(1)
        _write_lock(path, 'corrupt')
        result = try_acquire_scheduler_lock(1, owner_pid=5004)
        assert result is SchedulerLockResult.RECLAIMED_STALE
        assert read_lock_owner(path) == 5004

    def test_verify_after_reclaim_detects_racing_winner(self, lock_dir, pidfile_mode):
        """If another worker wins the read->remove->recreate race, back off."""
        path = scheduler_lock_path(1)
        _write_lock(path, str(DEAD_PID))
        # First read: stale owner. Second read (verify): another pid won.
        with patch('scheduler_lock.read_lock_owner', side_effect=[DEAD_PID, 424242]):
            result = try_acquire_scheduler_lock(1, owner_pid=5005)
        assert result is SchedulerLockResult.HELD_BY_LIVE_OWNER

    def test_fs_error_fails_closed_by_default(self, lock_dir, pidfile_mode, monkeypatch):
        monkeypatch.delenv('SCHEDULER_LOCK_FAIL_OPEN', raising=False)
        with patch('scheduler_lock._create_pidfile_atomically', return_value=None):
            result = try_acquire_scheduler_lock(1, owner_pid=5006)
        assert result is SchedulerLockResult.HELD_BY_LIVE_OWNER

    def test_fs_error_fail_open_via_env(self, lock_dir, pidfile_mode, monkeypatch):
        monkeypatch.setenv('SCHEDULER_LOCK_FAIL_OPEN', 'true')
        with patch('scheduler_lock._create_pidfile_atomically', return_value=None):
            result = try_acquire_scheduler_lock(1, owner_pid=5007)
        assert result is SchedulerLockResult.FILESYSTEM_FALLBACK


class TestReleasePidfileFallback:
    def test_release_when_owner_matches(self, lock_dir, pidfile_mode):
        try_acquire_scheduler_lock(1, owner_pid=6001)
        assert release_scheduler_lock(1, owner_pid=6001) is True
        assert not os.path.exists(scheduler_lock_path(1))

    def test_release_skips_other_owner(self, lock_dir, pidfile_mode):
        try_acquire_scheduler_lock(1, owner_pid=6001)
        assert release_scheduler_lock(1, owner_pid=6002) is False
        assert read_lock_owner(scheduler_lock_path(1)) == 6001

    def test_release_missing_lock(self, lock_dir, pidfile_mode):
        assert release_scheduler_lock(1, owner_pid=6001) is False


# ---------------------------------------------------------------------------
# flock implementation (POSIX / Linux CI only)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAS_FCNTL, reason='flock requires POSIX (runs in Linux CI)')
class TestFlockLock:
    def test_acquires_when_missing(self, lock_dir):
        result = try_acquire_scheduler_lock(1, owner_pid=5001)
        assert result is SchedulerLockResult.ACQUIRED
        assert read_lock_owner(scheduler_lock_path(1)) == 5001

    def test_same_owner_re_acquires_via_registry(self, lock_dir):
        try_acquire_scheduler_lock(1, owner_pid=5001)
        assert try_acquire_scheduler_lock(1, owner_pid=5001) is SchedulerLockResult.ACQUIRED

    def test_other_owner_in_same_process_blocks(self, lock_dir):
        try_acquire_scheduler_lock(1, owner_pid=5001)
        assert try_acquire_scheduler_lock(1, owner_pid=5002) is SchedulerLockResult.HELD_BY_LIVE_OWNER

    def test_external_flock_holder_blocks(self, lock_dir):
        """A flock held on another open-file-description (i.e. another process) blocks."""
        import fcntl as _fcntl
        path = scheduler_lock_path(1)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            result = try_acquire_scheduler_lock(1, owner_pid=5003)
            assert result is SchedulerLockResult.HELD_BY_LIVE_OWNER
        finally:
            os.close(fd)

    def test_leftover_content_from_dead_owner_reports_reclaim(self, lock_dir):
        """Kernel released a dead owner's flock; its pid remains as content."""
        path = scheduler_lock_path(1)
        _write_lock(path, str(DEAD_PID))
        result = try_acquire_scheduler_lock(1, owner_pid=5004)
        assert result is SchedulerLockResult.RECLAIMED_STALE
        assert read_lock_owner(path) == 5004

    def test_release_clears_owner_but_keeps_file(self, lock_dir):
        try_acquire_scheduler_lock(1, owner_pid=6001)
        assert release_scheduler_lock(1, owner_pid=6001) is True
        # No unlink (flock unlink race); owner pid is cleared instead.
        assert os.path.exists(scheduler_lock_path(1))
        assert read_lock_owner(scheduler_lock_path(1)) is None

    def test_release_skips_other_owner(self, lock_dir):
        try_acquire_scheduler_lock(1, owner_pid=6001)
        assert release_scheduler_lock(1, owner_pid=6002) is False
        assert read_lock_owner(scheduler_lock_path(1)) == 6001

    def test_release_when_not_held(self, lock_dir):
        assert release_scheduler_lock(1, owner_pid=6001) is False

    def test_reacquire_after_release(self, lock_dir):
        try_acquire_scheduler_lock(1, owner_pid=6001)
        release_scheduler_lock(1, owner_pid=6001)
        assert try_acquire_scheduler_lock(1, owner_pid=6002) is SchedulerLockResult.ACQUIRED

    def test_flock_error_fails_closed_by_default(self, lock_dir, monkeypatch):
        monkeypatch.delenv('SCHEDULER_LOCK_FAIL_OPEN', raising=False)
        with patch.object(scheduler_lock.fcntl, 'flock', side_effect=OSError(5, 'io error')):
            result = try_acquire_scheduler_lock(1, owner_pid=5005)
        assert result is SchedulerLockResult.HELD_BY_LIVE_OWNER

    def test_flock_error_fail_open_via_env(self, lock_dir, monkeypatch):
        monkeypatch.setenv('SCHEDULER_LOCK_FAIL_OPEN', 'true')
        with patch.object(scheduler_lock.fcntl, 'flock', side_effect=OSError(5, 'io error')):
            result = try_acquire_scheduler_lock(1, owner_pid=5006)
        assert result is SchedulerLockResult.FILESYSTEM_FALLBACK


# ---------------------------------------------------------------------------
# Dead-master sweep
# ---------------------------------------------------------------------------

class TestSweepStaleSchedulerLocks:
    def test_removes_dead_master_files(self, lock_dir):
        dead_path = scheduler_lock_path(DEAD_PID)
        _write_lock(dead_path, '4242')
        assert sweep_stale_scheduler_locks() == 1
        assert not os.path.exists(dead_path)

    def test_keeps_live_master_files(self, lock_dir):
        live_path = scheduler_lock_path(os.getpid())
        _write_lock(live_path, '4242')
        assert sweep_stale_scheduler_locks() == 0
        assert os.path.exists(live_path)

    def test_skips_current_master_even_when_pid_looks_dead(self, lock_dir):
        own_path = scheduler_lock_path(DEAD_PID)
        _write_lock(own_path, '4242')
        assert sweep_stale_scheduler_locks(current_master_pid=DEAD_PID) == 0
        assert os.path.exists(own_path)

    def test_ignores_unrelated_files(self, lock_dir):
        other = os.path.join(str(lock_dir), 'hdb_scheduler_notapid.lock')
        _write_lock(other, 'x')
        unrelated = os.path.join(str(lock_dir), 'something_else.lock')
        _write_lock(unrelated, 'x')
        assert sweep_stale_scheduler_locks() == 0
        assert os.path.exists(other)
        assert os.path.exists(unrelated)


# ---------------------------------------------------------------------------
# Bounded shutdown helpers
# ---------------------------------------------------------------------------

class TestShutdownSchedulerBounded:
    def test_returns_true_when_shutdown_completes(self):
        sched = MagicMock()
        assert shutdown_scheduler_bounded(sched, timeout_s=2.0) is True
        sched.shutdown.assert_called_once_with(wait=True)

    def test_returns_false_and_abandons_when_stuck(self):
        release = threading.Event()
        calls = []

        def _shutdown(wait=True):
            calls.append(wait)
            if wait:
                release.wait(5)

        sched = MagicMock()
        sched.shutdown.side_effect = _shutdown
        try:
            t0 = time.monotonic()
            assert shutdown_scheduler_bounded(sched, timeout_s=0.2) is False
            assert time.monotonic() - t0 < 2.0
            # After timing out it retries without waiting.
            assert calls == [True, False]
        finally:
            release.set()


class TestShutdownWorkerScheduler:
    def test_shuts_down_scheduler_and_releases_lock(self, lock_dir, pidfile_mode):
        try_acquire_scheduler_lock(1, owner_pid=7001)
        wsgi = MagicMock()
        sched = MagicMock()
        sched.running = True
        wsgi.scheduler = sched

        shutdown_worker_scheduler(wsgi, master_pid=1, worker_pid=7001)

        sched.shutdown.assert_called_once_with(wait=True)
        assert wsgi.scheduler is None
        assert not os.path.exists(scheduler_lock_path(1))

    def test_no_wait_uses_immediate_shutdown(self, lock_dir, pidfile_mode):
        wsgi = MagicMock()
        sched = MagicMock()
        sched.running = True
        wsgi.scheduler = sched

        shutdown_worker_scheduler(wsgi, master_pid=1, worker_pid=7001, wait=False)

        sched.shutdown.assert_called_once_with(wait=False)

    def test_releases_lock_even_without_scheduler(self, lock_dir, pidfile_mode):
        try_acquire_scheduler_lock(1, owner_pid=7002)
        shutdown_worker_scheduler(None, master_pid=1, worker_pid=7002)
        assert not os.path.exists(scheduler_lock_path(1))

    def test_does_not_release_other_workers_lock(self, lock_dir, pidfile_mode):
        try_acquire_scheduler_lock(1, owner_pid=7003)
        shutdown_worker_scheduler(None, master_pid=1, worker_pid=7004)
        assert read_lock_owner(scheduler_lock_path(1)) == 7003


class TestHardExitOnTimeout:
    def _stuck_wsgi(self):
        wsgi = MagicMock()
        sched = MagicMock()
        sched.running = True
        wsgi.scheduler = sched
        return wsgi

    def test_hard_exits_when_stuck_in_own_worker(self, lock_dir, pidfile_mode):
        wsgi = self._stuck_wsgi()
        with patch('scheduler_lock.shutdown_scheduler_bounded', return_value=False), \
             patch('scheduler_lock.os._exit') as mock_exit, \
             patch('scheduler_lock._flush_logging_and_stdio') as mock_flush:
            shutdown_worker_scheduler(
                wsgi, master_pid=1, worker_pid=os.getpid(),
                hard_exit_on_timeout=True,
            )
        mock_exit.assert_called_once_with(0)
        mock_flush.assert_called_once()

    def test_releases_lock_before_hard_exit(self, lock_dir, pidfile_mode):
        try_acquire_scheduler_lock(1, owner_pid=os.getpid())
        wsgi = self._stuck_wsgi()
        with patch('scheduler_lock.shutdown_scheduler_bounded', return_value=False), \
             patch('scheduler_lock.os._exit'):
            shutdown_worker_scheduler(
                wsgi, master_pid=1, worker_pid=os.getpid(),
                hard_exit_on_timeout=True,
            )
        assert not os.path.exists(scheduler_lock_path(1))

    def test_never_hard_exits_in_master_reap_path(self, lock_dir, pidfile_mode):
        """worker_pid != os.getpid() (master reaping a dead worker) must not _exit."""
        wsgi = self._stuck_wsgi()
        with patch('scheduler_lock.shutdown_scheduler_bounded', return_value=False), \
             patch('scheduler_lock.os._exit') as mock_exit:
            shutdown_worker_scheduler(
                wsgi, master_pid=1, worker_pid=os.getpid() + 1,
                hard_exit_on_timeout=True,
            )
        mock_exit.assert_not_called()

    def test_no_hard_exit_when_flag_unset(self, lock_dir, pidfile_mode):
        wsgi = self._stuck_wsgi()
        with patch('scheduler_lock.shutdown_scheduler_bounded', return_value=False), \
             patch('scheduler_lock.os._exit') as mock_exit:
            shutdown_worker_scheduler(wsgi, master_pid=1, worker_pid=os.getpid())
        mock_exit.assert_not_called()

    def test_no_hard_exit_when_shutdown_completes(self, lock_dir, pidfile_mode):
        wsgi = self._stuck_wsgi()
        with patch('scheduler_lock.shutdown_scheduler_bounded', return_value=True), \
             patch('scheduler_lock.os._exit') as mock_exit:
            shutdown_worker_scheduler(
                wsgi, master_pid=1, worker_pid=os.getpid(),
                hard_exit_on_timeout=True,
            )
        mock_exit.assert_not_called()


class TestShimReExport:
    def test_app_scheduler_lock_exposes_same_objects(self):
        import app.scheduler_lock as shim
        assert shim.try_acquire_scheduler_lock is try_acquire_scheduler_lock
        assert shim.SchedulerLockResult is SchedulerLockResult
        assert shim.shutdown_worker_scheduler is shutdown_worker_scheduler
