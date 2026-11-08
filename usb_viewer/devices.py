"""Detects USB block devices by reading sysfs (no udev dependency).

Polling sysfs keeps working when a stick is yanked without "safe removal":
its entries simply disappear from ``/sys/class/block``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_SYSFS_ROOT = Path("/sys")
DEFAULT_DEV_ROOT = Path("/dev")
DEFAULT_MOUNTS_FILE = Path("/proc/self/mounts")
USB_PATH_MARKER = "/usb"
# Only names the mount helper accepts (install/usb-viewer-mount); this leaves
# out USB optical drives (sr0) and similar devices we cannot mount anyway.
DEVICE_NAME_PATTERN = re.compile(r"^sd[a-z]+[0-9]*$")
OWN_MOUNT_BASE = "/media/usb-viewer/"


@dataclass(frozen=True)
class SysfsDeviceScanner:
    sysfs_root: Path = DEFAULT_SYSFS_ROOT
    dev_root: Path = DEFAULT_DEV_ROOT
    mounts_file: Path = DEFAULT_MOUNTS_FILE

    def list_usb_partitions(self) -> tuple[str, ...]:
        """Sorted device nodes of every mountable partition on a USB disk.

        Partitions already mounted elsewhere (for example the system disk when
        booting from USB) are skipped; our own mounts are still reported.
        """
        foreign = self._devices_mounted_elsewhere()
        disks = tuple(entry for entry in self._block_entries() if self._is_usb_disk(entry))
        nodes = tuple(node for disk in disks for node in self._mountable_nodes(disk))
        return tuple(sorted(node for node in nodes if node not in foreign))

    def _block_entries(self) -> tuple[Path, ...]:
        class_block = self.sysfs_root / "class" / "block"
        try:
            return tuple(class_block.iterdir())
        except OSError:
            return ()

    def _is_usb_disk(self, entry: Path) -> bool:
        if not DEVICE_NAME_PATTERN.match(entry.name):
            return False
        if (entry / "partition").exists():
            return False
        try:
            real = entry.resolve()
        except OSError:
            return False
        return USB_PATH_MARKER in real.as_posix()

    def _mountable_nodes(self, disk: Path) -> tuple[str, ...]:
        partitions = tuple(
            sorted(
                child
                for child in _children(disk)
                if DEVICE_NAME_PATTERN.match(child.name) and (child / "partition").exists()
            )
        )
        candidates = partitions if partitions else (disk,)
        return tuple(
            (self.dev_root / candidate.name).as_posix()
            for candidate in candidates
            if _has_media(candidate)
        )

    def _devices_mounted_elsewhere(self) -> frozenset[str]:
        try:
            lines = self.mounts_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return frozenset()
        return frozenset(
            source
            for source, target in (_mount_entry(line) for line in lines)
            if source and not target.startswith(OWN_MOUNT_BASE)
        )


def _mount_entry(line: str) -> tuple[str, str]:
    fields = line.split()
    if len(fields) < 2:
        return ("", "")
    return (fields[0], fields[1])


def _children(directory: Path) -> tuple[Path, ...]:
    try:
        return tuple(child for child in directory.iterdir() if child.is_dir())
    except OSError:
        return ()


def _has_media(entry: Path) -> bool:
    try:
        return int((entry / "size").read_text().strip() or "0") > 0
    except (OSError, ValueError):
        return False
