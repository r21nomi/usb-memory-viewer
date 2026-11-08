import tempfile
import unittest
from pathlib import Path

from usb_viewer.html_selector import select_html


class SelectHtmlTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _touch(self, *names: str) -> None:
        for name in names:
            (self.root / name).write_text("<html></html>")

    def test_prefers_index_html(self) -> None:
        self._touch("a.html", "index.html", "z.html")
        self.assertEqual(select_html(self.root), self.root / "index.html")

    def test_index_match_is_case_insensitive(self) -> None:
        self._touch("a.html", "INDEX.HTML")
        self.assertEqual(select_html(self.root), self.root / "INDEX.HTML")

    def test_falls_back_to_alphabetical_first(self) -> None:
        self._touch("zeta.html", "beta.htm", "alpha.html")
        self.assertEqual(select_html(self.root), self.root / "alpha.html")

    def test_alphabetical_order_ignores_case(self) -> None:
        self._touch("b.html", "A.html")
        self.assertEqual(select_html(self.root), self.root / "A.html")

    def test_ignores_non_html_and_directories(self) -> None:
        self._touch("notes.txt", "image.png")
        (self.root / "folder.html").mkdir()
        self.assertIsNone(select_html(self.root))

    def test_ignores_hidden_and_macos_metadata_files(self) -> None:
        self._touch("._index.html", ".hidden.html", "work.html")
        self.assertEqual(select_html(self.root), self.root / "work.html")

    def test_does_not_descend_into_subdirectories(self) -> None:
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "index.html").write_text("")
        self.assertIsNone(select_html(self.root))

    def test_missing_directory_returns_none(self) -> None:
        self.assertIsNone(select_html(self.root / "nope"))


if __name__ == "__main__":
    unittest.main()
