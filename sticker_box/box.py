import os
import re
import uuid
import sqlite3
from pathlib import Path

from . import clock, db, policy, presets
from .errors import BoxError

DB_NAME = "box.sqlite3"
LANGUAGE = re.compile(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*")
NOTES_LIMIT = 20_000


class Box:
    def __init__(self, root: Path):
        self.root = root
        self.temporary = root / "temporary"
        self.persistent = root / "persistent"
        self.db_path = root / DB_NAME
        self.readme = root / "README.md"
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = db.connect(self.db_path)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def meta(self, key: str, default: str | None = None) -> str | None:
        return db.get_meta(self.conn, key, default)

    def policy(self) -> dict:
        return policy.load(self.conn)

    @property
    def language(self) -> str:
        return self.meta("language", "und")

    def write_readme(self) -> None:
        from . import manual

        text = manual.render(self)
        tmp = self.root / f".README.md.{uuid.uuid4().hex}.tmp"
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self.readme)

    @classmethod
    def create(cls, path: Path, preset: str, language: str, description: str | None = None) -> "Box":
        if preset not in presets.PRESETS:
            raise BoxError("unknown_preset", f"unknown preset {preset!r}", presets=sorted(presets.PRESETS))
        if not LANGUAGE.fullmatch(language):
            raise BoxError("invalid_language", f"language {language!r} is not a language tag such as zh-Hans, ja or en")
        path = path.resolve()
        if description is not None and len(description) > 2000:
            raise BoxError("too_long", "the description is limited to 2000 characters")
        if (path / DB_NAME).exists():
            raise BoxError("exists", f"{path} already holds a box")
        if path.exists() and (not path.is_dir() or any(path.iterdir())):
            raise BoxError("not_empty", f"{path} exists and is not an empty directory")
        start = presets.get(preset)
        rules = policy.validate(start["policy"])
        path.mkdir(parents=True, exist_ok=True)
        box = cls(path)
        box.temporary.mkdir()
        box.persistent.mkdir()
        db.create(box.conn)
        with db.transaction(box.conn):
            for key, value in {
                "preset": preset,
                "language": language,
                "description": description if description is not None else start["description"],
                "created_at": clock.stamp(),
                "agent_notes": "",
            }.items():
                db.set_meta(box.conn, key, value)
            policy.store_all(box.conn, rules)
        box.write_readme()
        return box

    @classmethod
    def open(cls, path: Path) -> "Box":
        path = path.resolve()
        if not (path / DB_NAME).is_file():
            raise BoxError("no_box", f"{path} is not a sticker box (no {DB_NAME})")
        box = cls(path)
        db.check_version(box.conn)
        box.temporary.mkdir(exist_ok=True)
        box.persistent.mkdir(exist_ok=True)
        return box


def locate(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    env = os.environ.get("STICKER_BOX_DIR")
    if env:
        return Path(env)
    cwd = Path.cwd()
    if (cwd / DB_NAME).is_file():
        return cwd
    raise BoxError("no_box", "no box given: pass --box, set STICKER_BOX_DIR, or run inside a box directory")
