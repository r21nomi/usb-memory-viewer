import os
import tempfile
import unittest
from pathlib import Path

from usb_viewer.devices import SysfsDeviceScanner


class SysfsDeviceScannerTest(unittest.TestCase):
    """Builds a fake sysfs tree so the scanner can be tested on any OS."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.sys = Path(self._tmp.name) / "sys"
        (self.sys / "class" / "block").mkdir(parents=True)
        self.mounts = Path(self._tmp.name) / "mounts"
        self.mounts.write_text("")
        self.scanner = SysfsDeviceScanner(
            sysfs_root=self.sys, dev_root=Path("/dev"), mounts_file=self.mounts
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _add_disk(self, name: str, bus: str, partitions: int, size: int = 1000) -> None:
        bus_dir = self.sys / "devices" / "platform" / bus / "host0" / "target0:0:0"
        disk_dir = bus_dir / "0:0:0:0" / "block" / name
        disk_dir.mkdir(parents=True)
        (disk_dir / "size").write_text(f"{size}\n")
        (disk_dir / "removable").write_text("1\n")
        os.symlink(disk_dir, self.sys / "class" / "block" / name)
        for index in range(1, partitions + 1):
            part_dir = disk_dir / f"{name}{index}"
            part_dir.mkdir()
            (part_dir / "partition").write_text(f"{index}\n")
            (part_dir / "size").write_text(f"{size}\n")
            os.symlink(part_dir, self.sys / "class" / "block" / f"{name}{index}")

    def test_empty_sysfs_yields_nothing(self) -> None:
        self.assertEqual(self.scanner.list_usb_partitions(), ())

    def test_lists_partitions_of_usb_disk(self) -> None:
        self._add_disk("sda", "xhci-hcd.0/usb1/1-1", partitions=2)
        self.assertEqual(
            self.scanner.list_usb_partitions(), ("/dev/sda1", "/dev/sda2")
        )

    def test_ignores_non_usb_disks(self) -> None:
        self._add_disk("mmcblk0", "fe340000.mmc", partitions=2)
        self._add_disk("nvme0n1", "pcie/0000:01:00.0", partitions=1)
        self.assertEqual(self.scanner.list_usb_partitions(), ())

    def test_disk_without_partition_table_is_returned_as_whole(self) -> None:
        self._add_disk("sdb", "xhci-hcd.0/usb1/1-2", partitions=0)
        self.assertEqual(self.scanner.list_usb_partitions(), ("/dev/sdb",))

    def test_skips_devices_with_no_media(self) -> None:
        self._add_disk("sdc", "xhci-hcd.0/usb1/1-3", partitions=0, size=0)
        self.assertEqual(self.scanner.list_usb_partitions(), ())

    def test_result_is_sorted_across_disks(self) -> None:
        self._add_disk("sdb", "xhci-hcd.0/usb1/1-2", partitions=1)
        self._add_disk("sda", "xhci-hcd.0/usb1/1-1", partitions=1)
        self.assertEqual(
            self.scanner.list_usb_partitions(), ("/dev/sda1", "/dev/sdb1")
        )

    def test_missing_sysfs_root_yields_nothing(self) -> None:
        scanner = SysfsDeviceScanner(
            sysfs_root=self.sys / "nope", dev_root=Path("/dev"), mounts_file=self.mounts
        )
        self.assertEqual(scanner.list_usb_partitions(), ())

    def test_ignores_usb_devices_the_mount_helper_would_reject(self) -> None:
        self._add_disk("sr0", "xhci-hcd.0/usb1/1-4", partitions=0)
        self._add_disk("sda", "xhci-hcd.0/usb1/1-1", partitions=1)
        self.assertEqual(self.scanner.list_usb_partitions(), ("/dev/sda1",))

    def test_skips_partitions_mounted_elsewhere_such_as_a_usb_boot_disk(self) -> None:
        self._add_disk("sda", "xhci-hcd.0/usb1/1-1", partitions=2)
        self._add_disk("sdb", "xhci-hcd.0/usb1/1-2", partitions=1)
        self.mounts.write_text(
            "/dev/sda2 / ext4 rw,noatime 0 0\n"
            "/dev/sda1 /boot/firmware vfat rw 0 0\n"
            "/dev/sdb1 /media/usb-viewer/sdb1 vfat ro 0 0\n"
        )
        self.assertEqual(self.scanner.list_usb_partitions(), ("/dev/sdb1",))

    def test_unreadable_mounts_file_is_treated_as_empty(self) -> None:
        self._add_disk("sda", "xhci-hcd.0/usb1/1-1", partitions=1)
        scanner = SysfsDeviceScanner(
            sysfs_root=self.sys, dev_root=Path("/dev"), mounts_file=self.mounts / "nope"
        )
        self.assertEqual(scanner.list_usb_partitions(), ("/dev/sda1",))


if __name__ == "__main__":
    unittest.main()
