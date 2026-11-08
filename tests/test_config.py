import tempfile
import unittest
from pathlib import Path

from usb_viewer.config import Config, ConfigError, load_config, parse_config


class ParseConfigTest(unittest.TestCase):
    def test_defaults_when_empty(self) -> None:
        config = parse_config({})
        self.assertIsInstance(config, Config)
        self.assertEqual(config.content_dir, "")
        self.assertIsNone(config.default_html)
        self.assertEqual(config.poll_interval_sec, 0.5)
        self.assertEqual(config.browser_command, "chromium")
        self.assertEqual(config.browser_extra_args, ())
        self.assertTrue(config.allow_file_access_from_files)

    def test_browser_file_access_flag(self) -> None:
        config = parse_config({"browser": {"allow_file_access_from_files": False}})
        self.assertFalse(config.allow_file_access_from_files)
        with self.assertRaises(ConfigError):
            parse_config({"browser": {"allow_file_access_from_files": "yes"}})

    def test_reads_all_fields(self) -> None:
        config = parse_config(
            {
                "content_dir": "works/",
                "default_html": "/opt/usb-viewer/default/index.html",
                "poll_interval_sec": 1,
                "log_file": "/tmp/usb-viewer.log",
                "mount": {
                    "mount_helper": "/usr/local/bin/m",
                    "umount_helper": "/usr/local/bin/u",
                },
                "browser": {"command": "chromium-browser", "extra_args": ["--foo"]},
            }
        )
        self.assertEqual(config.content_dir, "works")
        self.assertEqual(
            config.default_html, Path("/opt/usb-viewer/default/index.html")
        )
        self.assertEqual(config.poll_interval_sec, 1.0)
        self.assertEqual(config.log_file, Path("/tmp/usb-viewer.log"))
        self.assertEqual(config.mount_helper, "/usr/local/bin/m")
        self.assertEqual(config.umount_helper, "/usr/local/bin/u")
        self.assertEqual(config.browser_command, "chromium-browser")
        self.assertEqual(config.browser_extra_args, ("--foo",))

    def test_root_content_dir_aliases(self) -> None:
        for value in ("", "/", "./", "."):
            with self.subTest(value=value):
                self.assertEqual(parse_config({"content_dir": value}).content_dir, "")

    def test_rejects_parent_traversal_in_content_dir(self) -> None:
        with self.assertRaises(ConfigError):
            parse_config({"content_dir": "../etc"})

    def test_rejects_non_positive_poll_interval(self) -> None:
        with self.assertRaises(ConfigError):
            parse_config({"poll_interval_sec": 0})

    def test_rejects_wrong_types(self) -> None:
        with self.assertRaises(ConfigError):
            parse_config({"browser": {"extra_args": "--not-a-list"}})
        with self.assertRaises(ConfigError):
            parse_config({"content_dir": 3})

    def test_empty_default_html_means_none(self) -> None:
        self.assertIsNone(parse_config({"default_html": ""}).default_html)

    def test_default_html_expands_user(self) -> None:
        config = parse_config({"default_html": "~/x.html"})
        self.assertEqual(config.default_html, Path("~/x.html").expanduser())


class LoadConfigTest(unittest.TestCase):
    def test_loads_toml_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text('content_dir = "art"\n[browser]\ncommand = "chromium"\n')
            config = load_config(path)
            self.assertEqual(config.content_dir, "art")

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(Path("/definitely/not/here.toml"))

    def test_invalid_toml_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text("this is = = not toml")
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
