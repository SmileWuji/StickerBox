import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import BoxError

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE policy_rule (name TEXT PRIMARY KEY, params TEXT NOT NULL);
CREATE TABLE policy_log (id INTEGER PRIMARY KEY, at TEXT NOT NULL, name TEXT NOT NULL, old TEXT, new TEXT);

CREATE TABLE item (
  sha256 TEXT PRIMARY KEY,
  file TEXT NOT NULL UNIQUE,
  format TEXT NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  animated INTEGER NOT NULL,
  frames INTEGER NOT NULL,
  duration_ms INTEGER,
  fps REAL,
  codec TEXT,
  audio INTEGER NOT NULL DEFAULT 0,
  bytes INTEGER NOT NULL,
  phash INTEGER NOT NULL,
  added_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  expires_at TEXT,
  license TEXT NOT NULL,
  source TEXT,
  text TEXT,
  description TEXT,
  note TEXT
);
CREATE INDEX item_added ON item (added_at);
CREATE INDEX item_expires ON item (expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE item_field (
  sha256 TEXT NOT NULL REFERENCES item (sha256) ON DELETE CASCADE,
  name TEXT NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (sha256, name)
);
CREATE TABLE keyframe (
  sha256 TEXT NOT NULL REFERENCES item (sha256) ON DELETE CASCADE,
  idx INTEGER NOT NULL,
  frame_no INTEGER NOT NULL,
  t_ms INTEGER NOT NULL,
  phash INTEGER NOT NULL,
  PRIMARY KEY (sha256, idx)
);

CREATE TABLE tag (
  id INTEGER PRIMARY KEY,
  category TEXT NOT NULL,
  value TEXT NOT NULL,
  definition TEXT,
  parent_id INTEGER REFERENCES tag (id) ON DELETE SET NULL,
  lang TEXT,
  created_at TEXT NOT NULL,
  retired_at TEXT,
  UNIQUE (category, value)
);
CREATE TABLE tag_alias (
  tag_id INTEGER NOT NULL REFERENCES tag (id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  alias TEXT NOT NULL,
  PRIMARY KEY (category, alias)
);
CREATE TABLE item_tag (
  sha256 TEXT NOT NULL REFERENCES item (sha256) ON DELETE CASCADE,
  tag_id INTEGER NOT NULL REFERENCES tag (id) ON DELETE CASCADE,
  PRIMARY KEY (sha256, tag_id)
);
CREATE INDEX item_tag_tag ON item_tag (tag_id);
CREATE TABLE vocab_log (id INTEGER PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL);

CREATE TABLE feature (
  sha256 TEXT NOT NULL REFERENCES item (sha256) ON DELETE CASCADE,
  frame INTEGER NOT NULL,
  extractor TEXT NOT NULL,
  n INTEGER NOT NULL,
  kp BLOB NOT NULL,
  desc BLOB NOT NULL,
  PRIMARY KEY (sha256, frame)
);
CREATE TABLE relation (
  a TEXT NOT NULL REFERENCES item (sha256) ON DELETE CASCADE,
  b TEXT NOT NULL REFERENCES item (sha256) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  method TEXT NOT NULL,
  score REAL,
  transform TEXT,
  found_at TEXT NOT NULL,
  PRIMARY KEY (a, b)
);
CREATE INDEX relation_b ON relation (b);
"""


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


QUERY_SECONDS = 10.0
TABLES = ("meta", "item", "item_field", "tag", "tag_alias", "item_tag")


def connect_readonly(path: Path) -> sqlite3.Connection:
    """For another box's database, which may be hostile: read-only, no writes even to temp
    tables, the tables the tool reads must be real tables, and every statement is cut off after
    QUERY_SECONDS."""
    import time
    from urllib.parse import quote

    conn = sqlite3.connect(f"file:{quote(str(path))}?mode=ro&immutable=1", uri=True, timeout=5, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
    conn.execute("PRAGMA query_only = ON")
    kinds = {r["name"]: r["type"] for r in conn.execute(
        f"SELECT name, type FROM sqlite_master WHERE name IN ({','.join('?' * len(TABLES))})", TABLES)}
    if any(kinds.get(t) != "table" for t in TABLES):
        conn.close()
        raise BoxError("unsafe_box", f"{path} does not have the tables a box has")
    state = {"end": None}

    def guard():
        if state["end"] is None:
            state["end"] = time.monotonic() + QUERY_SECONDS
        return 1 if time.monotonic() > state["end"] else 0

    conn.set_progress_handler(guard, 10_000)
    return conn


def create(conn: sqlite3.Connection) -> None:
    conn.executescript(f"BEGIN; {SCHEMA} INSERT INTO meta (key, value) VALUES ('schema_version', '{SCHEMA_VERSION}'); COMMIT;")


def check_version(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    if row is None:
        raise BoxError("not_a_box", "box.sqlite3 has no schema_version")
    try:
        version = int(row["value"])
    except (TypeError, ValueError):
        raise BoxError("not_a_box", "box.sqlite3 has an unreadable schema_version") from None
    if version > SCHEMA_VERSION:
        raise BoxError("box_too_new", f"this box uses schema {version}; this sticker-box understands up to {SCHEMA_VERSION}", schema_version=version)


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value", (key, value))


def to_signed(value: int) -> int:
    return value - (1 << 64) if value >= (1 << 63) else value


def to_unsigned(value: int) -> int:
    return value + (1 << 64) if value < 0 else value
