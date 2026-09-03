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

    def search_series(self, query: str, library_id: Optional[str] = None, user_token: Optional[str] = None) -> List[Dict[str, Any]]:
        """Durchsucht Bibliotheken nach Serien anhand eines Suchbegriffs."""
        if not query or not query.strip():
            return self.get_series_list(library_id=library_id, user_token=user_token)

        q_clean = query.strip()
        q_lower = q_clean.lower()
        results = []
        seen_ids = set()
        try:
            libraries = [library_id] if library_id else [lib["id"] for lib in self.get_libraries(user_token)]
            for lib_id in libraries:
                url = f"{self.base_url}/api/libraries/{lib_id}/search?q={requests.utils.quote(q_clean)}"
                resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    series_list = data.get("series") or []
                    for s_entry in series_list:
                        s = s_entry.get("series") if isinstance(s_entry, dict) and "series" in s_entry else s_entry
                        if isinstance(s, dict):
                            s_id = s.get("id")
                            if s_id and s_id not in seen_ids:
                                name = s.get("name") or ""
                                if q_lower in name.lower() or q_lower in s_id.lower():
                                    seen_ids.add(s_id)
                                    books = s.get("books", [])
                                    num_books = s.get("numBooks", len(books))
                                    results.append({
                                        "id": s_id,
                                        "name": name,
                                        "library_id": lib_id,
                                        "num_books": num_books
                                    })
            # Fallback: Falls /search?q= nichts lieferte, durchsuche alle Serien der Bibliotheken
            if not results:
                all_s = self.get_series_list(library_id=library_id, user_token=user_token)
                for s in all_s:
                    s_id = s.get("id")
                    name = s.get("name") or ""
                    if s_id and s_id not in seen_ids and (q_lower in name.lower() or q_lower in s_id.lower()):
                        seen_ids.add(s_id)
                        results.append(s)
        except Exception as e:
            logger.warning(f"Fehler bei ABS-Seriensuche nach '{query}': {e}")
        return results

    def search_items(self, query: str, library_id: Optional[str] = None, user_token: Optional[str] = None) -> List[Dict[str, Any]]:
        """Durchsucht Bibliotheken nach Hörbüchern / Tracks anhand eines Suchbegriffs."""
        if not query or not query.strip():
            return self.get_items_list(library_id=library_id, user_token=user_token, limit=200)

        q_clean = query.strip()
        q_lower = q_clean.lower()
        results = []
        seen_ids = set()
        try:
            libraries = [library_id] if library_id else [lib["id"] for lib in self.get_libraries(user_token)]
            for lib_id in libraries:
                # 1. Direkter Search-Endpunkt /api/libraries/{id}/search?q=...
                url = f"{self.base_url}/api/libraries/{lib_id}/search?q={requests.utils.quote(q_clean)}"
                resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    # ABS gibt book / books / podcast / results zurück
                    raw_entries = (
                        data.get("book")
                        or data.get("books")
                        or data.get("podcast")
                        or data.get("results")
                        or []
                    )
                    for entry in raw_entries:
                        item = entry.get("libraryItem") if isinstance(entry, dict) and "libraryItem" in entry else entry
                        if isinstance(item, dict):
                            item_id = item.get("id")
                            if item_id and item_id not in seen_ids:
                                media = item.get("media", {})
                                meta = media.get("metadata", {}) if isinstance(media, dict) else {}
                                title = meta.get("title") or item.get("name") or "Unbekannt"
                                author = meta.get("authorName") or meta.get("artist") or ""
                                # Prüfe ob Query matcht
                                if q_lower in title.lower() or q_lower in author.lower() or q_lower in item_id.lower():
                                    seen_ids.add(item_id)
                                    results.append({
                                        "id": item_id,
                                        "title": title,
                                        "author": author,
                                        "library_id": lib_id,
                                        "duration": media.get("duration", 0) if isinstance(media, dict) else 0
                                    })

            # 2. Fallback: Falls /search?q= in allen Bibliotheken 0 Treffer ergab, filtere get_items_list mit Limit
            if not results:
                for lib_id in libraries:
                    url_items = f"{self.base_url}/api/libraries/{lib_id}/items?limit=200"
                    resp_items = requests.get(url_items, headers=self._get_headers(user_token), timeout=self.timeout)
                    if resp_items.status_code == 200:
                        data_items = resp_items.json()
                        raw_items = data_items.get("results", []) if isinstance(data_items, dict) else (data_items if isinstance(data_items, list) else [])
                        for item in raw_items:
                            if isinstance(item, dict):
                                item_id = item.get("id")
                                if item_id and item_id not in seen_ids:
                                    media = item.get("media", {})
                                    meta = media.get("metadata", {}) if isinstance(media, dict) else {}
                                    title = meta.get("title") or item.get("name") or "Unbekannt"
                                    author = meta.get("authorName") or meta.get("artist") or ""
                                    # STRIKTES Filtern: nur wenn Suchbegriff im Titel/Autor/ID vorkommt!
                                    if q_lower in title.lower() or q_lower in author.lower() or q_lower in item_id.lower():
                                        seen_ids.add(item_id)
                                        results.append({
                                            "id": item_id,
                                            "title": title,
                                            "author": author,
                                            "library_id": lib_id,
                                            "duration": media.get("duration", 0) if isinstance(media, dict) else 0
                                        })
        except Exception as e:
            logger.warning(f"Fehler bei ABS-Hörbuchsuche nach '{query}': {e}")
        return results

    def get_items_list(self, library_id: Optional[str] = None, user_token: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
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
        """Ruft direkt und zielgerichtet die Bücher einer Serie ab (1-2 gezielte HTTP-Aufrufe)."""
        import base64

        # 1. Direkter Aufruf über Library-ID
        if library_id:
            # 1a. /api/libraries/{lib_id}/series/{series_id}
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
                logger.debug(f"Direkte Bibliotheksabfrage {url} fehlgeschlagen: {e}")

            # 1b. ABS Web-UI Filter-Methode: /api/libraries/{lib_id}/items?filter=series.<base64_id>
            try:
                b64_id = base64.b64encode(series_id.encode()).decode()
                url_filter = f"{self.base_url}/api/libraries/{library_id}/items?filter=series.{b64_id}&limit=100"
                resp = requests.get(url_filter, headers=self._get_headers(user_token), timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_items = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    if raw_items:
                        series_name = "Serie"
                        for item in raw_items:
                            # Suche Seriennamen in Metadaten
                            item_series = item.get("media", {}).get("metadata", {}).get("series") or []
                            if isinstance(item_series, list):
                                for s_entry in item_series:
                                    if isinstance(s_entry, dict) and (s_entry.get("id") == series_id or s_entry.get("name")):
                                        series_name = s_entry.get("name", series_name)
                                        # Sequenz auf Root-Ebene für Sortierung
                                        item["sequence"] = s_entry.get("sequence", item.get("sequence"))
                                        break
                        logger.info(f"ABS-Filterabfrage für Serie '{series_name}' ({series_id}) erfolgreich: {len(raw_items)} Bücher gefunden.")
                        return {
                            "id": series_id,
                            "name": series_name,
                            "books": raw_items
                        }
            except Exception as e:
                logger.debug(f"ABS Filter-Abfrage {url_filter} fehlgeschlagen: {e}")

        # 2. Direkter Aufruf über /api/series/{series_id}
        url = f"{self.base_url}/api/series/{series_id}"
        try:
            resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("series") or data
        except Exception as e:
            logger.debug(f"Direkte Serienabfrage {url} fehlgeschlagen: {e}")

        return None

    def get_user_progress(self, user_token: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Ruft den Hörfortschritt des Nutzers ab.
        Gibt ein Dictionary gemappt nach libraryItemId und mediaItemId zurück.
        """
        url = f"{self.base_url}/api/me/progress"
        progress_map = {}
        user_name = "Default-Key"
        try:
            # Ermittle Benutzername für transparentes Logging
            auth_info = self.test_connection(user_token)
            if auth_info.get("success") and auth_info.get("username"):
                user_name = auth_info.get("username")

            resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                prog_list = []
                if isinstance(data, list):
                    prog_list = data
                elif isinstance(data, dict):
                    prog_list = (
                        data.get("mediaProgress")
                        or data.get("libraryItemProgress")
                        or data.get("mediaItemProgress")
                        or data.get("results")
                        or []
                    )
                for prog in prog_list:
                    for key in ["libraryItemId", "id", "mediaItemId"]:
                        val = prog.get(key)
                        if val:
                            progress_map[str(val)] = prog
                logger.info(f"Hörfortschritt von ABS für Nutzer '{user_name}' geladen ({len(progress_map)} Medien-Referenzen).")
        except Exception as e:
            logger.warning(f"Konnte Hörfortschritt nicht abrufen: {e}")
        return progress_map

    def _extract_sequence(self, item: Dict[str, Any], series_id: Optional[str] = None) -> Optional[float]:
        """Extrahiert die Folgen-/Sequenznummer eines Buchs aus allen ABS-Feldern und Titeln."""
        import re

        # 1. Direkte sequence Felder
        seq = item.get("sequence")
        if seq is not None and str(seq).strip() != "":
            try:
                return float(str(seq).replace(",", "."))
            except (ValueError, TypeError):
                pass

        media = item.get("media", {}) if isinstance(item.get("media"), dict) else {}
        metadata = media.get("metadata", {}) if isinstance(media.get("metadata"), dict) else {}

        # 2. metadata.series Einträge (Liste oder Dict)
        series_entries = metadata.get("series") or []
        if isinstance(series_entries, dict):
            series_entries = [series_entries]
        if isinstance(series_entries, list):
            for s in series_entries:
                if isinstance(s, dict):
                    s_id = s.get("id") or s.get("seriesId")
                    if not series_id or s_id == series_id or len(series_entries) == 1:
                        s_seq = s.get("sequence")
                        if s_seq is not None and str(s_seq).strip() != "":
                            try:
                                return float(str(s_seq).replace(",", "."))
                            except (ValueError, TypeError):
                                pass

        # 3. metadata.seriesSequence / metadata.sequence
        for key in ["seriesSequence", "sequence", "trackNum", "discNum"]:
            val = metadata.get(key)
            if val is not None and str(val).strip() != "":
                try:
                    return float(str(val).replace(",", "."))
                except (ValueError, TypeError):
                    pass

        # 4. Aus dem Titel per Regex extrahieren (z. B. "Folge 2: ...", "02 - ...", "Kids 02 ...", "#2")
        title = metadata.get("title") or item.get("name") or item.get("title") or ""
        m = re.search(r'(?:folge|episode|band|teil|nr\.?|#)\s*0*(\d+(?:[.,]\d+)?)', title, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except (ValueError, TypeError):
                pass

        m2 = re.match(r'^\s*0*(\d+)\s*[-:.\s]', title)
        if m2:
            try:
                return float(m2.group(1))
            except (ValueError, TypeError):
                pass

        return None

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

        # Sequenz für jedes Buch berechnen und anhängen
        for b in books:
            seq_val = self._extract_sequence(b, series_id)
            if seq_val is not None:
                b["_seq_num"] = seq_val
                b["sequence"] = int(seq_val) if seq_val.is_integer() else seq_val
            else:
                b["_seq_num"] = 9999

        # Sortiere strikt nach Folgensequenz
        sorted_books = sorted(books, key=lambda b: b.get("_seq_num", 9999))

        # Nutzer-Fortschritt abrufen
        progress_map = self.get_user_progress(user_token)
        logger.info(f"--- Prüfe Fortschritt für Serie '{series_data.get('name', 'Serie')}' ({len(sorted_books)} Bücher gefunden) ---")

        for idx, b in enumerate(sorted_books):
            book_id = str(b.get("id") or b.get("libraryItemId") or "")
            media_id = str(b.get("media", {}).get("id") or "") if isinstance(b.get("media"), dict) else ""
            b_title = b.get("media", {}).get("metadata", {}).get("title") or b.get("title") or b.get("name") or book_id
            prog = progress_map.get(book_id) or (progress_map.get(media_id) if media_id else None)
            seq_display = b.get("sequence", "?")

            if prog:
                raw_is_fin = prog.get("isFinished")
                is_fin_flag = str(raw_is_fin).lower() in ["true", "1"]
                raw_prog = float(prog.get("progress") or 0)
                # Normalisiere Fortschritt falls ABS Prozentwerte (0-100) statt (0-1) sendet
                p_ratio = (raw_prog / 100.0) if raw_prog > 1.0 else raw_prog
                c_time = float(prog.get("currentTime") or 0)
                dur = float(prog.get("duration") or 0)
                time_ratio = (c_time / dur) if dur > 0 else 0.0

                is_done = is_fin_flag or p_ratio >= 0.98 or time_ratio >= 0.98
                logger.info(f"  [{idx+1}] Folge {seq_display}: '{b_title}' -> {'BEENDET' if is_done else 'IN ARBEIT'} (isFinished={is_fin_flag}, prog={p_ratio:.1%}, time={c_time:.0f}/{dur:.0f}s)")
            else:
                logger.info(f"  [{idx+1}] Folge {seq_display}: '{b_title}' -> UNGEHÖRT (0%)")

        # Erstes unfertiges Buch suchen
        selected_book = None
        for b in sorted_books:
            book_id = str(b.get("id") or b.get("libraryItemId") or "")
            media_id = str(b.get("media", {}).get("id") or "") if isinstance(b.get("media"), dict) else ""
            b_title = b.get("media", {}).get("metadata", {}).get("title") or b.get("title") or b.get("name") or book_id

            prog = progress_map.get(book_id) or (progress_map.get(media_id) if media_id else None)

            if not prog:
                # Noch nie gehört -> erstes ungespieltes Buch
                selected_book = b
                logger.info(f"-> Auswahl: Folge {b.get('sequence', '?')} ('{b_title}') [Noch nie gehört]")
                break

            raw_is_fin = prog.get("isFinished")
            is_finished = str(raw_is_fin).lower() in ["true", "1"]
            raw_prog = float(prog.get("progress") or 0)
            progress_ratio = (raw_prog / 100.0) if raw_prog > 1.0 else raw_prog
            current_time = float(prog.get("currentTime") or 0)
            duration = float(prog.get("duration") or 0)
            time_ratio = (current_time / duration) if duration > 0 else 0.0

            # Buch gilt als beendet wenn isFinished == True oder Fortschritt >= 98%
            if is_finished or progress_ratio >= 0.98 or time_ratio >= 0.98:
                continue

            selected_book = b
            logger.info(f"-> Auswahl: Folge {b.get('sequence', '?')} ('{b_title}') [Unvollendet bei {progress_ratio:.1%}]")
            break

        # Falls alle Bücher bereits gehört wurden, starte wieder mit dem ersten und setze Serie zurück
        if not selected_book:
            selected_book = sorted_books[0]
            logger.info(f"-> Alle Bücher bereits beendet! Starte Serie von vorne mit Folge {selected_book.get('sequence', 1)} und setze Serienfortschritt zurück.")
            self.reset_series_progress(sorted_books, user_token=user_token)

        book_id = selected_book.get("id") or selected_book.get("libraryItemId")
        title = selected_book.get("media", {}).get("metadata", {}).get("title") or selected_book.get("name") or selected_book.get("title") or "Unbekannter Titel"

        logger.info(f"Nächstes Buch aufgelöst: '{title}' (ID: {book_id}, Folge: {selected_book.get('sequence')})")

        return {
            "series_id": series_id,
            "series_name": series_data.get("name", "Serie"),
            "book_id": book_id,
            "title": title,
            "sequence": selected_book.get("sequence"),
            "total_books": len(sorted_books)
        }

    def reset_item_progress(self, item_id: str, user_token: Optional[str] = None) -> bool:
        """
        Setzt den Fortschritt eines einzelnen Buchs in Audiobookshelf auf Anfang (0:00) zurück.
        1. Sucht den aktiven Fortschrittseintrag via GET /api/me/progress und löscht ihn via DELETE /api/me/progress/{prog_id}
        2. Führt zusätzlich einen PATCH /api/me/progress/{item_id} mit currentTime=0, progress=0, isFinished=False aus
        """
        headers = self._get_headers(user_token)
        success = False

        # 1. Bestehenden Progress suchen und per Progress-ID löschen
        try:
            resp = requests.get(f"{self.base_url}/api/me/progress", headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                for p in resp.json().get("mediaProgress", []):
                    if p.get("libraryItemId") == item_id or p.get("id") == item_id:
                        prog_id = p.get("id")
                        del_resp = requests.delete(f"{self.base_url}/api/me/progress/{prog_id}", headers=headers, timeout=self.timeout)
                        if del_resp.status_code in [200, 204]:
                            logger.info(f"Fortschritt für Buch '{item_id}' (Eintrag '{prog_id}') in ABS via DELETE gelöscht.")
                            success = True
        except Exception as e:
            logger.debug(f"DELETE progress via ID für '{item_id}' fehlgeschlagen: {e}")

        # 2. PATCH Versuch (Setzt explizit currentTime=0, progress=0 & isFinished=False)
        try:
            url = f"{self.base_url}/api/me/progress/{item_id}"
            payload = {
                "currentTime": 0,
                "progress": 0,
                "isFinished": False,
                "hideFromContinueListening": False
            }
            resp = requests.patch(url, headers=headers, json=payload, timeout=self.timeout)
            if resp.status_code in [200, 204]:
                logger.info(f"Fortschritt für Buch '{item_id}' in ABS via PATCH auf 0:00 zurückgesetzt.")
                success = True
        except Exception as e:
            logger.debug(f"PATCH progress {url} fehlgeschlagen: {e}")

        return success

    def reset_series_progress(self, books: List[Dict[str, Any]], user_token: Optional[str] = None):
        """
        Setzt den Fortschritt aller Bücher einer Serie in Audiobookshelf auf ungehört zurück.
        """
        logger.info(f"Setze Fortschritt für alle {len(books)} Bücher der Serie in ABS zurück...")
        reset_count = 0
        for b in books:
            book_id = str(b.get("id") or b.get("libraryItemId") or "")
            if book_id:
                if self.reset_item_progress(book_id, user_token=user_token):
                    reset_count += 1
        logger.info(f"Serienfortschritt in ABS zurückgesetzt ({reset_count}/{len(books)} Bücher aktualisiert).")

    def get_podcast_list(self, library_id: Optional[str] = None, user_token: Optional[str] = None) -> List[Dict[str, Any]]:
        """Gibt Podcasts aus einer oder allen Bibliotheken zurück."""
        podcasts = []
        try:
            libraries = self.get_libraries(user_token)
            if library_id:
                target_libs = [library_id]
            else:
                podcast_libs = [lib["id"] for lib in libraries if str(lib.get("mediaType", "")).lower() == "podcast"]
                target_libs = podcast_libs if podcast_libs else [lib["id"] for lib in libraries]

            for lib_id in target_libs:
                url = f"{self.base_url}/api/libraries/{lib_id}/items?limit=100"
                resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_items = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                    for item in raw_items:
                        is_podcast = item.get("mediaType") == "podcast" or (isinstance(item.get("media"), dict) and item.get("media", {}).get("episodes") is not None)
                        if is_podcast or not library_id:
                            meta = item.get("media", {}).get("metadata", {}) if isinstance(item.get("media"), dict) else {}
                            title = meta.get("title") or item.get("name") or "Unbekannter Podcast"
                            author = meta.get("author") or meta.get("authorName") or meta.get("artist") or ""
                            episodes = item.get("media", {}).get("episodes", []) if isinstance(item.get("media"), dict) else []
                            num_episodes = item.get("numEpisodes") or item.get("media", {}).get("numEpisodes") or len(episodes)
                            podcasts.append({
                                "id": item.get("id"),
                                "title": title,
                                "name": title,
                                "author": author,
                                "library_id": lib_id,
                                "num_episodes": num_episodes
                            })
        except Exception as e:
            logger.warning(f"Konnte ABS-Podcasts nicht abrufen: {e}")
        return podcasts

    def search_podcasts(self, query: str, library_id: Optional[str] = None, user_token: Optional[str] = None) -> List[Dict[str, Any]]:
        """Durchsucht Bibliotheken nach Podcasts."""
        if not query or not query.strip():
            return self.get_podcast_list(library_id=library_id, user_token=user_token)

        q_clean = query.strip().lower()
        all_podcasts = self.get_podcast_list(library_id=library_id, user_token=user_token)
        return [
            p for p in all_podcasts
            if q_clean in (p.get("title") or "").lower()
            or q_clean in (p.get("author") or "").lower()
            or q_clean in (p.get("id") or "").lower()
        ]

    def get_podcast_details(self, podcast_id: str, library_id: Optional[str] = None, user_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Ruft Details eines Podcasts ab (inkl. Episodenliste)."""
        item = self.get_item_details(podcast_id, user_token=user_token)
        if item:
            return item

        url = f"{self.base_url}/api/podcasts/{podcast_id}"
        try:
            resp = requests.get(url, headers=self._get_headers(user_token), timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("podcast") or data
        except Exception as e:
            logger.debug(f"Fallback /api/podcasts/{podcast_id} fehlgeschlagen: {e}")

        return None

    def resolve_latest_podcast_episode(self, podcast_id: str, library_id: Optional[str] = None, user_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Ermittelt die aktuellste Folge eines Podcasts, die noch nicht vollständig gehört wurde:
        1. Ruft Podcast-Details und Episodenliste ab.
        2. Sortiert Episoden absteigend nach Veröffentlichungsdatum (neueste zuerst).
        3. Gleicht den Nutzer-Hörfortschritt ab.
        4. Wählt die neueste Folge, die noch nicht 'isFinished' ist.
        5. Wenn alle fertig sind: Wählt die neueste Folge.
        """
        import email.utils
        from datetime import datetime

        podcast_data = self.get_podcast_details(podcast_id, library_id=library_id, user_token=user_token)
        if not podcast_data:
            logger.warning(f"ABS-Podcast '{podcast_id}' konnte nicht gefunden werden.")
            return None

        media = podcast_data.get("media", {}) if isinstance(podcast_data.get("media"), dict) else {}
        meta = media.get("metadata", {}) if isinstance(media.get("metadata"), dict) else {}
        podcast_title = meta.get("title") or podcast_data.get("name") or podcast_data.get("title") or "Podcast"

        episodes = media.get("episodes") or podcast_data.get("episodes") or []
        if not episodes:
            logger.warning(f"Keine Episoden in ABS-Podcast '{podcast_title}' ({podcast_id}) gefunden.")
            return None

        def _get_pub_timestamp(ep: Dict[str, Any]) -> float:
            pub_at = ep.get("publishedAt")
            if pub_at is not None:
                try:
                    val = float(pub_at)
                    return val / 1000.0 if val > 1e11 else val
                except (ValueError, TypeError):
                    pass
            pub_date = ep.get("pubDate")
            if pub_date:
                try:
                    dt = email.utils.parsedate_to_datetime(str(pub_date))
                    return dt.timestamp()
                except Exception:
                    pass
                try:
                    dt = datetime.fromisoformat(str(pub_date).replace("Z", "+00:00"))
                    return dt.timestamp()
                except Exception:
                    pass
            for k in ["episode", "season"]:
                if ep.get(k) is not None:
                    try:
                        return float(ep[k])
                    except (ValueError, TypeError):
                        pass
            return 0.0

        sorted_episodes = sorted(episodes, key=_get_pub_timestamp, reverse=True)
        progress_map = self.get_user_progress(user_token)
        logger.info(f"--- Prüfe Fortschritt für Podcast '{podcast_title}' ({len(sorted_episodes)} Folgen) ---")

        selected_episode = None
        for idx, ep in enumerate(sorted_episodes):
            ep_id = str(ep.get("id") or "")
            ep_title = ep.get("title") or f"Folge {len(sorted_episodes) - idx}"
            prog = progress_map.get(ep_id)

            if not prog:
                selected_episode = ep
                logger.info(f"-> Auswahl (Neueste Folge nie gehört): '{ep_title}' (ID: {ep_id})")
                break

            raw_is_fin = prog.get("isFinished")
            is_finished = str(raw_is_fin).lower() in ["true", "1"]
            raw_prog = float(prog.get("progress") or 0)
            progress_ratio = (raw_prog / 100.0) if raw_prog > 1.0 else raw_prog
            current_time = float(prog.get("currentTime") or 0)
            duration = float(prog.get("duration") or 0)
            time_ratio = (current_time / duration) if duration > 0 else 0.0

            is_done = is_finished or progress_ratio >= 0.98 or time_ratio >= 0.98
            if is_done:
                continue

            selected_episode = ep
            logger.info(f"-> Auswahl (Neueste unvollendete Folge bei {progress_ratio:.1%}): '{ep_title}' (ID: {ep_id})")
            break

        if not selected_episode:
            selected_episode = sorted_episodes[0]
            logger.info(f"-> Alle Folgen bereits beendet. Starte neueste Folge: '{selected_episode.get('title')}'")

        ep_id = str(selected_episode.get("id") or "")
        ep_title = selected_episode.get("title") or "Episode"

        return {
            "podcast_id": podcast_id,
            "podcast_title": podcast_title,
            "episode_id": ep_id,
            "episode_title": ep_title,
            "pub_date": selected_episode.get("pubDate") or selected_episode.get("publishedAt"),
            "total_episodes": len(sorted_episodes)
        }
