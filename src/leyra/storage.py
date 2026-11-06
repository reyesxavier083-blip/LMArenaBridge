"""Small durable SQLite store for memory and audit events."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Storage:
    def __init__(self, database_path: str) -> None:
        self.database_path = str(Path(database_path).expanduser())
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    def save_memory(self, namespace: str, content: str, metadata: dict[str, Any] | None = None) -> int:
        created = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO memory(namespace, content, metadata_json, created_at) VALUES (?, ?, ?, ?)",
                (namespace, content, json.dumps(metadata or {}, ensure_ascii=False), created),
            )
            return int(cursor.lastrowid)

    def list_memory(self, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id, namespace, content, metadata_json, created_at FROM memory "
                "WHERE namespace = ? ORDER BY id DESC LIMIT ?",
                (namespace, max(1, min(limit, 200))),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "namespace": row["namespace"],
                "content": row["content"],
                "metadata": json.loads(row["metadata_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def audit(self, event_type: str, actor: str, outcome: str) -> None:
        created = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute(
                "INSERT INTO audit_events(event_type, actor, outcome, created_at) VALUES (?, ?, ?, ?)",
                (event_type, actor, outcome, created),
            )

    def list_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT event_type, actor, outcome, created_at FROM audit_events "
                "ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [dict(row) for row in rows]
