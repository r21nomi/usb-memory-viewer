"""Launches and stops Chromium in kiosk mode."""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

BROWSER_CANDIDATES = ("chromium", "chromium-browser", "google-chrome")
TERMINATE_TIMEOUT_SEC = 3.0
KILL_TIMEOUT_SEC = 2.0
PROFILE_DIR_NAME = "usb-viewer-chromium"

KIOSK_ARGS = (
    "--kiosk",
    "--incognito",
    "--no-first-run",
    "--noerrdialogs",
    "--disable-infobars",
    "--disable-session-crashed-bubble",
    "--disable-translate",
    "--disable-features=TranslateUI",
    "--disable-pinch",
    "--overscroll-history-navigation=0",
    "--autoplay-policy=no-user-gesture-required",
    "--check-for-update-interval=31536000",
    "--password-store=basic",
    "--disk-cache-size=1",
)
FILE_ACCESS_ARG = "--allow-file-access-from-files"


class BrowserError(Exception):
    """Raised when the browser binary cannot be found or started."""


class ChromiumBrowser:
    def __init__(
        self,
        command: str,
        extra_args: tuple[str, ...] = (),
        allow_file_access: bool = True,
    ) -> None:
        self._command = _resolve_command(command)
        self._extra_args = extra_args
        self._allow_file_access = allow_file_access
        self._process: subprocess.Popen[bytes] | None = None
        self._profile_dir = _profile_dir()

    def show(self, html: Path) -> None:
        self.close()
        args = [
            self._command,
            *KIOSK_ARGS,
            *((FILE_ACCESS_ARG,) if self._allow_file_access else ()),
            f"--user-data-dir={self._profile_dir}",
            *self._extra_args,
            html.resolve().as_uri(),
        ]
        log.info("Chromiumを起動: %s", html)
        try:
            self._process = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as error:
            raise BrowserError(f"Chromiumを起動できません: {error}") from error

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        _stop_process_group(process)
        log.info("Chromiumを終了しました")

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def kill_stale(self) -> None:
        """Kill Chromium left over from a previous run that used our profile."""
        pattern = f"--user-data-dir={self._profile_dir}"
        try:
            result = subprocess.run(
                ["pkill", "-KILL", "-f", "--", pattern], check=False, capture_output=True
            )
        except OSError as error:
            log.warning("残留Chromiumの確認に失敗: %s", error)
            return
        if result.returncode == 0:
            log.warning("前回の残留Chromiumを終了しました")

    def cleanup(self) -> None:
        self.close()
        shutil.rmtree(self._profile_dir, ignore_errors=True)


def _profile_dir() -> Path:
    """A fixed profile path, on tmpfs when available, so stale runs are findable."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    base = Path(runtime_dir) if runtime_dir and Path(runtime_dir).is_dir() else (
        Path("~/.cache").expanduser()
    )
    profile = base / PROFILE_DIR_NAME
    profile.mkdir(parents=True, exist_ok=True)
    return profile


def _resolve_command(command: str) -> str:
    found = shutil.which(command)
    if found:
        return found
    for candidate in BROWSER_CANDIDATES:
        fallback = shutil.which(candidate)
        if fallback:
            log.warning("%s が見つからないため %s を使います", command, fallback)
            return fallback
    raise BrowserError(f"ブラウザが見つかりません: {command}")


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    """Terminate every process in Chromium's group, even if the leader died."""
    _signal_group(process, signal.SIGTERM)
    if not _wait(process, TERMINATE_TIMEOUT_SEC):
        log.warning("Chromiumが終了しないため強制終了します")
    # The group id stays reserved while any member lives, so SIGKILL is safe and
    # also reaps renderer/GPU processes that outlived the leader.
    _signal_group(process, signal.SIGKILL)
    _wait(process, KILL_TIMEOUT_SEC)


def _wait(process: subprocess.Popen[bytes], timeout: float) -> bool:
    try:
        process.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        return False


def _signal_group(process: subprocess.Popen[bytes], sig: signal.Signals) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass
    except OSError as error:
        log.warning("プロセスグループへのシグナル送信に失敗: %s", error)
