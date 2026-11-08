"""Mounts USB partitions through small privileged helper scripts.

The viewer runs as the desktop user. The helpers (see ``install/``) are the
only commands allowed through ``sudo`` without a password, which keeps the
privilege surface small.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

HELPER_TIMEOUT_SEC = 30


class MountError(Exception):
    """Raised when a mount or unmount helper fails."""


@dataclass(frozen=True)
class SudoMounter:
    mount_helper: str
    umount_helper: str

    def mount(self, device: str) -> Path:
        output = _run_helper([self.mount_helper, device])
        mountpoint = output.strip().splitlines()[-1] if output.strip() else ""
        if not mountpoint:
            raise MountError(f"マウントヘルパーがマウント先を返しませんでした: {device}")
        return Path(mountpoint)

    def unmount(self, mountpoint: Path) -> None:
        _run_helper([self.umount_helper, mountpoint.as_posix()])

    def unmount_all(self) -> None:
        """Release mounts left behind by a previous run (crash, power loss...)."""
        _run_helper([self.umount_helper, "--all"])


def _run_helper(command: list[str]) -> str:
    full_command = ["sudo", "-n", *command]
    try:
        completed = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=HELPER_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MountError(f"{' '.join(command)}: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise MountError(f"{' '.join(command)} (exit {completed.returncode}): {detail}")
    return completed.stdout
