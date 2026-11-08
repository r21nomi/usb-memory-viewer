"""Command line entry point: ``python3 -m usb_viewer [--config PATH]``."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

from usb_viewer import __version__
from usb_viewer.browser import BrowserError, ChromiumBrowser
from usb_viewer.config import Config, ConfigError, load_config
from usb_viewer.devices import SysfsDeviceScanner
from usb_viewer.logging_setup import configure_logging
from usb_viewer.mounter import MountError, SudoMounter
from usb_viewer.viewer import Viewer

log = logging.getLogger("usb_viewer")

CONFIG_SEARCH_PATHS = (
    Path("~/.config/usb-viewer/config.toml").expanduser(),
    Path("/etc/usb-viewer/config.toml"),
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        config = _load_config(args.config)
    except ConfigError as error:
        print(f"usb-viewer: {error}", file=sys.stderr)
        return 2
    configure_logging(config.log_file, args.verbose)
    try:
        browser = ChromiumBrowser(
            config.browser_command,
            config.browser_extra_args,
            allow_file_access=config.allow_file_access_from_files,
        )
    except BrowserError as error:
        log.error("%s", error)
        return 2
    mounter = SudoMounter(config.mount_helper, config.umount_helper)
    _clean_up_previous_run(browser, mounter)
    viewer = Viewer(
        config=config, scanner=SysfsDeviceScanner(), mounter=mounter, browser=browser
    )
    try:
        _run_loop(viewer, config.poll_interval_sec)
    finally:
        viewer.shutdown()
        browser.cleanup()
    return 0


def _clean_up_previous_run(browser: ChromiumBrowser, mounter: SudoMounter) -> None:
    browser.kill_stale()
    try:
        mounter.unmount_all()
    except MountError as error:
        log.warning("前回のマウント残骸の掃除に失敗: %s", error)


def _run_loop(viewer: Viewer, interval: float) -> None:
    stop = _StopFlag()
    signal.signal(signal.SIGTERM, stop.request)
    signal.signal(signal.SIGINT, stop.request)
    log.info("usb-viewer %s を開始しました", __version__)
    while not stop.requested:
        try:
            viewer.tick()
        except Exception:  # noqa: BLE001 - keep the kiosk alive at all costs
            log.exception("ポーリング中に予期しないエラーが発生しました")
        time.sleep(interval)
    log.info("停止します")


class _StopFlag:
    def __init__(self) -> None:
        self.requested = False

    def request(self, signum: int, _frame: object) -> None:
        log.info("シグナル %s を受信", signal.Signals(signum).name)
        self.requested = True


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="usb-viewer",
        description="USBメモリ内のHTMLをChromiumでフルスクリーン表示します",
    )
    parser.add_argument("--config", type=Path, help="設定ファイル (TOML) のパス")
    parser.add_argument("-v", "--verbose", action="store_true", help="詳細ログを出力")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def _load_config(explicit: Path | None) -> Config:
    if explicit is not None:
        return load_config(explicit)
    for candidate in CONFIG_SEARCH_PATHS:
        if candidate.is_file():
            return load_config(candidate)
    return Config()


if __name__ == "__main__":
    sys.exit(main())
