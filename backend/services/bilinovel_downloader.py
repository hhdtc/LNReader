"""Bilinovel.com novel downloader.

Ports the scraping logic of github.com/montaro2017/bili_novel_packer:
- rate-limited plain HTTP (Chrome TLS impersonation, no cookies)
- catalog parsing with volume grouping
- chapter URL resolution via next/prev chapter probing
- multi-page chapters (url_previous/url_next + #footlink)
- anti-scrape cleanup (junk tags, lazy-load images, unicode host obfuscation)
- paragraph-shuffle restore driven by chapterlog.js template parameters
- EPUB assembly (cover, volumes, images) compatible with LNReader's reader
"""
import base64
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from curl_cffi import requests as crequests

logger = logging.getLogger(__name__)

DOMAIN = "https://www.bilinovel.com"
UA = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)

# Site rate limits (same as the packer): 15 text req/min, 10 image req/min.
TEXT_INTERVAL = 4.0
IMAGE_INTERVAL = 6.0

_CONTENT_SELECTORS = ["#acontent", ".bcontent"]
_REMOVE_SELECTORS = ["div", "ins", "figure", "fig", "br", "script", ".tp", ".bd"]
_JUNK_TAG_RE = re.compile(r"[a-z]\d{4}")
_PAGE_URL_RE = re.compile(r"url_previous:'(.*?)',url_next:'(.*?)'")
_PREV_PAGE_TEXTS = {"上一页", "上一頁"}
_NEXT_PAGE_TEXTS = {"下一页", "下一頁"}
_MAX_PROBE_COUNT = 20
# The site hides image hostnames with a mathematical-bold "b" (U+1D623).
_UNICODE_B = "\U0001d623"

_NOVEL_ID_RE = re.compile(r"(?:linovelib|bilinovel)\.com/(?:novel|download)/(\d+)")
_CHAPTER_ID_RE = re.compile(r"chapterid:'(\d+)'")
_CHAPTERLOG_SRC_RE = re.compile(r'src="([^"]*chapterlog\.js[^"]*)"')


def _chapterlog_version(url: str) -> str:
    """Extract the ?v=... version string from a chapterlog.js URL."""
    m = re.search(r"chapterlog\.js\?v=([\w.]+)", url)
    return m.group(1) if m else "unknown"


class BilinovelError(Exception):
    """Raised when a novel cannot be downloaded."""


@dataclass
class ChapterRef:
    title: str
    href: Optional[str]  # None when the catalog hides the URL (needs probing)


@dataclass
class VolumeRef:
    title: str
    chapters: List[ChapterRef] = field(default_factory=list)


@dataclass
class NovelMeta:
    novel_id: str
    title: str
    author: str
    cover_url: str


class _RateLimiter:
    def __init__(self, interval: float) -> None:
        self._interval = interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._last + self._interval - now
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()


class BilinovelDownloader:
    def __init__(self, text_interval: float = TEXT_INTERVAL,
                 image_interval: float = IMAGE_INTERVAL) -> None:
        self._session = crequests.Session(impersonate="chrome")
        self._session.headers.update({
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9",
            "cookie": "night=0",
            "referer": DOMAIN,
            "user-agent": UA,
        })
        self._text_limiter = _RateLimiter(text_interval)
        self._image_limiter = _RateLimiter(image_interval)
        self._templates: Dict[str, Optional["_ShuffleTemplate"]] = {}

    # ---------- fetching ----------

    def _get(self, url: str) -> str:
        self._text_limiter.wait()
        resp = self._session.get(url)
        if resp.status_code != 200 or not resp.text:
            raise BilinovelError(f"Request failed: {url} (status {resp.status_code})")
        return resp.text

    # ---------- novel & catalog ----------

    def fetch_novel(self, novel_id: str) -> NovelMeta:
        html = self._get(f"{DOMAIN}/novel/{novel_id}.html")
        soup = BeautifulSoup(html, "lxml")
        title_el = soup.select_one(".book-title")
        if not title_el:
            raise BilinovelError(f"Novel page missing title (id {novel_id})")
        title = title_el.get_text(strip=True)
        author_el = soup.select_one(".book-rand-a span")
        author = author_el.get_text(strip=True) if author_el else "Unknown"
        cover_el = soup.select_one(".book-layout img")
        cover_url = cover_el.get("src") if cover_el else ""
        return NovelMeta(novel_id=novel_id, title=title, author=author, cover_url=cover_url)

    def fetch_catalog(self, novel_id: str) -> List[VolumeRef]:
        html = self._get(f"{DOMAIN}/novel/{novel_id}/catalog")
        soup = BeautifulSoup(html, "lxml")
        items = soup.select(".volume-chapters > li")
        if not items:
            raise BilinovelError(f"Catalog empty (id {novel_id})")

        volumes: List[VolumeRef] = []
        current: Optional[VolumeRef] = None
        for li in items:
            classes = li.get("class") or []
            if "chapter-bar" in classes:
                if current is not None:
                    volumes.append(current)
                current = VolumeRef(title=li.get_text(strip=True))
            elif "jsChapter" in classes and current is not None:
                link = li.find("a")
                if not link:
                    continue
                href = link.get("href") or ""
                title = link.get_text(strip=True) or f"Chapter {len(current.chapters) + 1}"
                if href.startswith("javascript"):
                    current.chapters.append(ChapterRef(title=title, href=None))
                else:
                    current.chapters.append(
                        ChapterRef(title=title, href=href if href.startswith("http") else DOMAIN + href)
                    )
        if current is not None:
            volumes.append(current)
        if not volumes:
            raise BilinovelError(f"No chapters found (id {novel_id})")
        return volumes

    # ---------- chapter URL resolution ----------

    def _all_chapters(self, volumes: List[VolumeRef]) -> List[Tuple[int, ChapterRef]]:
        return [(i, ch) for v in volumes for i, ch in enumerate(v.chapters)]

    def resolve_chapter_url(self, volumes: List[VolumeRef], pos: int) -> str:
        """Resolve a hidden chapter URL (catalog href was javascript:).

        Mirrors the packer: probe the next chapter's page for its
        "previous chapter" link; otherwise walk the previous chapter's
        pages to its final page and take the "next chapter" link.
        """
        chapters = self._all_chapters(volumes)

        # Next chapter first.
        if pos + 1 < len(chapters):
            nxt = chapters[pos + 1][1]
            if nxt.href:
                page = self._fetch_page(nxt.href)
                if page.prev_chapter_url:
                    return page.prev_chapter_url

        # Then walk the previous chapter's pages.
        if pos > 0:
            prev = chapters[pos - 1][1]
            if prev.href:
                page = self._fetch_page(prev.href)
                for _ in range(_MAX_PROBE_COUNT):
                    if page.next_page_url:
                        page = self._fetch_page(page.next_page_url)
                        continue
                    if page.next_chapter_url:
                        return page.next_chapter_url
                    break
        raise BilinovelError("Could not resolve chapter URL")

    # ---------- chapter content ----------

    def fetch_chapter(self, url: str, volume_title: str) -> Tuple[str, str, List[str]]:
        """Fetch a full chapter. Returns (title, cleaned_html, image_urls).

        The site's chapterlog.js shuffles each page's paragraphs independently
        (same chapterId seed, per-page DOM), so restore per page — mirroring
        the packer — never across the concatenated chapter.
        """
        page = self._fetch_page(url)
        title = page.title or ""
        parts: List[str] = []
        image_urls: List[str] = []
        chapter_id = page.chapter_id
        script_urls = list(page.script_urls)
        while True:
            content = page.content
            if chapter_id and script_urls:
                content = self._restore_if_shuffled(content, chapter_id, script_urls[0])
            parts.append(content)
            image_urls.extend(page.image_urls)
            if not page.next_page_url:
                break
            page = self._fetch_page(page.next_page_url)
        return title, "".join(parts), image_urls

    def _restore_if_shuffled(self, html: str, chapter_id: int, script_url: str) -> str:
        template = self._get_template(script_url)
        if template is None:
            return html
        params = template.params_for(chapter_id)
        soup = BeautifulSoup(html, "lxml")
        container = soup.new_tag("div")
        # A content fragment parses as a full document (html/body wrapper), so
        # operate on body contents — soup.contents is just [html] and the
        # shuffle only moves direct <p> children.
        body = soup.body or soup
        for node in list(body.contents):
            container.append(node)
        self._restore_paragraphs(container, params)
        return "".join(str(c) for c in container.contents)

    def _fetch_page(self, url: str) -> "_ChapterPage":
        html = self._get(url)
        soup = BeautifulSoup(html, "lxml")

        title = ""
        if "_" not in url:
            atitle = soup.select_one("#atitle")
            if atitle:
                title = atitle.get_text(strip=True)

        content_el = None
        for selector in _CONTENT_SELECTORS:
            content_el = soup.select_one(selector)
            if content_el:
                break
        if content_el is None:
            raise BilinovelError(f"Chapter content missing: {url}")

        # Anti-scrape junk: remove elements whose tag name looks like a marker.
        for el in content_el.find_all(True):
            if _JUNK_TAG_RE.search(el.name or ""):
                el.decompose()
        for sel in _REMOVE_SELECTORS:
            for el in content_el.select(sel):
                el.decompose()

        # Paragraph-shuffle restore happens on the full chapter, but we need
        # the chapter id + script urls from this page.
        chapter_id = None
        m = _CHAPTER_ID_RE.search(html)
        if m:
            chapter_id = int(m.group(1))
        script_urls = [m2.group(1) for m2 in _CHAPTERLOG_SRC_RE.finditer(html)]

        # Navigation.
        nav = _PAGE_URL_RE.search(html)
        prev_url = nav.group(1) if nav else None
        next_url = nav.group(2) if nav else None
        prev_page = next_page = prev_chapter = next_chapter = None
        prevlink = soup.select_one("#footlink a.prevlink")
        nextlink = soup.select_one("#footlink a.nextlink")
        if prevlink is not None and prev_url:
            if prevlink.get_text(strip=True) in _PREV_PAGE_TEXTS:
                prev_page = DOMAIN + prev_url
            else:
                prev_chapter = DOMAIN + prev_url
        if nextlink is not None and next_url:
            if nextlink.get_text(strip=True) in _NEXT_PAGE_TEXTS:
                next_page = DOMAIN + next_url
            else:
                next_chapter = DOMAIN + next_url

        # Images: lazy-load data-src -> src, protocol-relative, junk removal.
        image_urls: List[str] = []
        for img in content_el.find_all("img"):
            src = img.get("data-src") or img.get("src") or ""
            if not src or "<" in src:
                img.decompose()
                continue
            if src.startswith("//"):
                src = "https:" + src
            img["src"] = src
            image_urls.append(src)
            for attr in list(img.attrs):
                if attr not in {"alt", "class", "dir", "height", "id", "ismap",
                                "lang", "longdesc", "style", "title", "usemap",
                                "width", "src", "xml:lang"}:
                    del img[attr]
            img["alt"] = img.get("alt", "")

        return _ChapterPage(
            title=title,
            content=str(content_el.decode_contents()),
            image_urls=image_urls,
            prev_page_url=prev_page,
            next_page_url=next_page,
            prev_chapter_url=prev_chapter,
            next_chapter_url=next_chapter,
            chapter_id=chapter_id,
            script_urls=script_urls,
        )

    # ---------- shuffle restore ----------

    def _get_template(self, script_url: str) -> Optional["_ShuffleTemplate"]:
        if script_url in self._templates:
            return self._templates[script_url]
        full_url = script_url if script_url.startswith("http") else DOMAIN + script_url
        try:
            js = self._get(full_url)
        except Exception as exc:
            # Transient fetch failure: warn instead of silently shipping
            # shuffled paragraphs.
            logger.warning(
                "chapterlog.js fetch failed: %s (%s) — paragraphs will not be restored",
                full_url, exc,
            )
            self._templates[script_url] = None
            return None
        template = _ShuffleTemplate.parse(js)
        if template is None:
            logger.warning(
                "chapterlog.js template unparseable (version %s) — paragraphs will NOT "
                "be restored. Anti-scrape likely changed; diff bili_novel_packer's "
                "bili_novel_chapterlog.dart for the new template: %s",
                _chapterlog_version(full_url), full_url,
            )
        self._templates[script_url] = template
        return template

    @staticmethod
    def _restore_paragraphs(container, params: "_ShuffleParams") -> None:
        children = list(container.children)
        slots: List[int] = []
        paragraphs: List = []
        for i, node in enumerate(children):
            if getattr(node, "name", None) == "p":
                text = node.get_text()
                if re.sub(r"\s+", "", text):
                    slots.append(i)
                    paragraphs.append(node)
        if len(paragraphs) <= params.fixed_length:
            return

        indices = list(range(len(paragraphs)))
        fixed = indices[: params.fixed_length]
        shuffled = indices[params.fixed_length:]
        seed = params.seed
        a, c, mod = params.a, params.c, params.mod
        for i in range(len(shuffled) - 1, 0, -1):
            seed = (seed * a + c) % mod
            j = int(seed / mod * (i + 1))
            shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
        order = fixed + shuffled

        restored = [None] * len(paragraphs)
        for i, target in enumerate(order):
            restored[target] = paragraphs[i]
        for i, slot in enumerate(slots):
            children[slot] = restored[i]
        container.clear()
        for node in children:
            container.append(node)

    # ---------- images ----------

    def download_image(self, src: str) -> bytes:
        if src.startswith("data:image"):
            b64 = src.split(",", 1)[1]
            return base64.b64decode(b64)
        url = src.replace(_UNICODE_B, "b").replace("https://https://", "https://")
        if not url.startswith("http"):
            url = DOMAIN + url
        self._image_limiter.wait()
        resp = self._session.get(url)
        if resp.status_code != 200 or not resp.content:
            raise BilinovelError(f"Image download failed: {url}")
        return resp.content


def build_epub(
    meta: NovelMeta,
    volumes: List[VolumeRef],
    chapters: List[Tuple[str, str]],
    images: List[Tuple[str, bytes]],
    out_path: str,
) -> None:
    """Assemble an EPUB compatible with LNReader's reader pipeline.

    chapters = [(title, html)] in reading order; images = [(src_url, bytes)].
    Image <img src> values in the html are rewritten to ../images/... paths.
    """
    import html as html_mod
    import os

    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier(f"bilinovel-{meta.novel_id}")
    book.set_title(meta.title)
    book.set_language("zh")
    if meta.author and meta.author != "Unknown":
        book.add_author(meta.author)

    cover_bytes = None
    if meta.cover_url:
        try:
            import mimetypes
            from urllib.parse import urlparse

            ext = os.path.splitext(urlparse(meta.cover_url).path)[1] or ".jpg"
            media = mimetypes.guess_type(meta.cover_url)[0] or "image/jpeg"
            # Cover must be re-downloaded without the shared rate limiter
            # unless already present in the images list.
            for src, data in images:
                if src == meta.cover_url:
                    cover_bytes = data
                    break
            if cover_bytes is None:
                downloader = BilinovelDownloader()
                cover_bytes = downloader.download_image(meta.cover_url)
            book.set_cover("cover" + ext, cover_bytes)
        except Exception:
            cover_bytes = None

    # Image registry: src url -> (file_name, media_type)
    image_map: Dict[str, Tuple[str, str]] = {}
    for idx, (src, data) in enumerate(images):
        if src in image_map:
            continue
        ext = ".jpg"
        for cand in (".png", ".gif", ".webp", ".jpeg"):
            if cand in src.lower():
                ext = cand
                break
        file_name = f"images/img{len(image_map) + 1:05d}{ext}"
        media = "image/png" if ext == ".png" else "image/gif" if ext == ".gif" \
            else "image/webp" if ext == ".webp" else "image/jpeg"
        item = epub.EpubItem(
            uid=f"img{len(image_map) + 1:05d}",
            file_name=file_name,
            media_type=media,
            content=data,
        )
        book.add_item(item)
        image_map[src] = (file_name, media)

    chapter_items = []
    for idx, (title, ch_html) in enumerate(chapters):
        # Rewrite image srcs to relative EPUB paths.
        for src, (file_name, _) in image_map.items():
            if src in ch_html:
                ch_html = ch_html.replace(src, "../" + file_name)
        item = epub.EpubHtml(
            title=title or f"Chapter {idx + 1}",
            file_name=f"chapters/ch{idx + 1:05d}.xhtml",
            lang="zh",
        )
        item.content = f"<h1>{html_mod.escape(title or '')}</h1>" + ch_html
        book.add_item(item)
        chapter_items.append(item)

    # TOC grouped by volume (flat volumes group everything under the novel).
    toc: List = []
    pos = 0
    for vol in volumes:
        count = len(vol.chapters)
        group = chapter_items[pos:pos + count]
        pos += count
        if not group:
            continue
        if vol.title and len(volumes) > 1:
            toc.append((vol.title, tuple(group)))
        else:
            toc.extend(group)

    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = chapter_items
    epub.write_epub(out_path, book, {})


@dataclass
class _ChapterPage:
    title: str
    content: str
    image_urls: List[str]
    prev_page_url: Optional[str] = None
    next_page_url: Optional[str] = None
    prev_chapter_url: Optional[str] = None
    next_chapter_url: Optional[str] = None
    chapter_id: Optional[int] = None
    script_urls: List[str] = field(default_factory=list)


# ---------- chapterlog.js template parsing ----------

@dataclass
class _ShuffleParams:
    fixed_length: int
    seed: int
    a: int
    c: int
    mod: int


class _ShuffleTemplate:
    _FIXED_LENGTH_RE = re.compile(r"if\s*\(\s*[_$a-zA-Z0-9]+\s*>\s*")
    _SEED_RE = re.compile(r"=\s*(.+?Number\s*\(\s*chapterId\s*\).+?)\s*;")
    _LCG_RE = re.compile(r"=\s*(\(\s*[_$a-zA-Z0-9]+\s*\*.+?\)\s*%\s*.+?)\s*;")
    _OBF_SEED_RE = re.compile(
        r"var\s+[_$a-zA-Z0-9]+\s*=\s*[^;]*?Number\s*\(\s*[_$a-zA-Z0-9]+\s*\)\s*,\s*([^,)]+?)\s*\)\s*,\s*([^,)]+?)\s*\)\s*,"
    )
    _OBF_LCG_RE = re.compile(
        r"([_$a-zA-Z0-9]+)\s*=\s*[^;]*?\(\s*\1\s*,\s*([^,)]+?)\s*\)\s*,\s*([^,)]+?)\s*\)\s*,\s*([^;)]+?)\s*\)\s*;"
    )

    def __init__(self, fixed_length: int, seed_multiplier: int, seed_offset: int,
                 a: int, c: int, mod: int) -> None:
        self.fixed_length = fixed_length
        self.seed_multiplier = seed_multiplier
        self.seed_offset = seed_offset
        self.a = a
        self.c = c
        self.mod = mod

    def params_for(self, chapter_id: int) -> _ShuffleParams:
        return _ShuffleParams(
            fixed_length=self.fixed_length,
            seed=chapter_id * self.seed_multiplier + self.seed_offset,
            a=self.a,
            c=self.c,
            mod=self.mod,
        )

    @classmethod
    def parse(cls, js: str) -> Optional["_ShuffleTemplate"]:
        plain = cls._parse_plain(js)
        if plain is not None:
            return plain
        return cls._parse_obfuscated(js)

    @classmethod
    def _parse_plain(cls, js: str) -> Optional["_ShuffleTemplate"]:
        m = cls._FIXED_LENGTH_RE.search(js)
        fixed_expr = None
        if m:
            fixed_expr = _extract_trailing_expression(js, m.end(), ")")
        seed_m = cls._SEED_RE.search(js)
        lcg_m = cls._LCG_RE.search(js)
        if fixed_expr is None or not seed_m or not lcg_m:
            return None
        fixed = _eval_int(_strip_outer_parens(fixed_expr))
        seed_params = _parse_seed_expr(seed_m.group(1))
        lcg_params = _parse_lcg_expr(lcg_m.group(1))
        if fixed is None or seed_params is None or lcg_params is None:
            return None
        return cls(fixed, seed_params[0], seed_params[1], lcg_params[0], lcg_params[1], lcg_params[2])

    @classmethod
    def _parse_obfuscated(cls, js: str) -> Optional["_ShuffleTemplate"]:
        seed_params = None
        for m in cls._OBF_SEED_RE.finditer(js):
            mult = _eval_int(m.group(1))
            off = _eval_int(m.group(2))
            if mult is not None and off is not None and mult > 0 and off >= 0:
                seed_params = (mult, off)
                break
        lcg_params = None
        for m in cls._OBF_LCG_RE.finditer(js):
            a = _eval_int(m.group(2))
            c = _eval_int(m.group(3))
            mod = _eval_int(m.group(4))
            if a is not None and c is not None and mod is not None and a > 0 and c >= 0 and mod > a and mod > c:
                lcg_params = (a, c, mod)
                break
        if seed_params is None or lcg_params is None:
            return None
        return cls(20, seed_params[0], seed_params[1], lcg_params[0], lcg_params[1], lcg_params[2])


def _extract_trailing_expression(source: str, start: int, terminator: str) -> Optional[str]:
    depth = 0
    for i in range(start, len(source)):
        ch = source[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0 and terminator == ")":
                return source[start:i].strip()
            depth -= 1
        elif depth == 0 and ch == terminator:
            return source[start:i].strip()
    return None


def _strip_outer_parens(expr: str) -> str:
    value = expr.strip()
    while value.startswith("(") and value.endswith(")"):
        depth = 0
        wraps = True
        for i, ch in enumerate(value):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i != len(value) - 1:
                    wraps = False
                    break
        if not wraps:
            return value
        value = value[1:-1].strip()
    return value


def _parse_seed_expr(expr: str) -> Optional[Tuple[int, int]]:
    offset = _eval_expr_with_vars(expr, {"chapterId": 0})
    one = _eval_expr_with_vars(expr, {"chapterId": 1})
    if offset is None or one is None:
        return None
    return (one - offset, offset)


def _parse_lcg_expr(expr: str) -> Optional[Tuple[int, int, int]]:
    parts = _split_top_level(expr, "%")
    if len(parts) != 2:
        return None
    mod = _eval_int(parts[1])
    if mod is None:
        return None
    left = _strip_outer_parens(parts[0])
    m = re.search(r"[_$a-zA-Z][_$a-zA-Z0-9]*", left)
    if not m:
        return None
    var = m.group(0)
    c = _eval_expr_with_vars(left, {var: 0})
    one = _eval_expr_with_vars(left, {var: 1})
    if c is None or one is None:
        return None
    return (one - c, c, mod)


def _split_top_level(expr: str, op: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    start = 0
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and expr.startswith(op, i):
            parts.append(expr[start:i].strip())
            start = i + len(op)
            i += len(op) - 1
        i += 1
    parts.append(expr[start:].strip())
    return parts


def _eval_expr_with_vars(expr: str, variables: Dict[str, int]) -> Optional[int]:
    normalized = expr
    for key, value in variables.items():
        normalized = re.sub(rf"Number\s*\(\s*{key}\s*\)", str(value), normalized)
        normalized = re.sub(rf"\b{key}\b", str(value), normalized)
    return _eval_int(normalized)


# JS number literal pattern (dec/hex). Once variables are substituted the
# expression must be pure arithmetic; reject anything else.
_SAFE_EXPR_RE = re.compile(r"^[0-9a-fA-FxX+\-*/%^<>&|~()\s]+$")


def _eval_int(expr: Optional[str]) -> Optional[int]:
    if expr is None:
        return None
    expr = expr.strip()
    if not expr or not _SAFE_EXPR_RE.match(expr):
        return None
    try:
        value = _eval_js_arith(expr)
    except Exception:
        return None
    return value


def _eval_js_arith(expr: str) -> int:
    """Evaluate a JS integer expression (^ << >> >>> + - * / % ~, hex literals)."""
    tokens = re.findall(r"0[xX][0-9a-fA-F]+|\d+|<<|>>>|>>|[+\-*/%^<>&|~()]", expr)
    pos = 0

    def peek() -> Optional[str]:
        return tokens[pos] if pos < len(tokens) else None

    def parse_xor() -> int:
        nonlocal pos
        value = parse_shift()
        while peek() == "^":
            pos += 1
            value ^= parse_shift()
        return value

    def parse_shift() -> int:
        nonlocal pos
        value = parse_addsub()
        while True:
            op = peek()
            if op == "<<":
                pos += 1
                value <<= parse_addsub()
            elif op in (">>", ">>>"):
                pos += 1
                value >>= parse_addsub()
            else:
                return value

    def parse_addsub() -> int:
        nonlocal pos
        value = parse_muldiv()
        while True:
            op = peek()
            if op == "+":
                pos += 1
                value += parse_muldiv()
            elif op == "-":
                pos += 1
                value -= parse_muldiv()
            else:
                return value

    def parse_muldiv() -> int:
        nonlocal pos
        value = parse_unary()
        while True:
            op = peek()
            if op == "*":
                pos += 1
                value *= parse_unary()
            elif op == "/":
                pos += 1
                value //= parse_unary()
            elif op == "%":
                pos += 1
                value %= parse_unary()
            else:
                return value

    def parse_unary() -> int:
        nonlocal pos
        op = peek()
        if op == "+":
            pos += 1
            return parse_unary()
        if op == "-":
            pos += 1
            return -parse_unary()
        if op == "~":
            pos += 1
            return ~parse_unary()
        return parse_primary()

    def parse_primary() -> int:
        nonlocal pos
        if peek() == "(":
            pos += 1
            value = parse_xor()
            if peek() != ")":
                raise ValueError("missing paren")
            pos += 1
            return value
        tok = peek()
        if tok is None or not re.fullmatch(r"0[xX][0-9a-fA-F]+|\d+", tok):
            raise ValueError(f"unexpected token {tok}")
        pos += 1
        if tok.lower().startswith("0x"):
            return int(tok[2:], 16)
        return int(tok)

    value = parse_xor()
    if pos != len(tokens):
        raise ValueError("trailing tokens")
    return value
