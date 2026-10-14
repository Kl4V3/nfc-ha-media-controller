"""
Unit tests for Version 0.4.1 Hotfix:
- Dynamic Audiobookshelf series pagination (>100 parts)
- Dynamic library series list pagination
- Library ID fallback resolution
- Version bump verification
"""

import base64
from unittest.mock import patch, MagicMock
import pytest

from app import __version__
from app.audiobookshelf import AudiobookshelfClient


def test_v41_version():
    """Verify system version is bumped to 0.4.1."""
    assert __version__ == "0.4.1"


@patch("requests.get")
def test_series_details_dynamic_pagination_over_100_books(mock_get):
    """
    Simulate a series with 197 books (e.g., John Sinclair).
    Verify that:
    1. First call fetches page 0 (100 books, total=197).
    2. Second call fetches page 1 (97 books).
    3. User has finished books 1-100; resolver successfully picks book 101.
    4. Total books count in resolved payload is 197.
    """
    client = AudiobookshelfClient("http://abs.local:13378", default_token="token_xyz", timeout=3.0)
    series_id = "ser_sinclair"
    library_id = "lib_hoerspiele"
    b64_id = base64.b64encode(series_id.encode()).decode()

    # Generate 197 book items
    page_0_books = [
        {
            "id": f"book_{i}",
            "media": {
                "metadata": {
                    "title": f"Folge {i}: Der Geisterjäger Teil {i}",
                    "series": [{"id": series_id, "name": "John Sinclair-Hörspiel", "sequence": str(i)}]
                }
            }
        }
        for i in range(1, 101)
    ]

    page_1_books = [
        {
            "id": f"book_{i}",
            "media": {
                "metadata": {
                    "title": f"Folge {i}: Der Geisterjäger Teil {i}",
                    "series": [{"id": series_id, "name": "John Sinclair-Hörspiel", "sequence": str(i)}]
                }
            }
        }
        for i in range(101, 198)
    ]

    # Progress: Books 1 to 100 are finished (progress=1.0, isFinished=True)
    media_progress = [
        {"libraryItemId": f"book_{i}", "isFinished": True, "progress": 1.0, "currentTime": 3600, "duration": 3600}
        for i in range(1, 101)
    ]
    # Book 101 has 30% progress
    media_progress.append(
        {"libraryItemId": "book_101", "isFinished": False, "progress": 0.3, "currentTime": 1000, "duration": 3333}
    )

    def side_effect(url, **kwargs):
        if f"/api/libraries/{library_id}/series/{series_id}" in url:
            # Direct series endpoint without books (returns series info with no books)
            m = MagicMock(status_code=200)
            m.json.return_value = {"id": series_id, "name": "John Sinclair-Hörspiel"}
            return m
        elif f"/api/libraries/{library_id}/items?filter=series.{b64_id}" in url:
            if "page=1" in url:
                m = MagicMock(status_code=200)
                m.json.return_value = {
                    "results": page_1_books,
                    "total": 197,
                    "limit": 100,
                    "page": 1
                }
                return m
            else:
                m = MagicMock(status_code=200)
                m.json.return_value = {
                    "results": page_0_books,
                    "total": 197,
                    "limit": 100,
                    "page": 0
                }
                return m
        elif "/api/me/progress" in url:
            m = MagicMock(status_code=200)
            m.json.return_value = {"mediaProgress": media_progress}
            return m
        elif "/api/me" in url:
            m = MagicMock(status_code=200)
            m.json.return_value = {"user": {"username": "test_user"}}
            return m
        return MagicMock(status_code=404)

    mock_get.side_effect = side_effect

    resolved = client.resolve_next_book_in_series(series_id, library_id=library_id, user_token="user_token")

    assert resolved is not None
    assert resolved["series_id"] == series_id
    assert resolved["series_name"] == "John Sinclair-Hörspiel"
    assert resolved["book_id"] == "book_101"
    assert resolved["sequence"] == 101
    assert resolved["total_books"] == 197


@patch("requests.get")
def test_series_details_no_unnecessary_pagination_under_100_books(mock_get):
    """
    Verify that series with <= 100 books only trigger a single items query.
    """
    client = AudiobookshelfClient("http://abs.local:13378", default_token="token_xyz", timeout=3.0)
    series_id = "ser_short"
    library_id = "lib_short"
    b64_id = base64.b64encode(series_id.encode()).decode()

    books = [
        {
            "id": f"book_{i}",
            "media": {
                "metadata": {
                    "title": f"Folge {i}",
                    "series": [{"id": series_id, "name": "Kurze Serie", "sequence": str(i)}]
                }
            }
        }
        for i in range(1, 11)
    ]

    items_calls = []

    def side_effect(url, **kwargs):
        if f"/api/libraries/{library_id}/series/{series_id}" in url:
            m = MagicMock(status_code=200)
            m.json.return_value = {"id": series_id, "name": "Kurze Serie"}
            return m
        elif f"/api/libraries/{library_id}/items?filter=series.{b64_id}" in url:
            items_calls.append(url)
            m = MagicMock(status_code=200)
            m.json.return_value = {
                "results": books,
                "total": 10,
                "limit": 100,
                "page": 0
            }
            return m
        return MagicMock(status_code=404)

    mock_get.side_effect = side_effect

    details = client.get_series_details(series_id, library_id=library_id)

    assert details is not None
    assert len(details["books"]) == 10
    # Exactly one HTTP request to the items filter endpoint
    assert len(items_calls) == 1
    assert "page=" not in items_calls[0]


@patch("requests.get")
def test_get_series_list_pagination(mock_get):
    """
    Verify that get_series_list retrieves all series across pages if a library has > 100 series.
    """
    client = AudiobookshelfClient("http://abs.local:13378", default_token="token_xyz", timeout=3.0)
    library_id = "lib_huge"

    page_0_series = [{"id": f"ser_{i}", "name": f"Serie {i}", "numBooks": 5} for i in range(1, 101)]
    page_1_series = [{"id": f"ser_{i}", "name": f"Serie {i}", "numBooks": 3} for i in range(101, 141)]

    def side_effect(url, **kwargs):
        if f"/api/libraries/{library_id}/series" in url:
            if "page=1" in url:
                m = MagicMock(status_code=200)
                m.json.return_value = {
                    "results": page_1_series,
                    "total": 140,
                    "limit": 100,
                    "page": 1
                }
                return m
            else:
                m = MagicMock(status_code=200)
                m.json.return_value = {
                    "results": page_0_series,
                    "total": 140,
                    "limit": 100,
                    "page": 0
                }
                return m
        return MagicMock(status_code=404)

    mock_get.side_effect = side_effect

    all_series = client.get_series_list(library_id=library_id)

    assert len(all_series) == 140
    assert all_series[0]["id"] == "ser_1"
    assert all_series[-1]["id"] == "ser_140"


@patch("requests.get")
def test_series_details_fallback_library_id(mock_get):
    """
    Verify that when library_id is None, get_series_details queries /api/series/{series_id},
    discovers libraryId from the series metadata, and automatically triggers the filter method.
    """
    client = AudiobookshelfClient("http://abs.local:13378", default_token="token_xyz", timeout=3.0)
    series_id = "ser_auto"
    library_id = "lib_auto_discovered"
    b64_id = base64.b64encode(series_id.encode()).decode()

    def side_effect(url, **kwargs):
        if url == f"http://abs.local:13378/api/series/{series_id}":
            m = MagicMock(status_code=200)
            m.json.return_value = {
                "id": series_id,
                "name": "Auto Discovered Series",
                "libraryId": library_id,
                "books": []  # empty books triggers fallback
            }
            return m
        elif f"/api/libraries/{library_id}/series/{series_id}" in url:
            m = MagicMock(status_code=200)
            m.json.return_value = {"id": series_id, "name": "Auto Discovered Series"}
            return m
        elif f"/api/libraries/{library_id}/items?filter=series.{b64_id}" in url:
            m = MagicMock(status_code=200)
            m.json.return_value = {
                "results": [
                    {
                        "id": "book_discovered_1",
                        "media": {
                            "metadata": {
                                "title": "Buch 1",
                                "series": [{"id": series_id, "name": "Auto Discovered Series", "sequence": "1"}]
                            }
                        }
                    }
                ],
                "total": 1,
                "limit": 100,
                "page": 0
            }
            return m
        return MagicMock(status_code=404)

    mock_get.side_effect = side_effect

    # Call with library_id=None
    details = client.get_series_details(series_id, library_id=None)

    assert details is not None
    assert details["name"] == "Auto Discovered Series"
    assert len(details["books"]) == 1
    assert details["books"][0]["id"] == "book_discovered_1"


@patch("requests.get")
def test_series_details_preserves_name_from_api(mock_get):
    """
    Verify that get_series_details captures the series name from endpoint 1a
    even when falling back to 1b for the books list.
    """
    client = AudiobookshelfClient("http://abs.local:13378", default_token="token_xyz", timeout=3.0)
    series_id = "ser_dorian"
    library_id = "lib_hoerspiele"
    b64_id = base64.b64encode(series_id.encode()).decode()

    def side_effect(url, **kwargs):
        if f"/api/libraries/{library_id}/series/{series_id}" in url:
            # Endpoint 1a has the name, but no books
            m = MagicMock(status_code=200)
            m.json.return_value = {"id": series_id, "name": "Dorian Hunter", "books": []}
            return m
        elif f"/api/libraries/{library_id}/items?filter=series.{b64_id}" in url:
            # Endpoint 1b has items where metadata series may lack the series name
            m = MagicMock(status_code=200)
            m.json.return_value = {
                "results": [
                    {
                        "id": "book_dh_1",
                        "media": {
                            "metadata": {
                                "title": "Im Zeichen des Bösen",
                                "series": []  # empty series metadata inside item
                            }
                        }
                    }
                ],
                "total": 1,
                "limit": 100,
                "page": 0
            }
            return m
        return MagicMock(status_code=404)

    mock_get.side_effect = side_effect

    details = client.get_series_details(series_id, library_id=library_id)

    assert details is not None
    assert details["name"] == "Dorian Hunter"
    assert len(details["books"]) == 1


@patch("requests.get")
def test_search_series_uses_lightweight_series_list(mock_get):
    """
    Verify that search_series queries the lightweight series endpoint (/api/libraries/{id}/series),
    filters locally, and does not hit the heavy /search endpoint.
    """
    client = AudiobookshelfClient("http://abs.local:13378", default_token="token_xyz", timeout=3.0)
    lib_id = "lib_hoerspiele"

    def side_effect(url, **kwargs):
        if url.endswith("/api/libraries"):
            m = MagicMock(status_code=200)
            m.json.return_value = {"libraries": [{"id": lib_id, "name": "Hörspiele"}]}
            return m
        elif f"/api/libraries/{lib_id}/series" in url:
            m = MagicMock(status_code=200)
            m.json.return_value = {
                "results": [
                    {"id": "ser_sinclair", "name": "John Sinclair-Hörspiel", "numBooks": 167},
                    {"id": "ser_other", "name": "Offenbarung 23", "numBooks": 80}
                ],
                "total": 2
            }
            return m
        return MagicMock(status_code=404)

    mock_get.side_effect = side_effect

    results = client.search_series("Sinclair")
    assert len(results) == 1
    assert results[0]["id"] == "ser_sinclair"
    assert results[0]["name"] == "John Sinclair-Hörspiel"
    assert results[0]["num_books"] == 167


@patch("requests.get")
def test_search_items_uses_limit_25(mock_get):
    """
    Verify that search_items limits queries to 25 items.
    """
    client = AudiobookshelfClient("http://abs.local:13378", default_token="token_xyz", timeout=3.0)
    lib_id = "lib_hoerspiele"
    called_urls = []

    def side_effect(url, **kwargs):
        called_urls.append(url)
        if url.endswith("/api/libraries"):
            m = MagicMock(status_code=200)
            m.json.return_value = {"libraries": [{"id": lib_id, "name": "Hörspiele"}]}
            return m
        elif f"/api/libraries/{lib_id}/search" in url:
            m = MagicMock(status_code=200)
            m.json.return_value = {
                "book": [
                    {
                        "libraryItem": {
                            "id": "book_1",
                            "media": {"metadata": {"title": "John Sinclair 001", "authorName": "Jason Dark"}}
                        }
                    }
                ]
            }
            return m
        return MagicMock(status_code=404)

    mock_get.side_effect = side_effect

    results = client.search_items("John")
    assert len(results) == 1
    assert results[0]["id"] == "book_1"
    # Verify limit=25 is used in query
    search_url = [u for u in called_urls if "/search" in u][0]
    assert "limit=25" in search_url


@patch("requests.get")
def test_search_podcasts_targets_podcast_library_only(mock_get):
    """
    Verify that get_podcast_list / search_podcasts only queries libraries with mediaType == 'podcast'.
    """
    client = AudiobookshelfClient("http://abs.local:13378", default_token="token_xyz", timeout=3.0)
    called_urls = []

    def side_effect(url, **kwargs):
        called_urls.append(url)
        if url.endswith("/api/libraries"):
            m = MagicMock(status_code=200)
            m.json.return_value = {
                "libraries": [
                    {"id": "lib_books", "name": "Hörbücher", "mediaType": "book"},
                    {"id": "lib_pods", "name": "Podcasts", "mediaType": "podcast"}
                ]
            }
            return m
        elif "/api/libraries/lib_pods/items" in url:
            m = MagicMock(status_code=200)
            m.json.return_value = {
                "results": [
                    {
                        "id": "pod_1",
                        "mediaType": "podcast",
                        "media": {"metadata": {"title": "Fest & Flauschig", "author": "Jan & Olli"}},
                        "numEpisodes": 200
                    }
                ]
            }
            return m
        return MagicMock(status_code=404)

    mock_get.side_effect = side_effect

    results = client.search_podcasts("Fest")
    assert len(results) == 1
    assert results[0]["id"] == "pod_1"
    # Ensure lib_books was NEVER queried for items
    assert not any("lib_books/items" in u for u in called_urls)
    assert any("lib_pods/items" in u and "minified=1" in u for u in called_urls)


