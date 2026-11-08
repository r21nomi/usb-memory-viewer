"""Configuration loading and validation."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

DEFAULT_POLL_INTERVAL_SEC = 0.5
DEFAULT_BROWSER_COMMAND = "chromium"
DEFAULT_MOUNT_HELPER = "/usr/local/bin/usb-viewer-mount"
DEFAULT_UMOUNT_HELPER = "/usr/local/bin/usb-viewer-umount"
ROOT_CONTENT_DIR_ALIASES = ("", "/", ".", "./")


class ConfigError(Exception):
    """Raised when the configuration file is missing or invalid."""


@dataclass(frozen=True)
class Config:
    """Immutable, validated viewer configuration."""

    content_dir: str = ""
    default_html: Path | None = None
    poll_interval_sec: float = DEFAULT_POLL_INTERVAL_SEC
    log_file: Path | None = None
    mount_helper: str = DEFAULT_MOUNT_HELPER
    umount_helper: str = DEFAULT_UMOUNT_HELPER
    browser_command: str = DEFAULT_BROWSER_COMMAND
    browser_extra_args: tuple[str, ...] = ()
    allow_file_access_from_files: bool = True


def load_config(path: Path) -> Config:
    """Read a TOML file and return a validated Config."""
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ConfigError(f"設定ファイルを読めません: {path} ({error})") from error
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise ConfigError(f"設定ファイルの書式が不正です: {path} ({error})") from error
    return parse_config(data)


def parse_config(data: Mapping[str, Any]) -> Config:
    """Build a Config from a parsed TOML mapping, validating every field."""
    mount = _section(data, "mount")
    browser = _section(data, "browser")
    return Config(
        content_dir=_parse_content_dir(data.get("content_dir", "")),
        default_html=_optional_path(data.get("default_html"), "default_html"),
        poll_interval_sec=_parse_interval(
            data.get("poll_interval_sec", DEFAULT_POLL_INTERVAL_SEC)
        ),
        log_file=_optional_path(data.get("log_file"), "log_file"),
        mount_helper=_string(mount.get("mount_helper", DEFAULT_MOUNT_HELPER), "mount.mount_helper"),
        umount_helper=_string(
            mount.get("umount_helper", DEFAULT_UMOUNT_HELPER), "mount.umount_helper"
        ),
        browser_command=_string(
            browser.get("command", DEFAULT_BROWSER_COMMAND), "browser.command"
        ),
        browser_extra_args=_string_tuple(browser.get("extra_args", ()), "browser.extra_args"),
        allow_file_access_from_files=_bool(
            browser.get("allow_file_access_from_files", True),
            "browser.allow_file_access_from_files",
        ),
    )


def _section(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, Mapping):
        raise ConfigError(f"[{key}] はテーブルである必要があります")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{name} は文字列である必要があります")
    return value


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{name} は true / false である必要があります")
    return value


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ConfigError(f"{name} は文字列の配列である必要があります")
    return tuple(_string(item, name) for item in value)


def _optional_path(value: Any, name: str) -> Path | None:
    if value is None:
        return None
    text = _string(value, name)
    if text == "":
        return None
    return Path(text).expanduser()


def _parse_content_dir(value: Any) -> str:
    text = _string(value, "content_dir").strip()
    if text in ROOT_CONTENT_DIR_ALIASES:
        return ""
    normalized = text.strip("/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if ".." in parts:
        raise ConfigError("content_dir に '..' は使えません")
    return "/".join(parts)


def _parse_interval(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError("poll_interval_sec は数値である必要があります")
    if value <= 0:
        raise ConfigError("poll_interval_sec は 0 より大きい必要があります")
    return float(value)
