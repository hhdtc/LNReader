"""OPDS server + client tests.

- serve: /opds, /opds/catalog, /opds/search, /opds/opensearch.xml,
  /opds/books/<id>/file
- client: remote feed parsing (unit), sources CRUD, and an end-to-end
  browse + acquire against a local ephemeral HTTP server serving the
  repo's real EPUB fixture.
"""
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Isolate the app from the developer's real database before any import.
_TMP = tempfile.mkdtemp(prefix="lnreader_opds_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
os.environ["BOOKS_DIR"] = os.path.join(_TMP, "books")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from database import Book, OpdsSource, SessionLocal  # noqa: E402
from services.opds import parse_opds_feed  # noqa: E402

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_EPUB = os.path.join(
    os.path.dirname(APP_DIR), "testepub", "aozorabunko_43737.epub"
)

_INLINE_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <id>urn:uuid:test-catalog</id>
  <title>Test Catalog</title>
  <subtitle>Fixture feed</subtitle>
  <updated>2026-01-01T00:00:00Z</updated>
  <link rel="self" href="/feed.xml"/>
  <link rel="search" type="application/opensearchdescription+xml" href="/search?q={searchTerms}"/>
  <entry>
    <title>Test Book</title>
    <id>urn:uuid:book-1</id>
    <updated>2026-01-02T00:00:00Z</updated>
    <author><name>Test Author</name></author>
    <dc:language>en</dc:language>
    <summary>A summary</summary>
    <link rel="http://opds-spec.org/image" type="image/jpeg" href="/cover.jpg"/>
    <link rel="http://opds-spec.org/thumbnail" type="image/jpeg" href="/thumb.jpg"/>
    <link rel="http://opds-spec.org/acquisition/open-access" type="application/epub+zip" href="/book.epub"/>
  </entry>
  <entry>
    <title>Category</title>
    <link rel="subsection" type="application/atom+xml;profile=opds-catalog" href="/feed.xml"/>
  </entry>
</feed>
"""


class _StaticHandler(BaseHTTPRequestHandler):
    """Serves feed.xml and book.epub from a prepared directory."""

    def do_GET(self):
        if self.path.split("?")[0] == "/feed.xml":
            with open(os.path.join(self.server.directory, "feed.xml"), "rb") as fh:
                body = fh.read()
            self._respond(200, body, "application/atom+xml")
        elif self.path.split("?")[0] == "/opensearch_feed.xml":
            # Same catalog, but the search link is an OpenSearch description.
            with open(os.path.join(self.server.directory, "feed.xml"), "rb") as fh:
                body = fh.read()
            body = (
                body.decode()
                .replace(
                    f'href="http://127.0.0.1:{self.server.server_address[1]}/feed.xml?q={{searchTerms}}"',
                    'href="/opensearch.xml"',
                )
                .encode()
            )
            self._respond(200, body, "application/atom+xml")
        elif self.path.split("?")[0] == "/opensearch.xml":
            template = (
                f'http://127.0.0.1:{self.server.server_address[1]}/feed.xml?q={{searchTerms}}'
            )
            body = (
                '<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">'
                "<ShortName>Fixture</ShortName><Description>Fixture catalog</Description>"
                '<Url type="application/atom+xml;profile=opds-catalog" '
                f'template="{template}"/>'
                "</OpenSearchDescription>"
            ).encode()
            self._respond(200, body, "application/opensearchdescription+xml")
        elif self.path.startswith("/book.epub"):
            with open(os.path.join(self.server.directory, "book.epub"), "rb") as fh:
                body = fh.read()
            self._respond(200, body, "application/epub+zip")
        elif self.path.startswith("/download/"):
            # Extensionless acquisition link — type carried by Content-Type.
            with open(os.path.join(self.server.directory, "book.epub"), "rb") as fh:
                body = fh.read()
            self._respond(200, body, "application/epub+zip")
        elif self.path.startswith("/cover.jpg"):
            body = b"\xff\xd8\xff\xe0" + b"0" * 64
            self._respond(200, body, "image/jpeg")
        else:
            self._respond(404, b"not found", "text/plain")

    def _respond(self, status: int, body: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class OpdsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server_dir = os.path.join(_TMP, "server")
        os.makedirs(cls.server_dir, exist_ok=True)
        shutil.copyfile(FIXTURE_EPUB, os.path.join(cls.server_dir, "book.epub"))

        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _StaticHandler)
        cls.httpd.directory = cls.server_dir
        cls.httpd.timeout = 30
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

        with open(os.path.join(cls.server_dir, "feed.xml"), "w", encoding="utf-8") as fh:
            fh.write(
                _INLINE_FEED.decode()
                .replace("href=\"/feed.xml\"", f'href="http://127.0.0.1:{cls.port}/feed.xml"')
                .replace("href=\"/search?q={searchTerms}\"", f'href="http://127.0.0.1:{cls.port}/feed.xml?q={{searchTerms}}"')
                .replace("href=\"/cover.jpg\"", f'href="http://127.0.0.1:{cls.port}/cover.jpg"')
                .replace("href=\"/thumb.jpg\"", f'href="http://127.0.0.1:{cls.port}/thumb.jpg"')
                .replace("href=\"/book.epub\"", f'href="http://127.0.0.1:{cls.port}/book.epub"')
            )
        cls.client = TestClient(main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.httpd.shutdown()

    # ---------- unit: parser ----------

    def test_parse_opds_feed_unit(self):
        feed = parse_opds_feed(_INLINE_FEED, "http://catalog.example/feed.xml")
        self.assertEqual(feed.title, "Test Catalog")
        self.assertEqual(feed.subtitle, "Fixture feed")
        self.assertEqual(feed.search_url, "http://catalog.example/search?q={searchTerms}")
        self.assertEqual(len(feed.entries), 2)

        book_entry = feed.entries[0]
        self.assertEqual(book_entry.title, "Test Book")
        self.assertEqual(book_entry.author, "Test Author")
        self.assertEqual(book_entry.language, "en")
        self.assertEqual(book_entry.summary, "A summary")
        self.assertEqual(book_entry.acquisition_url, "http://catalog.example/book.epub")
        self.assertEqual(book_entry.acquisition_type, "application/epub+zip")
        self.assertEqual(book_entry.cover_url, "http://catalog.example/cover.jpg")

        subsection = feed.entries[1]
        self.assertEqual(subsection.subsection_url, "http://catalog.example/feed.xml")
        self.assertIsNone(subsection.acquisition_url)

    def test_parse_rejects_non_atom(self):
        with self.assertRaises(ValueError):
            parse_opds_feed(b"<html><body>hi</body></html>", "http://x/feed")
        with self.assertRaises(ValueError):
            parse_opds_feed(b"not xml at all", "http://x/feed")

    # ---------- server: our library as OPDS ----------

    def test_root_feed(self):
        resp = self.client.get("/opds")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/atom+xml", resp.headers["content-type"])
        self.assertIn("<title>LNreader</title>", resp.text)
        self.assertIn('rel="subsection"', resp.text)
        self.assertIn("/opds/catalog", resp.text)

    def test_opensearch_xml(self):
        resp = self.client.get("/opds/opensearch.xml")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("opensearchdescription", resp.headers["content-type"])
        self.assertIn("{searchTerms}", resp.text)

    def test_catalog_search_and_file(self):
        # Seed library with the fixture EPUB.
        books_dir = os.path.join(_TMP, "books")
        os.makedirs(books_dir, exist_ok=True)
        dest = os.path.join(books_dir, "fixture.epub")
        shutil.copyfile(FIXTURE_EPUB, dest)
        db = SessionLocal()
        book = Book(
            title="Fixture Novel",
            author="Aozora Bunko",
            file_path=dest,
            file_type="epub",
            language="ja",
            total_chapters=1,
        )
        db.add(book)
        db.commit()
        db.refresh(book)
        book_id = book.id
        db.close()

        db = SessionLocal()
        dest2 = os.path.join(books_dir, "fixture2.epub")
        shutil.copyfile(FIXTURE_EPUB, dest2)
        book2 = Book(
            title="Second Novel",
            author="Another Author",
            file_path=dest2,
            file_type="epub",
            language="en",
            total_chapters=1,
        )
        db.add(book2)
        db.commit()
        db.close()

        resp = self.client.get("/opds/catalog")
        self.assertEqual(resp.status_code, 200)
        body = resp.text
        self.assertIn("<title>Fixture Novel</title>", body)
        self.assertIn('<language>ja</language>', body)
        self.assertIn('rel="http://opds-spec.org/acquisition/open-access"', body)
        self.assertIn(f"/opds/books/{book_id}/file", body)
        self.assertIn('type="application/epub+zip"', body)

        resp = self.client.get("/opds/search?q=Fixture")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Fixture Novel", resp.text)

        resp = self.client.get("/opds/search?q=no-such-book-zzz")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("<entry>", resp.text)

        # Pagination: page_size=1 with 1 book → no next link; page 1 has it
        resp = self.client.get("/opds/catalog?page_size=1&page=1")
        self.assertIn('rel="next"', resp.text)

        resp = self.client.get(f"/opds/books/{book_id}/file")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "application/epub+zip")
        self.assertTrue(len(resp.content) > 1000)

    # ---------- client: sources CRUD ----------

    def test_sources_crud(self):
        resp = self.client.post(
            "/api/opds/sources", json={"name": "Fixture", "url": f"http://127.0.0.1:{self.port}/feed.xml"}
        )
        self.assertEqual(resp.status_code, 200)
        source_id = resp.json()["id"]

        resp = self.client.get("/api/opds/sources")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(s["id"] == source_id for s in resp.json()))

        resp = self.client.delete(f"/api/opds/sources/{source_id}")
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get("/api/opds/sources")
        self.assertFalse(any(s["id"] == source_id for s in resp.json()))

    def test_sources_rejects_bad_url(self):
        resp = self.client.post(
            "/api/opds/sources", json={"name": "Bad", "url": "file:///etc/passwd"}
        )
        self.assertEqual(resp.status_code, 400)

    # ---------- client: browse + acquire end-to-end ----------

    def test_browse_remote_feed(self):
        resp = self.client.get("/api/opds/browse", params={"url": f"http://127.0.0.1:{self.port}/feed.xml"})
        self.assertEqual(resp.status_code, 200)
        feed = resp.json()
        self.assertEqual(feed["title"], "Test Catalog")
        self.assertEqual(len(feed["entries"]), 2)
        entry = feed["entries"][0]
        self.assertEqual(entry["title"], "Test Book")
        self.assertEqual(entry["acquisition_type"], "application/epub+zip")
        self.assertTrue(entry["acquisition_url"].startswith(f"http://127.0.0.1:{self.port}"))
        self.assertTrue(entry["cover_url"].startswith(f"http://127.0.0.1:{self.port}"))
        self.assertEqual(feed["entries"][1]["subsection_url"], f"http://127.0.0.1:{self.port}/feed.xml")

    def test_browse_search_template(self):
        resp = self.client.get(
            "/api/opds/browse",
            params={"url": f"http://127.0.0.1:{self.port}/feed.xml", "q": "Test"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("q=Test", resp.json()["url"])

    def test_browse_resolves_opensearch_description(self):
        """A rel=search pointing at an OpenSearch description resolves to its template."""
        url = f"http://127.0.0.1:{self.port}/opensearch_feed.xml"
        resp = self.client.get("/api/opds/browse", params={"url": url})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("{searchTerms}", resp.json()["search_url"])

        resp = self.client.get("/api/opds/browse", params={"url": url, "q": "pulp"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("q=pulp", resp.json()["url"])

    def test_acquire_book(self):
        resp = self.client.get("/api/opds/browse", params={"url": f"http://127.0.0.1:{self.port}/feed.xml"})
        acquire_url = resp.json()["entries"][0]["acquisition_url"]

        resp = self.client.post("/api/opds/acquire", json={"url": acquire_url})
        self.assertEqual(resp.status_code, 200)
        book = resp.json()
        self.assertEqual(book["file_type"], "epub")
        self.assertGreater(book["total_chapters"], 0)
        self.assertTrue(book["title"])

        db = SessionLocal()
        stored = db.query(Book).filter(Book.id == book["id"]).first()
        self.assertIsNotNone(stored)
        self.assertTrue(os.path.exists(stored.file_path))
        db.close()

    def test_acquire_rejects_unsupported_type(self):
        resp = self.client.post(
            "/api/opds/acquire", json={"url": f"http://127.0.0.1:{self.port}/other.pdf"}
        )
        self.assertEqual(resp.status_code, 400)

    def test_acquire_extensionless_url(self):
        """Extensionless OPDS acquisition links resolve via Content-Type."""
        resp = self.client.post(
            "/api/opds/acquire", json={"url": f"http://127.0.0.1:{self.port}/download/42"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["file_type"], "epub")
        self.assertGreater(resp.json()["total_chapters"], 0)

    def test_server_info(self):
        resp = self.client.get("/api/opds/server")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["url"].endswith("/opds"))

    def test_upload_book_writes_file(self):
        """Regression: upload must persist the file before parsing it."""
        with open(FIXTURE_EPUB, "rb") as fh:
            resp = self.client.post(
                "/api/books",
                files={"file": ("regression_upload.epub", fh, "application/epub+zip")},
            )
        self.assertEqual(resp.status_code, 200)
        book = resp.json()
        self.assertEqual(book["file_type"], "epub")
        self.assertGreater(book["total_chapters"], 0)
        db = SessionLocal()
        row = db.query(Book).filter(Book.id == book["id"]).first()
        self.assertTrue(os.path.exists(row.file_path))
        db.close()


if __name__ == "__main__":
    unittest.main()
