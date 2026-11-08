import os
import tempfile
import unittest
from pathlib import Path

from usb_viewer.config import parse_config
from usb_viewer.mounter import MountError
from usb_viewer.viewer import MAX_MOUNT_ATTEMPTS, Viewer


class FakeScanner:
    def __init__(self) -> None:
        self.devices: tuple[str, ...] = ()

    def list_usb_partitions(self) -> tuple[str, ...]:
        return self.devices


class FakeMounter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.mounted: dict[str, Path] = {}
        self.unmounted: list[Path] = []
        self.mount_calls: list[str] = []
        self.fail_mount = False
        self.failing_devices: set[str] = set()

    def mount(self, device: str) -> Path:
        self.mount_calls.append(device)
        if self.fail_mount or device in self.failing_devices:
            raise MountError(f"cannot mount {device}")
        mountpoint = self.root / device.replace("/", "_")
        mountpoint.mkdir(parents=True, exist_ok=True)
        self.mounted[device] = mountpoint
        return mountpoint

    def unmount(self, mountpoint: Path) -> None:
        self.unmounted.append(mountpoint)


class FakeBrowser:
    def __init__(self) -> None:
        self.shown: list[Path] = []
        self.current: Path | None = None
        self.close_count = 0
        self.alive = True

    def show(self, html: Path) -> None:
        if self.current is not None:
            self.close_count += 1
        self.shown.append(html)
        self.current = html
        self.alive = True

    def close(self) -> None:
        self.close_count += 1
        self.current = None
        self.alive = False

    def is_running(self) -> bool:
        return self.alive and self.current is not None


class ViewerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.default_html = tmp / "default.html"
        self.default_html.write_text("<html>default</html>")
        self.scanner = FakeScanner()
        self.mounter = FakeMounter(tmp / "mnt")
        self.browser = FakeBrowser()
        self.config = parse_config({"default_html": str(self.default_html)})
        self.viewer = self._make_viewer(self.config)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_viewer(self, config) -> Viewer:
        return Viewer(
            config=config,
            scanner=self.scanner,
            mounter=self.mounter,
            browser=self.browser,
        )

    def _plug(self, device: str, *files: str) -> Path:
        mountpoint = self.mounter.root / device.replace("/", "_")
        mountpoint.mkdir(parents=True, exist_ok=True)
        for name in files:
            target = mountpoint / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("<html></html>")
        self.scanner.devices = (device,)
        return mountpoint

    def test_shows_default_when_no_usb(self) -> None:
        self.viewer.tick()
        self.assertEqual(self.browser.shown, [self.default_html])

    def test_does_not_relaunch_default_every_tick(self) -> None:
        self.viewer.tick()
        self.viewer.tick()
        self.viewer.tick()
        self.assertEqual(len(self.browser.shown), 1)

    def test_shows_index_html_from_usb_root(self) -> None:
        self.viewer.tick()
        mountpoint = self._plug("/dev/sda1", "a.html", "index.html")
        self.viewer.tick()
        self.assertEqual(self.browser.current, mountpoint / "index.html")
        self.assertIn("/dev/sda1", self.mounter.mounted)

    def test_mounts_only_once_while_usb_stays(self) -> None:
        self._plug("/dev/sda1", "index.html")
        self.viewer.tick()
        self.viewer.tick()
        self.viewer.tick()
        self.assertEqual(len(self.browser.shown), 1)

    def test_closes_html_and_unmounts_when_usb_removed(self) -> None:
        mountpoint = self._plug("/dev/sda1", "index.html")
        self.viewer.tick()
        self.scanner.devices = ()
        self.viewer.tick()
        self.assertEqual(self.mounter.unmounted, [mountpoint])
        self.assertGreaterEqual(self.browser.close_count, 1)
        self.assertEqual(self.browser.current, self.default_html)

    def test_reads_html_from_configured_content_dir(self) -> None:
        config = parse_config(
            {"default_html": str(self.default_html), "content_dir": "works"}
        )
        viewer = self._make_viewer(config)
        mountpoint = self._plug("/dev/sda1", "index.html", "works/piece.html")
        viewer.tick()
        self.assertEqual(self.browser.current, mountpoint / "works" / "piece.html")

    def test_usb_without_html_keeps_default_and_does_not_remount(self) -> None:
        self._plug("/dev/sda1", "readme.txt")
        self.viewer.tick()
        self.viewer.tick()
        self.assertEqual(self.browser.current, self.default_html)
        self.assertEqual(len(self.browser.shown), 1)
        self.assertEqual(len(self.mounter.mounted), 1)

    def test_usb_without_html_does_not_flash_default_on_removal(self) -> None:
        self._plug("/dev/sda1", "readme.txt")
        self.viewer.tick()
        self.scanner.devices = ()
        self.viewer.tick()
        self.assertEqual(len(self.browser.shown), 1)
        self.assertEqual(self.browser.close_count, 0)

    def test_removal_closes_html_before_showing_default(self) -> None:
        mountpoint = self._plug("/dev/sda1", "index.html")
        self.viewer.tick()
        self.scanner.devices = ()
        self.viewer.tick()
        self.assertEqual(self.browser.shown, [mountpoint / "index.html", self.default_html])

    def test_mount_failure_falls_back_to_default_without_crashing(self) -> None:
        self.mounter.fail_mount = True
        self._plug("/dev/sda1", "index.html")
        self.viewer.tick()
        self.viewer.tick()
        self.assertEqual(self.browser.current, self.default_html)

    def test_mount_is_retried_a_few_times_then_given_up(self) -> None:
        self.mounter.fail_mount = True
        self._plug("/dev/sda1", "index.html")
        for _ in range(MAX_MOUNT_ATTEMPTS + 3):
            self.viewer.tick()
        self.assertEqual(len(self.mounter.mount_calls), MAX_MOUNT_ATTEMPTS)

    def test_transient_mount_failure_recovers_on_retry(self) -> None:
        self.mounter.fail_mount = True
        mountpoint = self._plug("/dev/sda1", "index.html")
        self.viewer.tick()
        self.mounter.fail_mount = False
        self.viewer.tick()
        self.assertEqual(self.browser.current, mountpoint / "index.html")

    def test_given_up_device_is_retried_after_it_is_replugged(self) -> None:
        self.mounter.fail_mount = True
        self._plug("/dev/sda1", "index.html")
        for _ in range(MAX_MOUNT_ATTEMPTS):
            self.viewer.tick()
        self.scanner.devices = ()
        self.viewer.tick()
        self.mounter.fail_mount = False
        self.scanner.devices = ("/dev/sda1",)
        self.viewer.tick()
        self.assertEqual(len(self.mounter.mount_calls), MAX_MOUNT_ATTEMPTS + 1)
        self.assertIn("/dev/sda1", self.mounter.mounted)

    def test_failing_first_device_does_not_block_the_next_candidate(self) -> None:
        self.mounter.failing_devices = {"/dev/sda1"}
        self._plug("/dev/sda1", "index.html")
        second = self._plug("/dev/sdb1", "index.html")
        self.scanner.devices = ("/dev/sda1", "/dev/sdb1")
        self.viewer.tick()
        self.assertEqual(self.browser.current, second / "index.html")

    def test_symlink_escaping_the_stick_is_not_shown(self) -> None:
        mountpoint = self._plug("/dev/sda1")
        os.symlink(self.default_html.parent / "secret.html", mountpoint / "index.html")
        (self.default_html.parent / "secret.html").write_text("<html>host</html>")
        self.viewer.tick()
        self.assertEqual(self.browser.current, self.default_html)
        self.assertEqual(len(self.browser.shown), 1)

    def test_relaunches_browser_if_it_died(self) -> None:
        mountpoint = self._plug("/dev/sda1", "index.html")
        self.viewer.tick()
        self.browser.alive = False
        self.viewer.tick()
        self.assertEqual(self.browser.shown, [mountpoint / "index.html"] * 2)

    def test_switches_to_second_usb_after_first_removed(self) -> None:
        self._plug("/dev/sda1", "index.html")
        self.viewer.tick()
        second = self._plug("/dev/sdb1", "index.html")
        self.scanner.devices = ("/dev/sdb1",)
        self.viewer.tick()
        self.assertEqual(self.browser.current, second / "index.html")

    def test_no_default_html_configured_shows_nothing(self) -> None:
        viewer = self._make_viewer(parse_config({}))
        viewer.tick()
        self.assertEqual(self.browser.shown, [])
        self.assertIsNone(self.browser.current)

    def test_shutdown_closes_browser_and_unmounts(self) -> None:
        mountpoint = self._plug("/dev/sda1", "index.html")
        self.viewer.tick()
        self.viewer.shutdown()
        self.assertEqual(self.mounter.unmounted, [mountpoint])
        self.assertIsNone(self.browser.current)


if __name__ == "__main__":
    unittest.main()
