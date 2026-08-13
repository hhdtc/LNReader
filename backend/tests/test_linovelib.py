"""Golden-fixture tests for bilinovel.com search.

Fixture captured 2026-08-12 from https://www.bilinovel.com:
- novel_1410.html — detail page for 妹妹人生 (novel 1410), the target of the
  Jieqi search redirect.

The site's Jieqi search redirects to /novel/<id>.html when searchkey exactly
matches one title instead of rendering a results list. These tests pin the
single-result path (and that list pages still parse as lists). They fail
loudly when the site changes its markup or redirect behavior.
"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.linovelib import (  # noqa: E402
    LinovelibError,
    _parse_novel_page,
    search_linovelib,
)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

NOVEL_URL = "https://www.bilinovel.com/novel/1410.html"
SEARCH_URL = "https://www.bilinovel.com/search.html"


def _load(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _stub_session(status: int, text: str, url: str) -> SimpleNamespace:
    return SimpleNamespace(
        post=lambda *a, **k: SimpleNamespace(status_code=status, text=text, url=url)
    )


def _patched_search(stub: SimpleNamespace, query: str):
    with (
        patch("services.linovelib._new_session", return_value=stub),
        patch("services.linovelib._run_guard", lambda s: None),
    ):
        return search_linovelib(query)


class ParseNovelPageTest(unittest.TestCase):
    def test_parses_detail_page_fields(self):
        book = _parse_novel_page(_load("novel_1410.html"), NOVEL_URL)
        self.assertIsNotNone(book)
        self.assertEqual(book.title, "妹妹人生")
        self.assertEqual(book.author, "入间人间")
        self.assertEqual(book.status, "完结")
        self.assertEqual(book.url, NOVEL_URL)
        self.assertEqual(
            book.cover_url,
            "https://www.bilinovel.com/files/article/image/1/1410/1410s.jpg",
        )
        self.assertIn("暑假结束", book.description)

    def test_returns_none_without_title(self):
        self.assertIsNone(_parse_novel_page("<html><body>no book</body></html>", NOVEL_URL))


class SearchRedirectTest(unittest.TestCase):
    def test_exact_title_redirect_becomes_single_result(self):
        stub = _stub_session(200, _load("novel_1410.html"), NOVEL_URL)
        result = _patched_search(stub, "妹妹人生")
        self.assertEqual(result.total, 1)
        self.assertEqual(result.books[0].title, "妹妹人生")
        self.assertEqual(result.books[0].url, NOVEL_URL)
        self.assertEqual(result.books[0].author, "入间人间")

    def test_list_page_still_parses_results(self):
        list_html = (
            '<ol><li class="book-li">'
            '<a class="book-layout" href="/novel/999.html">'
            '<h4 class="book-title">某书</h4>'
            '<div class="book-cover"><img src="https://www.bilinovel.com/files/x.jpg"></div>'
            '</a></li></ol>'
        )
        stub = _stub_session(200, list_html, SEARCH_URL)
        result = _patched_search(stub, "某书")
        self.assertEqual(result.total, 1)
        self.assertEqual(result.books[0].title, "某书")
        self.assertEqual(result.books[0].url, "https://www.bilinovel.com/novel/999.html")

    def test_empty_results_page_returns_zero(self):
        stub = _stub_session(200, "<html><body>no matches</body></html>", SEARCH_URL)
        result = _patched_search(stub, "无此书名xyzabc")
        self.assertEqual(result.total, 0)
        self.assertEqual(result.books, [])

    def test_unparseable_redirect_page_raises(self):
        stub = _stub_session(200, "<html><body>oops</body></html>", NOVEL_URL)
        with self.assertRaises(LinovelibError):
            _patched_search(stub, "妹妹人生")


class FuzzyFallbackTest(unittest.TestCase):
    """The fuzzy fallback fires when the primary search finds nothing."""

    BOOK_ITEM = (
        '<li class="book-li"><a class="book-layout" href="/novel/1410.html">'
        '<h4 class="book-title">妹妹人生</h4>'
        '<div class="book-author">入间人间</div></a></li>'
    )

    def _scripted_session(self, responses: dict) -> SimpleNamespace:
        def post(url, data=None, **kwargs):
            key = (data or {}).get("searchkey", "")
            return responses.get(
                key,
                SimpleNamespace(
                    status_code=200, text="<html>no matches</html>", url=SEARCH_URL
                ),
            )

        return SimpleNamespace(post=post)

    def _search(self, stub: SimpleNamespace, query: str):
        with (
            patch("services.linovelib._new_session", return_value=stub),
            patch("services.linovelib._run_guard", lambda s: None),
        ):
            return search_linovelib(query)

    def test_suggests_author_when_exact_query_misses(self):
        responses = {
            "入见人间": SimpleNamespace(status_code=200, text="<html>no matches</html>", url=SEARCH_URL),
            "入见人": SimpleNamespace(status_code=200, text="<html>no matches</html>", url=SEARCH_URL),
            "见人间": SimpleNamespace(status_code=200, text="<html>no matches</html>", url=SEARCH_URL),
            "人间": SimpleNamespace(
                status_code=200, text=f"<ol>{self.BOOK_ITEM}</ol>", url=SEARCH_URL
            ),
        }
        result = self._search(self._scripted_session(responses), "入见人间")
        self.assertEqual(result.total, 1)
        self.assertEqual(result.books[0].title, "妹妹人生")
        self.assertEqual(result.suggestion, "入间人间")

    def test_no_fallback_when_primary_finds_results(self):
        responses = {
            "妹妹人生": SimpleNamespace(
                status_code=200, text=f"<ol>{self.BOOK_ITEM}</ol>", url=SEARCH_URL
            ),
        }
        result = self._search(self._scripted_session(responses), "妹妹人生")
        self.assertEqual(result.total, 1)
        self.assertIsNone(result.suggestion)

    def test_no_fallback_for_short_query(self):
        calls = []

        def post(url, data=None, **kwargs):
            calls.append((data or {}).get("searchkey"))
            return SimpleNamespace(
                status_code=200, text="<html>no matches</html>", url=SEARCH_URL
            )

        result = self._search(SimpleNamespace(post=post), "人间")
        self.assertEqual(result.total, 0)
        self.assertEqual(calls, ["人间"])

    def test_fallback_discards_dissimilar_results(self):
        item = (
            '<li class="book-li"><a class="book-layout" href="/novel/999.html">'
            '<h4 class="book-title">人间失格</h4>'
            '<div class="book-author">太宰治</div></a></li>'
        )
        responses = {
            "入见人间": SimpleNamespace(status_code=200, text="<html>no matches</html>", url=SEARCH_URL),
            "入见人": SimpleNamespace(status_code=200, text="<html>no matches</html>", url=SEARCH_URL),
            "见人间": SimpleNamespace(status_code=200, text="<html>no matches</html>", url=SEARCH_URL),
            "人间": SimpleNamespace(
                status_code=200, text=f"<ol>{item}</ol>", url=SEARCH_URL
            ),
        }
        result = self._search(self._scripted_session(responses), "入见人间")
        self.assertEqual(result.total, 0)
        self.assertIsNone(result.suggestion)

    def test_fallback_request_budget_is_capped(self):
        calls = []

        def post(url, data=None, **kwargs):
            calls.append((data or {}).get("searchkey"))
            return SimpleNamespace(
                status_code=200, text="<html>no matches</html>", url=SEARCH_URL
            )

        result = self._search(SimpleNamespace(post=post), "一二三四五六七")
        self.assertEqual(result.total, 0)
        self.assertEqual(len(calls), 1 + 6)  # primary + capped fallback


if __name__ == "__main__":
    unittest.main()
