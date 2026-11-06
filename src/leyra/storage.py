"""Durable SQLite/PostgreSQL storage with optional Redis read cache."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # SQLite-only development/test install
    psycopg = None
    dict_row = None

try:
    import redis
except ImportError:
    redis = None


class Storage:
    def __init__(self, database_path: str = "/data/leyra.sqlite3",
                 database_url: str | None = None, redis_url: str | None = None) -> None:
        self.database_url = (database_url or os.getenv("LEYRA_DATABASE_URL", "")).strip()
        self.database_path = str(Path(database_path).expanduser())
        self.backend = "postgresql" if self.database_url.startswith(("postgres://", "postgresql://")) else "sqlite"
        if self.backend == "postgresql" and psycopg is None:
            raise RuntimeError("PostgreSQL configured but psycopg is not installed")
        self.cache = None
        cache_url = (redis_url or os.getenv("LEYRA_REDIS_URL", "")).strip()
        if cache_url and redis is not None:
            self.cache = redis.Redis.from_url(cache_url, decode_responses=True,
                                               socket_connect_timeout=2, socket_timeout=2)
        if self.backend == "sqlite":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self):
        if self.backend == "postgresql":
            return psycopg.connect(self.database_url, row_factory=dict_row)
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _sql(self, query: str) -> str:
        return query.replace("?", "%s") if self.backend == "postgresql" else query

    def initialize(self) -> None:
        with self.connect() as db:
            if self.backend == "sqlite":
                db.execute("PRAGMA journal_mode=WAL")
                id_type = "INTEGER PRIMARY KEY AUTOINCREMENT"
                json_type = "TEXT NOT NULL DEFAULT '{}'"
            else:
                id_type = "BIGSERIAL PRIMARY KEY"
                json_type = "JSONB NOT NULL DEFAULT '{}'::jsonb"
            db.execute(f"""CREATE TABLE IF NOT EXISTS memory (
                id {id_type}, namespace TEXT NOT NULL, content TEXT NOT NULL,
                metadata_json {json_type}, created_at TEXT NOT NULL)""")
            db.execute(f"""CREATE TABLE IF NOT EXISTS audit_events (
                id {id_type}, event_type TEXT NOT NULL, actor TEXT NOT NULL,
                outcome TEXT NOT NULL, created_at TEXT NOT NULL)""")

    def _invalidate(self, namespace: str) -> None:
        if self.cache:
            try:
                for key in self.cache.scan_iter(match=f"leyra:memory:{namespace}:*"):
                    self.cache.delete(key)
            except Exception:
                pass

    def save_memory(self, namespace: str, content: str,
                    metadata: dict[str, Any] | None = None) -> int:
        created = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(metadata or {}, ensure_ascii=False)
        with self.connect() as db:
            if self.backend == "postgresql":
                row = db.execute(
                    "INSERT INTO memory(namespace, content, metadata_json, created_at) "
                    "VALUES (%s, %s, %s::jsonb, %s) RETURNING id",
                    (namespace, content, payload, created)).fetchone()
                memory_id = int(row["id"])
            else:
                cursor = db.execute(
                    "INSERT INTO memory(namespace, content, metadata_json, created_at) VALUES (?, ?, ?, ?)",
                    (namespace, content, payload, created))
                memory_id = int(cursor.lastrowid)
        self._invalidate(namespace)
        return memory_id

    def list_memory(self, namespace: str, limit: int = 50) -> list[dict[str, Any]]:
        bounded = max(1, min(limit, 200))
        key = f"leyra:memory:{namespace}:{bounded}"
        if self.cache:
            try:
                cached = self.cache.get(key)
                if cached:
                    return json.loads(cached)
            except Exception:
                pass
        with self.connect() as db:
            rows = db.execute(self._sql(
                "SELECT id, namespace, content, metadata_json, created_at FROM memory "
                "WHERE namespace = ? ORDER BY id DESC LIMIT ?"),
                (namespace, bounded)).fetchall()
        items = []
        for row in rows:
            metadata = row["metadata_json"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            items.append({"id": row["id"], "namespace": row["namespace"],
                          "content": row["content"], "metadata": metadata,
                          "created_at": row["created_at"]})
        if self.cache:
            try:
                self.cache.setex(key, 60, json.dumps(items, ensure_ascii=False))
            except Exception:
                pass
        return items

    def audit(self, event_type: str, actor: str, outcome: str) -> None:
        created = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute(self._sql(
                "INSERT INTO audit_events(event_type, actor, outcome, created_at) VALUES (?, ?, ?, ?)"),
                (event_type, actor, outcome, created))

    def list_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(self._sql(
                "SELECT event_type, actor, outcome, created_at FROM audit_events ORDER BY id DESC LIMIT ?"),
                (max(1, min(limit, 200)),)).fetchall()
        return [dict(row) for row in rows]

    def health(self) -> dict[str, str]:
        with self.connect() as db:
            db.execute("SELECT 1")
        cache_status = "disabled"
        if self.cache:
            try:
                self.cache.ping()
                cache_status = "ready"
            except Exception:
                cache_status = "unavailable"
        return {"database": self.backend, "cache": cache_status}
