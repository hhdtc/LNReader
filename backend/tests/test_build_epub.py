"""Regression tests for EPUB assembly in bilinovel_downloader.build_epub.

Pins the multi-volume TOC bug: ebooklib's NCX/nav writers call `section.title`
on TOC entries; passing a plain string made that resolve to the *uncalled*
str.title method, crashing lxml ("Argument must be bytes or unicode, got
'builtin_function_or_method'") mid-write and leaving a truncated, unreadable
EPUB behind. Sections must be ebooklib Section objects.
"""

import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.bilinovel_downloader import (  # noqa: E402
    ChapterRef,
    NovelMeta,
    VolumeRef,
    build_epub,
)
from services.book_parser import parse_epub  # noqa: E402


def _volumes() -> list:
    return [
        VolumeRef(
            title="第1卷",
            chapters=[ChapterRef(title=f"Ch{i}", href=None) for i in range(9)],
        ),
        VolumeRef(
            title="第2卷",
            chapters=[ChapterRef(title=f"Ch{i}", href=None) for i in range(9, 17)],
        ),
    ]


class BuildEpubTest(unittest.TestCase):
    def _build(self, volumes) -> str:
        meta = NovelMeta(novel_id="1410", title="妹妹人生", author="入间人间", cover_url="")
        chapters = [(f"Ch{i}", f"<p>test content 第{i}章</p>") for i in range(17)]
        path = os.path.join(self.tmpdir, "out.epub")
        build_epub(meta, volumes, chapters, [], path)
        return path

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_multi_volume_toc_builds_valid_epub(self):
        path = self._build(_volumes())
        with zipfile.ZipFile(path) as zf:
            self.assertIsNone(zf.testzip(), "EPUB zip is corrupt")
            names = zf.namelist()
            self.assertIn("EPUB/nav.xhtml", names)
            self.assertIn("EPUB/toc.ncx", names)
    def test_multi_volume_epub_round_trips(self):
        path = self._build(_volumes())
        title, author, chapters, _ = parse_epub(path)
        self.assertEqual(title, "妹妹人生")
        self.assertEqual(author, "入间人间")
        self.assertEqual(len(chapters), 17)

    def test_single_volume_flat_toc_still_builds(self):
        volumes = [
            VolumeRef(
                title="",
                chapters=[ChapterRef(title=f"Ch{i}", href=None) for i in range(17)],
            )
        ]
        path = self._build(volumes)
        with zipfile.ZipFile(path) as zf:
            self.assertIsNone(zf.testzip())


if __name__ == "__main__":
    unittest.main()
