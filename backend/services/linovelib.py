"""Bilinovel.com (哔哩轻小说) book search.

The site mirrors linovelib.com and — unlike linovelib.com — does not
gate its endpoints behind a Cloudflare clearance cookie; only the Jieqi
"search guard" cookie chain protects the search form. That chain
(/search.html?search_guard=css|js|redeem) is fully replicable with
plain HTTP using Chrome TLS-fingerprint impersonation, so no browser
or user-supplied cookies are needed.
"""
import re
import time
from dataclasses import dataclass, field
from typing import List

from bs4 import BeautifulSoup
from curl_cffi import requests as crequests

SEARCH_URL = "https://www.bilinovel.com/search.html"
BASE_URL = "https://www.bilinovel.com"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)

PLACEHOLDER_COVER = "book-cover-no.svg"

_NOVEL_URL_RE = re.compile(r"(?:linovelib|bilinovel)\.com/(?:novel|download)/\d+")


class LinovelibError(Exception):
    """Raised when the bilinovel search cannot complete."""


@dataclass
class LinovelibBook:
    title: str
    url: str
    author: str = ""
    publisher: str = ""
    cover_url: str = ""
    status: str = ""
    rating: str = ""
    description: str = ""
    tags: str = ""


@dataclass
class LinovelibSearchResult:
    total: int
    books: List[LinovelibBook] = field(default_factory=list)


def _new_session() -> crequests.Session:
    session = crequests.Session(impersonate="chrome")
    session.headers.update(
        {
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
            "user-agent": UA,
        }
    )
    return session


def _run_guard(session: crequests.Session) -> None:
    """Complete the Jieqi search-guard dance.

    The css/js guard endpoints issue jieqiSearchCss / jieqiSearchJs
    (the js value arrives inline in the script body), and a redeem
    request issues jieqiSearchTicket. The search POST then passes.
    """
    page = session.get(SEARCH_URL, headers={"accept": "text/html"})
    if page.status_code != 200 or not page.text:
        raise LinovelibError("Bilinovel search page is unreachable.")

    session.get(
        SEARCH_URL + "?search_guard=css",
        headers={"accept": "text/css,*/*;q=0.1", "referer": SEARCH_URL},
    )

    js = session.get(
        SEARCH_URL + "?search_guard=js",
        headers={"accept": "*/*", "referer": SEARCH_URL},
    )
    match = re.search(r"jieqiSearchJs=([^;\"]+)", js.text)
    if match:
        session.cookies.set(
            "jieqiSearchJs", match.group(1), domain="www.bilinovel.com", path="/"
        )

    session.get(
        f"{SEARCH_URL}?search_guard=redeem&r={int(time.time() * 1000)}",
        headers={"accept": "*/*", "referer": SEARCH_URL},
    )


def _parse_results(html: str) -> LinovelibSearchResult:
    soup = BeautifulSoup(html, "lxml")

    books: List[LinovelibBook] = []
    for item in soup.select("li.book-li"):
        layout = item.select_one("a.book-layout")
        if not layout:
            continue
        href = layout.get("href", "")
        url = href if href.startswith("http") else BASE_URL + href
        # Search also matches authors/translators; only novels are useful here.
        if not _NOVEL_URL_RE.search(url):
            continue

        title_el = item.select_one("h4.book-title")
        title = title_el.get_text(strip=True) if title_el else ""

        img = item.select_one(".book-cover img")
        cover = ""
        if img:
            src = (img.get("data-src") or img.get("src") or "").split("?")[0]
            if PLACEHOLDER_COVER not in src:
                cover = src if src.startswith("http") else BASE_URL + src

        author_el = item.select_one(".book-author")
        author = ""
        if author_el:
            for svg in author_el.select("svg"):
                svg.decompose()
            author = author_el.get_text(strip=True)

        tags = publisher = status = ""
        for em in item.select(".tag-small"):
            cls = em.get("class", [])
            text = em.get_text(strip=True)
            if not text:
                continue
            if "red" in cls:
                tags = text
            elif "yellow" in cls:
                publisher = text
            elif "gray" in cls:
                status = text

        rating_el = item.select_one(".corner em")
        rating = rating_el.get_text(strip=True) if rating_el else ""

        desc_el = item.select_one("p.book-desc")
        description = desc_el.get_text(strip=True) if desc_el else ""

        books.append(
            LinovelibBook(
                title=title,
                url=url,
                author=author,
                publisher=publisher,
                cover_url=cover,
                status=status,
                rating=rating,
                description=description,
                tags=tags,
            )
        )
    return LinovelibSearchResult(total=len(books), books=books)


def search_linovelib(query: str) -> LinovelibSearchResult:
    """Search bilinovel.com. Raises LinovelibError on failure."""
    session = _new_session()
    _run_guard(session)

    resp = session.post(
        SEARCH_URL,
        data={"searchkey": query},
        headers={
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
            "origin": "https://www.bilinovel.com",
            "referer": SEARCH_URL,
        },
        timeout=20,
    )
    if resp.status_code != 200 or not resp.text:
        raise LinovelibError(
            "Bilinovel returned an empty response for the search. "
            "The site may have changed its anti-bot measures."
        )
    return _parse_results(resp.text)
