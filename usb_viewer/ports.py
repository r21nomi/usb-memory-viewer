"""Interfaces that separate the viewer logic from the Raspberry Pi specifics."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class DeviceScanner(Protocol):
    def list_usb_partitions(self) -> tuple[str, ...]:
        """Return sorted device nodes (e.g. ``/dev/sda1``) of attached USB storage."""


class Mounter(Protocol):
    def mount(self, device: str) -> Path:
        """Mount the device read-only and return the mountpoint."""

    def unmount(self, mountpoint: Path) -> None:
        """Release the mountpoint, even if the device is already gone."""


class Browser(Protocol):
    def show(self, html: Path) -> None:
        """Display the file fullscreen, replacing whatever is shown."""

    def close(self) -> None:
        """Close the browser window if one is open."""

    def is_running(self) -> bool:
        """True while the browser process is alive."""
