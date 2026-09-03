"""Text-encoding auto-detection tests.

TXT books from z-library/novel sites are often Shift-JIS (cp932) or
GBK/GB18030; under the old utf-8-with-replacement decode they rendered as
mojibake. decode_text() must pick the right codec (kana-presence scoring)
and parse_txt() must split aozora-style HTML-anchor chapters.
"""
import codecs
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.book_parser import decode_text, parse_txt  # noqa: E402


class DecodeTextTests(unittest.TestCase):
    def test_utf8_passthrough(self):
        text = "日本語のテキストです。"
        self.assertEqual(decode_text(text.encode("utf-8")), text)

    def test_utf8_bom_stripped(self):
        text = "名作の夜"
        self.assertEqual(decode_text(codecs.BOM_UTF8 + text.encode("utf-8")), text)

    def test_utf16_bom(self):
        text = "魔法使いの夜"
        self.assertEqual(decode_text(text.encode("utf-16")), text)

    def test_shift_jis_japanese(self):
        text = "魔法使いの夜は名作である。俺は月の珊瑚を見た。"
        self.assertEqual(decode_text(text.encode("cp932")), text)

    def test_euc_jp_japanese(self):
        text = "魔法使いの夜は名作である。"
        self.assertEqual(decode_text(text.encode("euc-jp")), text)

    def test_gbk_chinese_not_misdetected(self):
        text = "这是一本中文小说，讲月亮与珊瑚的故事。"
        self.assertEqual(decode_text(text.encode("gb18030")), text)

    def test_garbage_falls_back(self):
        data = b"\xff\xff\xff\xff\x00\x01"  # undecodable in any candidate
        decoded = decode_text(data)
        self.assertIsInstance(decoded, str)


class ParseTxtEncodingTests(unittest.TestCase):
    def _write(self, content: bytes) -> str:
        fh = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        fh.write(content)
        fh.close()
        return fh.name

    def test_shift_jis_file_with_kanji_headings(self):
        text = (
            "第1章 始まり\nこれはテストです。\n\n"
            "第2章 夜\nもう一度テストです。\n"
        )
        path = self._write(text.encode("cp932"))
        try:
            title, chapters = parse_txt(path)
            self.assertEqual(len(chapters), 2)
            self.assertEqual(chapters[0]["title"], "第1章")
            self.assertIn("これはテストです", chapters[0]["content"])
            self.assertIn("もう一度テスト", chapters[1]["content"])
        finally:
            os.unlink(path)

    def test_aozora_html_anchor_chapters(self):
        text = (
            "　　<a href=\"#1\">１</a>\n"  # TOC entry — must not split
            "　　<a name=\"1\">１\n\n前書き。\n\n"
            "　　<a name=\"2\">２\n\n本編。\n"
        )
        path = self._write(text.encode("cp932"))
        try:
            title, chapters = parse_txt(path)
            self.assertEqual(len(chapters), 2)
            self.assertEqual(chapters[0]["title"], "１")
            self.assertEqual(chapters[1]["title"], "２")
            self.assertIn("前書き", chapters[0]["content"])
            self.assertIn("本編", chapters[1]["content"])
        finally:
            os.unlink(path)

    def test_gbk_chinese_file(self):
        text = "第一章 开端\n这是中文。\n\n第二章 继续\n这是更多。\n"
        path = self._write(text.encode("gb18030"))
        try:
            title, chapters = parse_txt(path)
            self.assertEqual(len(chapters), 2)
            self.assertIn("这是中文", chapters[0]["content"])
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
