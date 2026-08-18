import logging
import requests
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class AudiobookshelfClient:
    """Client für die Audiobookshelf REST-API mit striktem Timeout und Multi-User-Support."""

    def __init__(self, base_url: str, default_token: str = "", timeout: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.default_token = default_token
        self.timeout = timeout

    def _get_headers(self, user_token: Optional[str] = None) -> Dict[str, str]:
        token = user_token if user_token and user_token.strip() else self.default_token
        headers = {
            "Content-Type": "application/json"
        }
        if token:
            headers["Authorization"] = f"Bearer {token.strip()}"
        return headers

    def test_connection(self, user_token: Optional[str] = None) -> Dict[str, Any]:
        """Prüft die Verbindung zum Audiobookshelf-Server und validiert das Token."""
        url = f"{self.base_url}/api/me"
        try:
            resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
            if resp.status_code == 200:
                user_data = resp.json()
                # Audiobookshelf kann {user: {username}} oder direkt {username} zurückgeben
                username = (
                    user_data.get("user", {}).get("username")
                    or user_data.get("username")
                    or user_data.get("user", {}).get("name")
                    or "Connected"
                )
                return {
                    "success": True,
                    "username": username,
                    "server": self.base_url,
                    "status_code": resp.status_code
                }
            return {
                "success": False,
                "error": f"HTTP {resp.status_code}: {resp.text[:100]}",
                "status_code": resp.status_code
            }
        except requests.exceptions.Timeout:
            logger.error(f"Audiobookshelf Timeout ({self.timeout}s) bei Verbindungsprüfung {url}")
            return {"success": False, "error": f"Timeout nach {self.timeout}s"}
        except Exception as e:
            logger.error(f"Audiobookshelf Verbindungsfehler: {e}")
            return {"success": False, "error": str(e)}

    def get_libraries(self, user_token: Optional[str] = None) -> List[Dict[str, Any]]:
        """Ruft alle verfügbaren Bibliotheken ab."""
        url = f"{self.base_url}/api/libraries"
        try:
            resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                libraries = data.get("libraries", data) if isinstance(data, dict) else data
                if isinstance(libraries, list):
                    return libraries
            logger.warning(f"ABS Libraries Antwort: {resp.status_code} {resp.text[:150]}")
            return []
        except Exception as e:
            logger.warning(f"Konnte ABS-Bibliotheken nicht abrufen: {e}")
            return []

    def get_series_list(self, library_id: Optional[str] = None, user_token: Optional[str] = None) -> List[Dict[str, Any]]:
        """Gibt Serien aus einer oder allen Bibliotheken zurück."""
        all_series = []
        try:
            libraries = [library_id] if library_id else [lib["id"] for lib in self.get_libraries(user_token)]
            for lib_id in libraries:
                url = f"{self.base_url}/api/libraries/{lib_id}/series?limit=100"
                resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    # Audiobookshelf gibt je nach Version 'results', 'series' oder ein Array zurück
                    series_items = []
                    if isinstance(data, dict):
                        series_items = data.get("results") or data.get("series") or []
                    elif isinstance(data, list):
                        series_items = data

                    for s in series_items:
                        books = s.get("books", [])
                        num_books = s.get("numBooks", len(books))
                        all_series.append({
                            "id": s.get("id"),
                            "name": s.get("name"),
                            "library_id": lib_id,
                            "num_books": num_books
                        })
        except Exception as e:
            logger.warning(f"Konnte ABS-Serien nicht abrufen: {e}")
        return all_series

    def get_items_list(self, library_id: Optional[str] = None, user_token: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Gibt einzelne Hörbücher / Tracks aus den Bibliotheken zurück."""
        all_items = []
        try:
            libraries = [library_id] if library_id else [lib["id"] for lib in self.get_libraries(user_token)]
            for lib_id in libraries:
                url = f"{self.base_url}/api/libraries/{lib_id}/items?limit={limit}"
                resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_items = data.get("results", []) if isinstance(data, dict) else data
                    if isinstance(raw_items, list):
                        for item in raw_items:
                            media = item.get("media", {})
                            meta = media.get("metadata", {})
                            title = meta.get("title") or item.get("name") or "Unbekannt"
                            author = meta.get("authorName") or meta.get("artist") or ""
                            all_items.append({
                                "id": item.get("id"),
                                "title": title,
                                "author": author,
                                "library_id": lib_id,
                                "duration": media.get("duration", 0)
                            })
        except Exception as e:
            logger.warning(f"Konnte ABS-Items nicht abrufen: {e}")
        return all_items

    def get_item_details(self, item_id: str, user_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Ruft Details eines einzelnen ABS-Items ab."""
        url = f"{self.base_url}/api/items/{item_id}"
        try:
            resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("libraryItem") or data.get("item") or data
            return None
        except Exception as e:
            logger.warning(f"Fehler beim Abrufen von ABS-Item {item_id}: {e}")
            return None

    def get_series_details(self, series_id: str, library_id: Optional[str] = None, user_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Ruft die Details einer Serie ab inklusive aller Bücher (direkt via library_id oder Auto-Discovery)."""
        # 1. Direkter Endpoint mit bekannter Library-ID (schnellster Pfad)
        if library_id:
            url = f"{self.base_url}/api/libraries/{library_id}/series/{series_id}"
            try:
                resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    series_obj = data.get("series") or data
                    books = series_obj.get("books") or series_obj.get("libraryItems") or []
                    if books:
                        return series_obj
            except Exception as e:
                logger.debug(f"Direkte Bibliotheks-Abfrage {url} fehlgeschlagen: {e}")

        # 2. Direkter Endpoint ohne Library-ID
        url = f"{self.base_url}/api/series/{series_id}"
        try:
            resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                series_obj = data.get("series") or data
                books = series_obj.get("books") or series_obj.get("libraryItems") or []
                if books:
                    return series_obj
        except Exception as e:
            logger.debug(f"Direkte Serienabfrage {url} fehlgeschlagen: {e}")

        # 3. Fallback: Alle Bibliotheken durchsuchen
        try:
            for lib in self.get_libraries(user_token):
                lib_id = lib.get("id")
                if not lib_id or lib_id == library_id:
                    continue
                url = f"{self.base_url}/api/libraries/{lib_id}/series/{series_id}"
                resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    series_obj = data.get("series") or data
                    return series_obj
        except Exception as e:
            logger.warning(f"Bibliotheks-Scan für Serie '{series_id}' fehlgeschlagen: {e}")

        logger.warning(f"Serie '{series_id}' konnte weder direkt noch über Bibliotheken gefunden werden.")
        return None

    def get_user_progress(self, user_token: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Ruft den Hörfortschritt des Nutzers ab.
        Gibt ein Dictionary gemappt nach libraryItemId zurück.
        """
        url = f"{self.base_url}/api/me/progress"
        progress_map = {}
        try:
            resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
            if resp.status_code == 200:
                items = resp.json()
                if isinstance(items, list):
                    for prog in items:
                        item_id = prog.get("libraryItemId") or prog.get("id")
                        if item_id:
                            progress_map[item_id] = prog
                elif isinstance(items, dict):
                    prog_list = items.get("libraryItemProgress") or items.get("mediaItemProgress") or items.get("results") or []
                    for prog in prog_list:
                        item_id = prog.get("libraryItemId") or prog.get("id")
                        if item_id:
                            progress_map[item_id] = prog
        except Exception as e:
            logger.warning(f"Konnte Hörfortschritt nicht abrufen: {e}")
        return progress_map

    def resolve_next_book_in_series(self, series_id: str, library_id: Optional[str] = None, user_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Ermittelt das nächste unvollendete Buch einer Serie für den jeweiligen Nutzer:
        1. Ruft die Buchliste der Serie ab (direkt über library_id oder per Auto-Scan).
        2. Sortiert die Bücher nach Sequenznummer / Index.
        3. Gleicht den Nutzer-Hörfortschritt ab.
        4. Wählt das erste Buch, das nicht als 'isFinished' markiert ist.
        5. Wenn alle fertig sind: Wählt das erste Buch (von vorne) oder das letzte.
        """
        series_data = self.get_series_details(series_id, library_id=library_id, user_token=user_token)
        
        # Fallback: Falls die ID keine Serie sondern ein einzelnes Buch ist
        if not series_data:
            item_data = self.get_item_details(series_id, user_token)
            if item_data:
                title = item_data.get("media", {}).get("metadata", {}).get("title") or item_data.get("name") or "Hörbuch"
                return {
                    "series_id": series_id,
                    "series_name": "Audiobook",
                    "book_id": item_data.get("id") or series_id,
                    "title": title,
                    "sequence": 1,
                    "total_books": 1
                }
            return None

        # Bücher aus der Serie extrahieren
        books = series_data.get("books") or series_data.get("libraryItems") or series_data.get("items") or []

        if not books:
            logger.warning(f"Keine Bücher in ABS-Serie '{series_id}' gefunden.")
            return None

        # Sortiere nach sequence falls vorhanden
        def sort_key(b):
            seq = b.get("sequence")
            if seq is not None:
                try:
                    return float(seq)
                except (ValueError, TypeError):
                    return 9999
            return 9999

        sorted_books = sorted(books, key=sort_key)

        # Nutzer-Fortschritt abrufen
        progress_map = self.get_user_progress(user_token)

        # Erstes unfertiges Buch suchen
        selected_book = None
        for b in sorted_books:
            book_id = b.get("id") or b.get("libraryItemId")
            prog = progress_map.get(book_id)

            if not prog:
                # Noch nie gehört -> erstes ungespieltes Buch
                selected_book = b
                break

            is_finished = prog.get("isFinished", False)
            current_time = float(prog.get("currentTime") or 0)
            duration = float(prog.get("duration") or 0)
            progress_ratio = float(prog.get("progress") or 0)

            # Buch gilt als beendet wenn isFinished == True oder Fortschritt >= 98%
            if is_finished or progress_ratio >= 0.98 or (duration > 0 and (current_time / duration) >= 0.98):
                continue

            selected_book = b
            break

        # Falls alle Bücher bereits gehört wurden, starte wieder mit dem ersten
        if not selected_book:
            selected_book = sorted_books[0]

        book_id = selected_book.get("id") or selected_book.get("libraryItemId")
        title = selected_book.get("media", {}).get("metadata", {}).get("title") or selected_book.get("name") or selected_book.get("title") or "Unbekannter Titel"

        return {
            "series_id": series_id,
            "series_name": series_data.get("name", "Serie"),
            "book_id": book_id,
            "title": title,
            "sequence": selected_book.get("sequence"),
            "total_books": len(sorted_books)
        }
