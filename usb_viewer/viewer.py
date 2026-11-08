"""State machine that reacts to USB insertion and removal."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from usb_viewer.config import Config
from usb_viewer.html_selector import select_html
from usb_viewer.mounter import MountError
from usb_viewer.ports import Browser, DeviceScanner, Mounter

log = logging.getLogger(__name__)

# A freshly inserted stick may need a moment before /dev/sdXN is usable, so a
# failed mount is retried on the next ticks before the device is given up on.
MAX_MOUNT_ATTEMPTS = 5


@dataclass(frozen=True)
class Session:
    """A USB stick that is currently mounted. ``html`` is None if it had no HTML."""

    device: str
    mountpoint: Path
    html: Path | None


class Viewer:
    """Polls for USB storage and keeps the browser showing the right page."""

    def __init__(
        self,
        config: Config,
        scanner: DeviceScanner,
        mounter: Mounter,
        browser: Browser,
    ) -> None:
        self._config = config
        self._scanner = scanner
        self._mounter = mounter
        self._browser = browser
        self._session: Session | None = None
        self._shown: Path | None = None
        self._failures: Mapping[str, int] = MappingProxyType({})

    def tick(self) -> None:
        """Run one polling cycle. Never raises for expected runtime failures."""
        devices = self._scanner.list_usb_partitions()
        self._forget_removed_failures(devices)
        if self._session is not None and self._session.device not in devices:
            self._end_session()
        if self._session is None:
            self._try_start_session(devices)
        self._ensure_display()

    def shutdown(self) -> None:
        """Close the browser and release any mount before exiting."""
        if self._session is not None:
            self._end_session()
        self._close_browser()

    def _forget_removed_failures(self, devices: tuple[str, ...]) -> None:
        kept = {device: count for device, count in self._failures.items() if device in devices}
        if len(kept) != len(self._failures):
            self._failures = MappingProxyType(kept)

    def _try_start_session(self, devices: tuple[str, ...]) -> None:
        for device in devices:
            if self._failures.get(device, 0) >= MAX_MOUNT_ATTEMPTS:
                continue
            if self._start_session(device):
                return

    def _start_session(self, device: str) -> bool:
        attempt = self._failures.get(device, 0) + 1
        if attempt == 1:
            log.info("USBを検出: %s", device)
        try:
            mountpoint = self._mounter.mount(device)
        except MountError as error:
            self._record_failure(device, attempt, error)
            return False
        self._session = Session(
            device=device, mountpoint=mountpoint, html=self._pick_html(mountpoint)
        )
        return True

    def _record_failure(self, device: str, attempt: int, error: MountError) -> None:
        self._failures = MappingProxyType({**self._failures, device: attempt})
        if attempt >= MAX_MOUNT_ATTEMPTS:
            log.error("マウントを諦めます (%d回失敗) %s: %s", attempt, device, error)
        else:
            log.warning("マウントに失敗 (%d/%d) %s: %s", attempt, MAX_MOUNT_ATTEMPTS, device, error)

    def _pick_html(self, mountpoint: Path) -> Path | None:
        content_dir = mountpoint / self._config.content_dir
        html = select_html(content_dir)
        if html is None:
            log.warning("HTMLファイルが見つかりません: %s", content_dir)
            return None
        if not _is_inside(html, mountpoint):
            log.warning("USB外を指すリンクのため表示しません: %s", html)
            return None
        log.info("表示: %s", html)
        return html

    def _end_session(self) -> None:
        session = self._session
        self._session = None
        if session is None:
            return
        log.info("USBが取り外されました: %s", session.device)
        if session.html is not None:
            self._close_browser()
        self._unmount_quietly(session.mountpoint)

    def _unmount_quietly(self, mountpoint: Path) -> None:
        try:
            self._mounter.unmount(mountpoint)
        except MountError as error:
            log.error("アンマウントに失敗しました: %s", error)

    def _ensure_display(self) -> None:
        """Show the right page, relaunching only when it changed or the browser died."""
        target = self._current_target()
        if target is None:
            self._close_browser()
            return
        if target != self._shown or not self._browser.is_running():
            self._browser.show(target)
            self._shown = target

    def _close_browser(self) -> None:
        if self._shown is None and not self._browser.is_running():
            return
        self._browser.close()
        self._shown = None

    def _current_target(self) -> Path | None:
        if self._session is not None and self._session.html is not None:
            return self._session.html
        return self._config.default_html


def _is_inside(path: Path, root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve())
    except OSError:
        return False
