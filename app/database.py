import sqlite3
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Erstellt eine Verbindung zur SQLite-Datenbank mit Row-Factory."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: str):
    """Initialisiert die Tabellen der Datenbank falls noch nicht vorhanden."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            # Tabelle readers (Mapping von reader_id -> target_player + abs_user_token + abs_provider_prefix)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS readers (
                    reader_id TEXT PRIMARY KEY,
                    target_player TEXT NOT NULL,
                    abs_user_token TEXT,
                    abs_provider_prefix TEXT,
                    notes TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migration falls Spalten in älterer DB-Version fehlen
            try:
                conn.execute("ALTER TABLE readers ADD COLUMN abs_provider_prefix TEXT")
            except Exception:
                pass

            # Tabelle tags (Konfiguration der RFID/NFC-Tags)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    tag_id TEXT PRIMARY KEY,
                    alias TEXT,
                    action_type TEXT,
                    library_id TEXT,
                    target_id TEXT,
                    volume INTEGER,
                    random BOOLEAN DEFAULT 0,
                    extra_params TEXT,
                    last_scanned DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migration falls library_id in älterer DB-Version fehlt
            try:
                conn.execute("ALTER TABLE tags ADD COLUMN library_id TEXT")
            except Exception:
                pass

            # Tabelle scan_history (Protokoll der letzten Scans für UI & Debugging)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag_id TEXT,
                    reader_id TEXT,
                    status TEXT,
                    action_executed TEXT,
                    payload TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Index für schnelle Abfragen der Historie
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_timestamp 
                ON scan_history(timestamp DESC)
            """)
        logger.info(f"Datenbank erfolgreich initialisiert: {db_path}")
    finally:
        conn.close()


# ==============================================================================
# TAGS CRUD
# ==============================================================================

def get_all_tags(db_path: str) -> List[Dict[str, Any]]:
    """Gibt alle registrierten Tags zurück."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute("""
            SELECT tag_id, alias, action_type, library_id, target_id, volume, random, 
                   extra_params, last_scanned, created_at, updated_at
            FROM tags 
            ORDER BY 
                CASE WHEN action_type IS NULL OR action_type = '' THEN 0 ELSE 1 END,
                last_scanned DESC NULLS LAST,
                alias ASC
        """)
        rows = cursor.fetchall()
        tags = []
        for row in rows:
            tag = dict(row)
            tag["random"] = bool(tag["random"])
            if tag["extra_params"]:
                try:
                    tag["extra_params_parsed"] = json.loads(tag["extra_params"])
                except Exception:
                    tag["extra_params_parsed"] = {}
            else:
                tag["extra_params_parsed"] = {}
            tags.append(tag)
        return tags
    finally:
        conn.close()


def get_tag_by_id(db_path: str, tag_id: str) -> Optional[Dict[str, Any]]:
    """Ermittelt ein Tag anhand der ID."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute("SELECT * FROM tags WHERE tag_id = ?", (tag_id,))
        row = cursor.fetchone()
        if not row:
            return None
        tag = dict(row)
        tag["random"] = bool(tag["random"])
        if tag["extra_params"]:
            try:
                tag["extra_params_parsed"] = json.loads(tag["extra_params"])
            except Exception:
                tag["extra_params_parsed"] = {}
        else:
            tag["extra_params_parsed"] = {}
        return tag
    finally:
        conn.close()


def auto_discover_or_update_tag(db_path: str, tag_id: str) -> Dict[str, Any]:
    """
    Sucht das Tag. Wenn es nicht existiert, wird ein leerer Auto-Discovery-Eintrag angelegt.
    Aktualisiert in jedem Fall das 'last_scanned' Feld.
    Gibt das Tag-Objekt zurück und ein Flag 'is_new'.
    """
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.execute("SELECT * FROM tags WHERE tag_id = ?", (tag_id,))
            row = cursor.fetchone()
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

            if not row:
                # Neu anlegen (Auto-Discovery)
                default_alias = f"Unbekannter Tag {tag_id}"
                conn.execute("""
                    INSERT INTO tags (tag_id, alias, action_type, library_id, target_id, volume, random, extra_params, last_scanned, created_at, updated_at)
                    VALUES (?, ?, '', '', '', NULL, 0, '{}', ?, ?, ?)
                """, (tag_id, default_alias, now, now, now))
                logger.info(f"Auto-Discovery: Neuer Tag '{tag_id}' in Datenbank angelegt.")
                return {
                    "tag_id": tag_id,
                    "alias": default_alias,
                    "action_type": "",
                    "library_id": "",
                    "target_id": "",
                    "volume": None,
                    "random": False,
                    "extra_params": "{}",
                    "extra_params_parsed": {},
                    "is_new": True,
                    "last_scanned": now
                }
            else:
                # Vorhandenen Tag aktualisieren (last_scanned)
                conn.execute("UPDATE tags SET last_scanned = ? WHERE tag_id = ?", (now, tag_id))
                tag = dict(row)
                tag["random"] = bool(tag["random"])
                tag["last_scanned"] = now
                tag["is_new"] = False
                if tag["extra_params"]:
                    try:
                        tag["extra_params_parsed"] = json.loads(tag["extra_params"])
                    except Exception:
                        tag["extra_params_parsed"] = {}
                else:
                    tag["extra_params_parsed"] = {}
                return tag
    finally:
        conn.close()


def upsert_tag(db_path: str, tag_data: Dict[str, Any]) -> Dict[str, Any]:
    """Speichert oder aktualisiert ein Tag."""
    conn = get_db_connection(db_path)
    tag_id = tag_data.get("tag_id")
    alias = tag_data.get("alias", "")
    action_type = tag_data.get("action_type", "")
    library_id = tag_data.get("library_id", "")
    target_id = tag_data.get("target_id", "")
    volume = tag_data.get("volume")
    random_flag = 1 if tag_data.get("random") else 0
    extra_params = tag_data.get("extra_params")

    if isinstance(extra_params, dict):
        extra_params_str = json.dumps(extra_params)
    elif isinstance(extra_params, str):
        extra_params_str = extra_params
    else:
        extra_params_str = "{}"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    try:
        with conn:
            conn.execute("""
                INSERT INTO tags (tag_id, alias, action_type, library_id, target_id, volume, random, extra_params, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tag_id) DO UPDATE SET
                    alias = excluded.alias,
                    action_type = excluded.action_type,
                    library_id = excluded.library_id,
                    target_id = excluded.target_id,
                    volume = excluded.volume,
                    random = excluded.random,
                    extra_params = excluded.extra_params,
                    updated_at = excluded.updated_at
            """, (tag_id, alias, action_type, library_id, target_id, volume, random_flag, extra_params_str, now, now))
        return get_tag_by_id(db_path, tag_id)
    finally:
        conn.close()


def delete_tag(db_path: str, tag_id: str) -> bool:
    """Löscht ein Tag aus der Datenbank."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.execute("DELETE FROM tags WHERE tag_id = ?", (tag_id,))
            return cursor.rowcount > 0
    finally:
        conn.close()


# ==============================================================================
# READERS CRUD
# ==============================================================================

def get_all_readers(db_path: str) -> List[Dict[str, Any]]:
    """Gibt alle konfigurierten Reader zurück."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute("SELECT * FROM readers ORDER BY reader_id ASC")
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_reader_by_id(db_path: str, reader_id: str) -> Optional[Dict[str, Any]]:
    """Sucht einen Reader anhand der reader_id."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute("SELECT * FROM readers WHERE reader_id = ?", (reader_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_reader(db_path: str, reader_data: Dict[str, Any]) -> Dict[str, Any]:
    """Speichert oder aktualisiert einen Reader."""
    conn = get_db_connection(db_path)
    reader_id = reader_data.get("reader_id")
    target_player = reader_data.get("target_player", "")
    abs_user_token = reader_data.get("abs_user_token", "")
    abs_provider_prefix = reader_data.get("abs_provider_prefix", "")
    notes = reader_data.get("notes", "")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        with conn:
            conn.execute("""
                INSERT INTO readers (reader_id, target_player, abs_user_token, abs_provider_prefix, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(reader_id) DO UPDATE SET
                    target_player = excluded.target_player,
                    abs_user_token = excluded.abs_user_token,
                    abs_provider_prefix = excluded.abs_provider_prefix,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
            """, (reader_id, target_player, abs_user_token, abs_provider_prefix, notes, now, now))
        return get_reader_by_id(db_path, reader_id)
    finally:
        conn.close()


def delete_reader(db_path: str, reader_id: str) -> bool:
    """Löscht einen Reader."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.execute("DELETE FROM readers WHERE reader_id = ?", (reader_id,))
            return cursor.rowcount > 0
    finally:
        conn.close()


# ==============================================================================
# SCAN HISTORY
# ==============================================================================

def add_scan_history(db_path: str, tag_id: str, reader_id: str, status: str, action_executed: str, payload: str):
    """Fügt einen Eintrag in die Scan-Historie ein."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO scan_history (tag_id, reader_id, status, action_executed, payload)
                VALUES (?, ?, ?, ?, ?)
            """, (tag_id, reader_id, status, action_executed, payload))
            # Halte maximal die letzten 200 Einträge
            conn.execute("""
                DELETE FROM scan_history 
                WHERE id NOT IN (
                    SELECT id FROM scan_history ORDER BY id DESC LIMIT 200
                )
            """)
    except Exception as e:
        logger.warning(f"Fehler beim Schreiben der Scan-Historie: {e}")
    finally:
        conn.close()


def get_scan_history(db_path: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Gibt die letzten N Einträge der Scan-Historie zurück."""
    conn = get_db_connection(db_path)
    try:
        cursor = conn.execute("""
            SELECT h.id, h.tag_id, h.reader_id, h.status, h.action_executed, h.payload, h.timestamp,
                   t.alias as tag_alias, r.target_player
            FROM scan_history h
            LEFT JOIN tags t ON h.tag_id = t.tag_id
            LEFT JOIN readers r ON h.reader_id = r.reader_id
            ORDER BY h.id DESC
            LIMIT ?
        """, (limit,))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()
