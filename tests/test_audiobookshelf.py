from unittest.mock import patch, MagicMock
import pytest
from app.audiobookshelf import AudiobookshelfClient


def test_abs_headers():
    client = AudiobookshelfClient("http://abs.local:13378", default_token="default_tok", timeout=3.0)
    
    # Default token
    headers = client._get_headers()
    assert headers["Authorization"] == "Bearer default_tok"

    # User-specific token override
    headers_user = client._get_headers("user_specific_tok")
    assert headers_user["Authorization"] == "Bearer user_specific_tok"


@patch("requests.get")
def test_test_connection(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"user": {"username": "admin"}}
    mock_get.return_value = mock_resp

    client = AudiobookshelfClient("http://abs.local:13378", default_token="token123", timeout=3.0)
    res = client.test_connection()

    assert res["success"] is True
    assert res["username"] == "admin"
    mock_get.assert_called_once_with("http://abs.local:13378/api/me", headers={"Content-Type": "application/json", "Authorization": "Bearer token123"}, timeout=3.0)


@patch("requests.get")
def test_resolve_next_book_in_series(mock_get):
    client = AudiobookshelfClient("http://abs.local:13378", default_token="token123", timeout=3.0)

    # Mock series response (3 books in series)
    series_resp = MagicMock()
    series_resp.status_code = 200
    series_resp.json.return_value = {
        "id": "ser_123",
        "name": "Die drei ??? Kids",
        "books": [
            {"id": "book_1", "sequence": "1", "title": "Panik im Paradies"},
            {"id": "book_2", "sequence": "2", "title": "Radio Rocky Beach"},
            {"id": "book_3", "sequence": "3", "title": "Invasion der Fliegen"}
        ]
    }

    # Mock user progress response (Book 1 is finished, Book 2 is not listened yet)
    progress_resp = MagicMock()
    progress_resp.status_code = 200
    progress_resp.json.return_value = {
        "mediaProgress": [
            {"libraryItemId": "book_1", "isFinished": True, "currentTime": 3600, "duration": 3600, "progress": 1.0}
        ]
    }

    def side_effect(url, **kwargs):
        assert kwargs.get("timeout") == 3.0
        if "/api/series/ser_123" in url:
            return series_resp
        elif "/api/me/progress" in url:
            return progress_resp
        return MagicMock(status_code=404)

    mock_get.side_effect = side_effect

    resolved = client.resolve_next_book_in_series("ser_123", user_token="user_tok")

    assert resolved is not None
    assert resolved["series_id"] == "ser_123"
    assert resolved["book_id"] == "book_2"
    assert resolved["title"] == "Radio Rocky Beach"
    assert resolved["sequence"] in [2, "2"]


@patch("requests.get")
def test_search_items_and_series(mock_get):
    client = AudiobookshelfClient("http://abs.local:13378", default_token="token123", timeout=3.0)

    # Mock libraries
    lib_resp = MagicMock()
    lib_resp.status_code = 200
    lib_resp.json.return_value = {"libraries": [{"id": "lib_1", "name": "Audiobooks"}]}

    # Mock search response
    search_resp = MagicMock()
    search_resp.status_code = 200
    search_resp.json.return_value = {
        "book": [
            {
                "libraryItem": {
                    "id": "856d3f32-e693-4e96-9235-a17c62b04229",
                    "media": {
                        "metadata": {
                            "title": "Aladdin",
                            "authorName": "Disney"
                        },
                        "duration": 3600
                    }
                }
            }
        ],
        "series": [
            {
                "series": {
                    "id": "ser_disney",
                    "name": "Disney Classics",
                    "books": [{"id": "b1"}]
                }
            }
        ]
    }

    def side_effect(url, **kwargs):
        if url.endswith("/api/libraries"):
            return lib_resp
        if "/api/libraries/lib_1/search" in url:
            return search_resp
        return MagicMock(status_code=404)

    mock_get.side_effect = side_effect

    # Search items
    items = client.search_items("Aladdin")
    assert len(items) == 1
    assert items[0]["id"] == "856d3f32-e693-4e96-9235-a17c62b04229"
    assert items[0]["title"] == "Aladdin"

    # Search series
    series = client.search_series("Disney")
    assert len(series) == 1
    assert series[0]["id"] == "ser_disney"
    assert series[0]["name"] == "Disney Classics"

