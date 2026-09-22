"""SQLite data layer for Wasla Kahraba."""
from __future__ import annotations

import csv
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from .embeddings import generate_embedding

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "database" / "wasla_kahraba.db"
TABLE_ORDER = ["ownerpoint", "chargepoint", "llm_roles"]


class Database:
    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            cursor = connection.execute(sql, params)
            rows = [dict(row) for row in cursor.fetchall()] if sql.lstrip().upper().startswith(("SELECT", "PRAGMA")) else []
            connection.commit()
            return rows
        finally:
            connection.close()

    def create_tables(self, purge: bool = False) -> None:
        if purge:
            for table in reversed(TABLE_ORDER):
                self.query(f"DROP TABLE IF EXISTS {table}")
        for table in TABLE_ORDER:
            sql_path = BASE_DIR / "database" / "create_tables" / f"{table}.sql"
            self.query(sql_path.read_text(encoding="utf-8"))
            self._seed_table(table)

    def _seed_table(self, table: str) -> None:
        csv_path = BASE_DIR / "database" / "initial_data" / f"{table}.csv"
        if not csv_path.exists():
            return
        with csv_path.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        if not rows:
            return
        columns = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        values = [tuple(None if value in ("", "NULL") else value for value in row.values()) for row in rows]
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executemany(sql, values)
            connection.commit()
        finally:
            connection.close()

    def get_chargepoints(self, owner_id: int | None = None) -> list[dict[str, Any]]:
        if owner_id is None:
            return self.query("SELECT * FROM chargepoint ORDER BY chargepoint_id")
        return self.query("SELECT * FROM chargepoint WHERE owner_id = ? ORDER BY chargepoint_id", (owner_id,))

    def search_chargepoints(self, query: str) -> list[dict[str, Any]]:
        term = f"%{query.strip()}%"
        return self.query(
            "SELECT * FROM chargepoint WHERE chargepoint_name LIKE ? OR area LIKE ? OR service_type LIKE ? OR description LIKE ? OR status LIKE ? ORDER BY chargepoint_id",
            (term, term, term, term, term),
        )

    def get_owner_by_key(self, owner_key: str) -> dict[str, Any] | None:
        rows = self.query("SELECT * FROM ownerpoint WHERE owner_key = ? LIMIT 1", (owner_key,))
        return rows[0] if rows else None

    def get_owner(self, owner_id: int) -> dict[str, Any] | None:
        rows = self.query("SELECT * FROM ownerpoint WHERE owner_id = ? LIMIT 1", (owner_id,))
        return rows[0] if rows else None

    def get_llm_roles(self) -> dict[str, dict[str, Any]]:
        return {row["role"]: row for row in self.query("SELECT * FROM llm_roles")}

    def update_chargepoint(self, chargepoint_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"status", "waiting_count", "opening_hours", "capacity", "last_update", "embedding"}
        updates = {key: data[key] for key in allowed if key in data}
        if not updates:
            return self.get_chargepoint(chargepoint_id)
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [chargepoint_id]
        self.query(f"UPDATE chargepoint SET {assignments} WHERE chargepoint_id = ?", tuple(values))
        return self.get_chargepoint(chargepoint_id)

    def get_chargepoint(self, chargepoint_id: int) -> dict[str, Any] | None:
        rows = self.query("SELECT * FROM chargepoint WHERE chargepoint_id = ? LIMIT 1", (chargepoint_id,))
        return rows[0] if rows else None

    def backfill_embeddings(self) -> None:
        rows = self.query("SELECT chargepoint_id, chargepoint_name, area, service_type, description FROM chargepoint WHERE embedding IS NULL")
        for row in rows:
            text = " ".join(str(row[field]) for field in ("chargepoint_name", "area", "service_type", "description"))
            embedding = json.dumps(generate_embedding(text))
            self.query("UPDATE chargepoint SET embedding = ? WHERE chargepoint_id = ?", (embedding, row["chargepoint_id"]))

    def semantic_search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        query_vector = generate_embedding(query)
        scored = []
        for row in self.query("SELECT * FROM chargepoint WHERE embedding IS NOT NULL"):
            score = self._cosine(query_vector, json.loads(row["embedding"]))
            visible = {key: value for key, value in row.items() if key != "embedding"}
            visible["similarity"] = round(score, 3)
            scored.append(visible)
        return sorted(scored, key=lambda row: row["similarity"], reverse=True)[:top_k]

    @staticmethod
    def _cosine(first: list[float], second: list[float]) -> float:
        dot = sum(a * b for a, b in zip(first, second))
        left = math.sqrt(sum(value * value for value in first))
        right = math.sqrt(sum(value * value for value in second))
        return dot / (left * right) if left and right else 0.0


# Alias matching the course naming style.
database = Database
