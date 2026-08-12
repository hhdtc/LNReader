"""Golden-fixture tests for bilinovel's paragraph-shuffle restore.

Fixtures captured 2026-08-12 from https://www.bilinovel.com:
- chapterlog_v1006c1.82.js  — live chapterlog.js (obfuscated template)
- chapter_307075_p1/p2.html — novel 4971 ch.307075, 11 + 14 paragraphs; both
  pages are under the 20-paragraph shuffle threshold, so the site never
  shuffles them
- chapter_330342_p1/p2.html — novel 5289 ch.330342, 22 + 20 paragraphs; page 1
  exceeds the threshold, so the site actually shuffles it

The site shuffles each page's paragraphs independently (client-side JS, seed
from chapterid), so restore is per page. These tests fail loudly when the
site changes its anti-scrape: parse returning None flags a structural change,
a failed round-trip flags a semantic (shuffle algorithm) change.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bs4 import BeautifulSoup  # noqa: E402

from services.bilinovel_downloader import (  # noqa: E402
    BilinovelDownloader,
    BilinovelError,
    _CHAPTER_ID_RE,
    _CHAPTERLOG_SRC_RE,
    _CONTENT_SELECTORS,
    _JUNK_TAG_RE,
    _REMOVE_SELECTORS,
    _ShuffleTemplate,
)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _load(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _page_content(html: str) -> str:
    """Mirror _fetch_page's cleanup so fixtures feed the same string the
    downloader concatenates."""
    soup = BeautifulSoup(html, "lxml")
    content_el = None
    for selector in _CONTENT_SELECTORS:
        content_el = soup.select_one(selector)
        if content_el:
            break
    assert content_el is not None, "content element missing in fixture"
    for el in content_el.find_all(True):
        if _JUNK_TAG_RE.search(el.name or ""):
            el.decompose()
    for selector in _REMOVE_SELECTORS:
        for el in content_el.select(selector):
            el.decompose()
    return str(content_el.decode_contents())


def _direct_paragraph_texts(html: str):
    """Direct <p> children with non-empty text — the only nodes the shuffle
    moves (non-p nodes stay in place as slot separators)."""
    soup = BeautifulSoup(html, "lxml")
    texts = []
    for node in soup.contents:
        if getattr(node, "name", None) == "p":
            text = node.get_text()
            if re.sub(r"\s+", "", text):
                texts.append(text)
    return texts


def _forward_shuffle(texts, params):
    """The site's shuffle: same LCG Fisher-Yates the restore inverts, applied
    to the compressed shuffled zone (first fixed_length paragraphs stay)."""
    arr = list(texts)
    n = len(arr)
    if n <= params.fixed_length:
        return arr
    zone = arr[params.fixed_length:]
    m = len(zone)
    seed = params.seed
    for i in range(m - 1, 0, -1):
        seed = (seed * params.a + params.c) % params.mod
        j = int(seed / params.mod * (i + 1))
        zone[i], zone[j] = zone[j], zone[i]
    arr[params.fixed_length:] = zone
    return arr


def _restore(page_html: str, js: str, script_url: str) -> str:
    """Run the production restore path offline with an injected template."""
    downloader = BilinovelDownloader()
    downloader._templates[script_url] = _ShuffleTemplate.parse(js)
    chapter_id = int(_CHAPTER_ID_RE.search(page_html).group(1))
    content_html = _page_content(page_html)
    return downloader._restore_if_shuffled(content_html, chapter_id, script_url)


class ChapterlogParseTest(unittest.TestCase):
    def test_parse_extracts_packer_verified_constants(self):
        tpl = _ShuffleTemplate.parse(_load("chapterlog_v1006c1.82.js"))
        self.assertIsNotNone(tpl)
        # Constants independently verified by bili_novel_packer's
        # v1006c1.3-era hardcoded values.
        self.assertEqual(tpl.fixed_length, 20)
        self.assertEqual(tpl.a, 9302)
        self.assertEqual(tpl.c, 49397)
        self.assertEqual(tpl.mod, 233280)
        self.assertEqual(tpl.seed_multiplier, 126)
        self.assertEqual(tpl.seed_offset, 232)

    def test_seed_is_chapter_id_keyed(self):
        tpl = _ShuffleTemplate.parse(_load("chapterlog_v1006c1.82.js"))
        self.assertEqual(tpl.params_for(307075).seed, 307075 * 126 + 232)
        self.assertNotEqual(tpl.params_for(307075).seed, tpl.params_for(307076).seed)

    def test_structural_change_parse_failure(self):
        # What a new template family would look like to the parser: no
        # Number() wrappers -> both plain and obfuscated regexes fail.
        broken = _load("chapterlog_v1006c1.82.js").replace("Number(", "parseInt(")
        self.assertIsNone(_ShuffleTemplate.parse(broken))

    def test_unparseable_template_warns_and_caches(self):
        # Detection: a structural change surfaces as a warning, not silence.
        downloader = BilinovelDownloader()
        downloader._get = lambda url: "var x = 1;"
        url = "/themes/zhmb/js/chapterlog.js?v9999.0"
        with self.assertLogs("services.bilinovel_downloader", level="WARNING") as cm:
            tpl = downloader._get_template(url)
        self.assertIsNone(tpl)
        self.assertTrue(any("unparseable" in line and "v9999.0" in line for line in cm.output))
        # Cached: second call must not re-fetch.
        downloader._get = lambda url: (_ for _ in ()).throw(AssertionError("refetched"))
        self.assertIsNone(downloader._get_template(url))

    def test_fetch_failure_warns(self):
        downloader = BilinovelDownloader()
        downloader._get = lambda url: (_ for _ in ()).throw(BilinovelError("boom"))
        with self.assertLogs("services.bilinovel_downloader", level="WARNING") as cm:
            tpl = downloader._get_template("/themes/zhmb/js/chapterlog.js?v1006c1.82")
        self.assertIsNone(tpl)
        self.assertTrue(any("fetch failed" in line for line in cm.output))


class ChapterlogRestoreTest(unittest.TestCase):
    def setUp(self):
        self.js = _load("chapterlog_v1006c1.82.js")
        self.tpl = _ShuffleTemplate.parse(self.js)
        self.assertIsNotNone(self.tpl)
        self.script_url = "/themes/zhmb/js/chapterlog.js?v1006c1.82"

    def test_roundtrip_shuffled_page(self):
        # Page with 22 paragraphs: the site shuffles it; restore must invert.
        page = _load("chapter_330342_p1.html")
        captured = _page_content(page)
        restored = _restore(page, self.js, self.script_url)

        original = _direct_paragraph_texts(captured)
        result = _direct_paragraph_texts(restored)
        self.assertEqual(len(result), len(original))
        self.assertEqual(sorted(result), sorted(original))  # same multiset
        # First 20 paragraphs are never shuffled.
        self.assertEqual(result[: self.tpl.fixed_length], original[: self.tpl.fixed_length])
        # Round-trip: re-shuffling the restored order reproduces the capture.
        params = self.tpl.params_for(330342)
        self.assertEqual(_forward_shuffle(result, params), original)

    def test_roundtrip_multi_page_chapter(self):
        # Per-page restore across pages must invert each page independently.
        for name in ("chapter_330342_p1.html", "chapter_330342_p2.html"):
            page = _load(name)
            captured = _page_content(page)
            restored = _restore(page, self.js, self.script_url)
            original = _direct_paragraph_texts(captured)
            result = _direct_paragraph_texts(restored)
            params = self.tpl.params_for(330342)
            self.assertEqual(
                _forward_shuffle(result, params), original, msg=f"round-trip failed on {name}"
            )

    def test_short_pages_unchanged(self):
        # Regression: 307075 has 11 + 14 paragraphs — the site shuffles
        # nothing (each page under the threshold). A whole-chapter restore
        # would have moved 5 paragraphs across the concatenation; per-page
        # restore must leave both pages byte-identical.
        for name in ("chapter_307075_p1.html", "chapter_307075_p2.html"):
            page = _load(name)
            captured = _page_content(page)
            restored = _restore(page, self.js, self.script_url)
            self.assertEqual(restored, captured, msg=f"page changed on {name}")

    def test_restore_has_no_document_wrapper(self):
        # Regression: fragment parsing used to wrap output in <html><body>,
        # polluting the EPUB chapter markup.
        page = _load("chapter_330342_p1.html")
        restored = _restore(page, self.js, self.script_url)
        self.assertNotIn("<html", restored)
        self.assertNotIn("<body", restored)

    def test_chapterlog_src_and_id_consistent(self):
        p1 = _load("chapter_330342_p1.html")
        p2 = _load("chapter_330342_p2.html")
        # Both pages carry the same chapterid and script (required for the
        # per-page seed to match).
        self.assertEqual(_CHAPTER_ID_RE.search(p1).group(1),
                         _CHAPTER_ID_RE.search(p2).group(1))
        self.assertEqual(_CHAPTERLOG_SRC_RE.search(p1).group(1),
                         _CHAPTERLOG_SRC_RE.search(p2).group(1))


if __name__ == "__main__":
    unittest.main()
