import sqlite3
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


def sanitize_tag_id(tag_id: Optional[str]) -> str:
    """Sanitizes a tag ID by converting to lowercase and stripping hyphens and colons."""
    if not tag_id:
        return ""
    return str(tag_id).replace("-", "").replace(":", "").strip().lower()


def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Creates a connection to the SQLite database with row factory."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: str):
    """Initializes database tables and runs schema/data migrations."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            # Table: readers (mapping reader_id -> target_player + abs credentials)
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

            # Migration if abs_provider_prefix is missing in older DB versions
            try:
                conn.execute("ALTER TABLE readers ADD COLUMN abs_provider_prefix TEXT")
            except Exception:
                pass

            # Table: tags (RFID/NFC tag configuration)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    tag_id TEXT PRIMARY KEY,
                    alias TEXT,
                    action_type TEXT,
                    library_id TEXT,
                    target_id TEXT,
                    volume INTEGER,
                    random BOOLEAN DEFAULT 0,
                    start_from_beginning BOOLEAN DEFAULT 0,
                    extra_params TEXT,
                    last_scanned DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migration if library_id is missing in older DB versions
            try:
                conn.execute("ALTER TABLE tags ADD COLUMN library_id TEXT")
            except Exception:
                pass

            # Migration if start_from_beginning is missing in older DB versions
            try:
                conn.execute("ALTER TABLE tags ADD COLUMN start_from_beginning BOOLEAN DEFAULT 0")
            except Exception:
                pass

            # Table: scan_history (log of recent scans for UI & debugging)
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

            # Index for history timestamps
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_timestamp 
                ON scan_history(timestamp DESC)
            """)

            # Migration: Sanitize existing tag IDs in database (convert to lowercase, remove hyphens)
            try:
                cursor = conn.execute("""
                    SELECT tag_id, alias, action_type, library_id, target_id, volume,
                           random, start_from_beginning, extra_params, last_scanned, created_at, updated_at 
                    FROM tags 
                    WHERE tag_id LIKE '%-%' OR tag_id != lower(tag_id)
                """)
                unclean_tags = cursor.fetchall()
                for r in unclean_tags:
                    old_id = r["tag_id"]
                    clean_id = sanitize_tag_id(old_id)
                    if clean_id != old_id:
                        existing = conn.execute("SELECT tag_id, action_type, target_id FROM tags WHERE tag_id = ?", (clean_id,)).fetchone()
                        if existing:
                            old_action = (r["action_type"] or "").strip()
                            old_target = (r["target_id"] or "").strip()
                            exist_action = (existing["action_type"] or "").strip()
                            exist_target = (existing["target_id"] or "").strip()
                            if (old_action or old_target) and not (exist_action or exist_target):
                                conn.execute("""
                                    UPDATE tags SET
                                        alias = ?,
                                        action_type = ?,
                                        library_id = ?,
                                        target_id = ?,
                                        volume = ?,
                                        random = ?,
                                        start_from_beginning = ?,
                                        extra_params = ?,
                                        updated_at = ?
                                    WHERE tag_id = ?
                                """, (r["alias"], r["action_type"], r["library_id"], r["target_id"], r["volume"], r["random"], r["start_from_beginning"], r["extra_params"], r["updated_at"], clean_id))
                            conn.execute("DELETE FROM tags WHERE tag_id = ?", (old_id,))
                        else:
                            conn.execute("UPDATE tags SET tag_id = ? WHERE tag_id = ?", (clean_id, old_id))

                # Sanitize scan_history records
                conn.execute("UPDATE scan_history SET tag_id = lower(replace(tag_id, '-', '')) WHERE tag_id LIKE '%-%' OR tag_id != lower(tag_id)")
            except Exception as e:
                logger.warning(f"Tag ID sanitization migration warning: {e}")
        logger.info(f"Database successfully initialized: {db_path}")
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
            SELECT tag_id, alias, action_type, library_id, target_id, volume, random, start_from_beginning,
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
            tag["start_from_beginning"] = bool(tag.get("start_from_beginning", 0))
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
    """Retrieves a tag by its ID."""
    conn = get_db_connection(db_path)
    clean_id = sanitize_tag_id(tag_id)
    try:
        cursor = conn.execute("SELECT * FROM tags WHERE tag_id = ?", (clean_id,))
        row = cursor.fetchone()
        if not row:
            return None
        tag = dict(row)
        tag["random"] = bool(tag["random"])
        tag["start_from_beginning"] = bool(tag.get("start_from_beginning", 0))
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
    Looks up the tag. If non-existent, creates an empty auto-discovery entry.
    Updates the 'last_scanned' field in all cases.
    Returns the tag dictionary and an 'is_new' flag.
    """
    conn = get_db_connection(db_path)
    clean_id = sanitize_tag_id(tag_id)
    try:
        with conn:
            cursor = conn.execute("SELECT * FROM tags WHERE tag_id = ?", (clean_id,))
            row = cursor.fetchone()
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

            if not row:
                # Create new auto-discovered tag
                default_alias = f"Unbekannter Tag {clean_id}"
                conn.execute("""
                    INSERT INTO tags (tag_id, alias, action_type, library_id, target_id, volume, random, start_from_beginning, extra_params, last_scanned, created_at, updated_at)
                    VALUES (?, ?, '', '', '', NULL, 0, 0, '{}', ?, ?, ?)
                """, (clean_id, default_alias, now, now, now))
                logger.info(f"Auto-Discovery: New tag '{clean_id}' registered in database.")
                return {
                    "tag_id": clean_id,
                    "alias": default_alias,
                    "action_type": "",
                    "library_id": "",
                    "target_id": "",
                    "volume": None,
                    "random": False,
                    "start_from_beginning": False,
                    "extra_params": "{}",
                    "extra_params_parsed": {},
                    "is_new": True,
                    "last_scanned": now
                }
            else:
                # Update last_scanned for existing tag
                conn.execute("UPDATE tags SET last_scanned = ? WHERE tag_id = ?", (now, clean_id))
                tag = dict(row)
                tag["random"] = bool(tag["random"])
                tag["start_from_beginning"] = bool(tag.get("start_from_beginning", 0))
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
    """Inserts or updates a tag record."""
    conn = get_db_connection(db_path)
    tag_id = sanitize_tag_id(tag_data.get("tag_id"))
    alias = tag_data.get("alias", "")
    action_type = tag_data.get("action_type", "")
    library_id = tag_data.get("library_id", "")
    target_id = tag_data.get("target_id", "")
    volume = tag_data.get("volume")
    random_flag = 1 if tag_data.get("random") else 0
    start_from_beginning_flag = 1 if tag_data.get("start_from_beginning") else 0
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
                INSERT INTO tags (tag_id, alias, action_type, library_id, target_id, volume, random, start_from_beginning, extra_params, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tag_id) DO UPDATE SET
                    alias = excluded.alias,
                    action_type = excluded.action_type,
                    library_id = excluded.library_id,
                    target_id = excluded.target_id,
                    volume = excluded.volume,
                    random = excluded.random,
                    start_from_beginning = excluded.start_from_beginning,
                    extra_params = excluded.extra_params,
                    updated_at = excluded.updated_at
            """, (tag_id, alias, action_type, library_id, target_id, volume, random_flag, start_from_beginning_flag, extra_params_str, now, now))
        return get_tag_by_id(db_path, tag_id)
    finally:
        conn.close()


def delete_tag(db_path: str, tag_id: str) -> bool:
    """Deletes a tag from the database."""
    conn = get_db_connection(db_path)
    clean_id = sanitize_tag_id(tag_id)
    try:
        with conn:
            cursor = conn.execute("DELETE FROM tags WHERE tag_id = ?", (clean_id,))
            return cursor.rowcount > 0
    finally:
        conn.close()


def delete_unconfigured_tags(db_path: str) -> int:
    """
    Deletes all tag records lacking a valid target or action.
    Returns the number of deleted records.
    """
    conn = get_db_connection(db_path)
    try:
        with conn:
            cursor = conn.execute("""
                DELETE FROM tags 
                WHERE action_type IS NULL OR trim(action_type) = '' 
                   OR lower(trim(action_type)) = 'none'
                   OR target_id IS NULL OR trim(target_id) = ''
            """)
            deleted_count = cursor.rowcount
            logger.info(f"Deleted {deleted_count} unconfigured tags from database.")
            return deleted_count
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
    """Inserts an entry into the scan history."""
    conn = get_db_connection(db_path)
    clean_id = sanitize_tag_id(tag_id)
    try:
        with conn:
            conn.execute("""
                INSERT INTO scan_history (tag_id, reader_id, status, action_executed, payload)
                VALUES (?, ?, ?, ?, ?)
            """, (clean_id, reader_id, status, action_executed, payload))
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
