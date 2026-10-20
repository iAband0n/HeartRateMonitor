"""SQLite-backed heart-rate history with bucketed reads for charts."""

from __future__ import annotations

import csv
import logging
import math
import random
import sqlite3
import time
from pathlib import Path

log = logging.getLogger(__name__)


class HistoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._last_saved: dict[str, tuple[float, int]] = {}
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_key TEXT NOT NULL,
                    ts REAL NOT NULL,
                    bpm INTEGER NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_samples_device_ts "
                "ON samples(device_key, ts)"
            )

    def add_sample(self, device_key: str, bpm: int, ts: float | None = None) -> bool:
        """Record a sample, de-duplicating streams that notify faster than 1 Hz."""
        if not device_key or not bpm or bpm < 20 or bpm > 300:
            return False
        ts = time.time() if ts is None else ts
        previous = self._last_saved.get(device_key)
        if previous and 0 <= ts - previous[0] < 0.85:
            return False
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO samples(device_key, ts, bpm) VALUES(?,?,?)",
                    (device_key, float(ts), int(bpm)),
                )
            self._last_saved[device_key] = (ts, int(bpm))
            return True
        except sqlite3.Error:
            log.exception("Failed to store heart-rate sample")
            return False

    def add_many(self, rows: list[tuple[str, float, int]]) -> None:
        if not rows:
            return
        try:
            with self._conn:
                self._conn.executemany(
                    "INSERT INTO samples(device_key, ts, bpm) VALUES(?,?,?)", rows
                )
        except sqlite3.Error:
            log.exception("Failed to bulk-insert heart-rate samples")

    def points(
        self,
        device_key: str,
        since: float,
        until: float | None = None,
        bucket: float = 1.0,
        max_points: int = 900,
    ) -> list[tuple[float, int]]:
        """Return chart points.  ``bucket`` seconds are averaged per column."""
        until = time.time() if until is None else until
        bucket = max(0.2, float(bucket))
        try:
            if bucket <= 1.01:
                rows = self._conn.execute(
                    "SELECT ts, bpm FROM samples "
                    "WHERE device_key=? AND ts>=? AND ts<=? ORDER BY ts",
                    (device_key, since, until),
                ).fetchall()
                if len(rows) > max_points:
                    step = len(rows) / max_points
                    rows = [rows[int(i * step)] for i in range(max_points)]
                return [(float(row["ts"]), int(row["bpm"])) for row in rows]

            rows = self._conn.execute(
                "SELECT CAST(ts / ? AS INTEGER) * ? AS b, AVG(bpm) AS avg_bpm, "
                "MIN(bpm) AS min_bpm, MAX(bpm) AS max_bpm, COUNT(*) AS n "
                "FROM samples WHERE device_key=? AND ts>=? AND ts<=? "
                "GROUP BY b ORDER BY b",
                (bucket, bucket, device_key, since, until),
            ).fetchall()
            if len(rows) > max_points:
                step = len(rows) / max_points
                rows = [rows[int(i * step)] for i in range(max_points)]
            return [(float(row["b"]), int(round(row["avg_bpm"]))) for row in rows]
        except sqlite3.Error:
            log.exception("Failed to query history")
            return []

    def stats(self, device_key: str, since: float) -> dict[str, float | int]:
        try:
            row = self._conn.execute(
                "SELECT MIN(bpm) AS lo, MAX(bpm) AS hi, AVG(bpm) AS avg, "
                "COUNT(*) AS n FROM samples WHERE device_key=? AND ts>=?",
                (device_key, since),
            ).fetchone()
            if not row or not row["n"]:
                return {"min": 0, "max": 0, "avg": 0, "count": 0}
            return {
                "min": int(row["lo"]),
                "max": int(row["hi"]),
                "avg": int(round(row["avg"])),
                "count": int(row["n"]),
            }
        except sqlite3.Error:
            log.exception("Failed to query history stats")
            return {"min": 0, "max": 0, "avg": 0, "count": 0}

    def latest(self, device_key: str) -> tuple[float, int] | None:
        try:
            row = self._conn.execute(
                "SELECT ts, bpm FROM samples WHERE device_key=? ORDER BY ts DESC LIMIT 1",
                (device_key,),
            ).fetchone()
            return (float(row["ts"]), int(row["bpm"])) if row else None
        except sqlite3.Error:
            return None

    def has_data(self, device_key: str) -> bool:
        return self.latest(device_key) is not None

    def clear(self, device_key: str | None = None) -> None:
        try:
            with self._conn:
                if device_key:
                    self._conn.execute("DELETE FROM samples WHERE device_key=?", (device_key,))
                    self._last_saved.pop(device_key, None)
                else:
                    self._conn.execute("DELETE FROM samples")
                    self._last_saved.clear()
        except sqlite3.Error:
            log.exception("Failed to clear history")

    def prune(self, retention_days: int) -> int:
        cutoff = time.time() - max(1, retention_days) * 86400
        try:
            with self._conn:
                cur = self._conn.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
            return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        except sqlite3.Error:
            log.exception("Failed to prune history")
            return 0

    def export_csv(self, device_key: str, since: float, path: str) -> int:
        try:
            rows = self._conn.execute(
                "SELECT ts, bpm FROM samples WHERE device_key=? AND ts>=? ORDER BY ts",
                (device_key, since),
            ).fetchall()
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(["时间", "时间戳", "心率(BPM)"])
                for row in rows:
                    writer.writerow(
                        [
                            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row["ts"])),
                            f"{row['ts']:.3f}",
                            row["bpm"],
                        ]
                    )
            return len(rows)
        except (OSError, sqlite3.Error):
            log.exception("Failed to export history")
            return -1

    def seed_demo(self, devices: list[tuple[str, str]]) -> None:
        """Populate a believable 24h history for demo/screenshot mode."""
        if not devices:
            return
        existing = self._conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
        if existing:
            return
        now = time.time()
        rows: list[tuple[str, float, int]] = []
        rng = random.Random(20251019)
        for device_index, (key, name) in enumerate(devices):
            base = 68 + device_index * 7
            # One day of 15-second samples, with a few rest / workout blocks.
            start = now - 24 * 3600
            coarse_end = now - 600
            t = start
            while t < coarse_end:
                hour = time.localtime(t).tm_hour
                minute = time.localtime(t).tm_min
                sleeping = 1 <= hour < 6
                workout = (7 <= hour < 8) or (18 <= hour < 19)
                if sleeping:
                    value = base - 12 + 3 * math.sin(t / 900) + rng.uniform(-2, 2)
                elif workout:
                    value = base + 38 + 12 * math.sin(t / 180) + rng.uniform(-4, 4)
                else:
                    value = base + 5 * math.sin(t / 1200) + rng.uniform(-3, 3)
                # A lunch-time walk and a short disconnect gap.
                if hour == 12 and minute < 30:
                    value += 12
                if hour == 15 and minute < 5:
                    t += 900
                    continue
                rows.append((key, t, int(max(45, min(190, round(value))))))
                t += 15
            # Dense last 10 minutes for the live chart (no overlap with coarse data).
            t = coarse_end
            while t < now:
                value = base + 8 + 5 * math.sin(t / 70) + rng.uniform(-2, 2)
                rows.append((key, t, int(round(value))))
                t += 1
        try:
            with self._conn:
                self._conn.executemany(
                    "INSERT INTO samples(device_key, ts, bpm) VALUES(?,?,?)", rows
                )
            log.info("Seeded %d demo samples", len(rows))
        except sqlite3.Error:
            log.exception("Failed to seed demo history")

    def close(self) -> None:
        try:
            with self._conn:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._conn.close()
        except sqlite3.Error:
            pass
