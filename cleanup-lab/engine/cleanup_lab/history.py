"""Private SQLite cleanup history with a per-install HMAC-SHA256 chain."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import stat

from .paths import state_dir

DATABASE = "history.sqlite3"
KEY = "history.key"
GENESIS = "0" * 64


class HistoryError(RuntimeError):
    """The history cannot be trusted or written."""


def _private_state(env=None, platform=None, *, create=False):
    folder = state_dir(env, platform)
    if create:
        os.makedirs(folder, mode=0o700, exist_ok=True)
    if not os.path.isdir(folder) or os.path.islink(folder):
        raise HistoryError("The cleanup state folder is missing or is a symlink.")
    if os.name != "nt" and stat.S_IMODE(os.stat(folder).st_mode) & 0o077:
        raise HistoryError("The cleanup state folder must be private (mode 0700).")
    return folder


def _key(folder, *, create=False):
    path = os.path.join(folder, KEY)
    if create and not os.path.lexists(path):
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as handle:
                handle.write(os.urandom(32))
    if os.path.islink(path):
        raise HistoryError("The history key must not be a symlink.")
    try:
        mode = os.stat(path).st_mode
        if os.name != "nt" and stat.S_IMODE(mode) & 0o077:
            raise HistoryError("The history key must be private (mode 0600).")
        with open(path, "rb") as handle:
            key = handle.read()
    except FileNotFoundError as exc:
        raise HistoryError("The history key is missing; existing history cannot be verified.") from exc
    if len(key) != 32:
        raise HistoryError("The history key has an invalid length.")
    return key


def _connect(folder, *, create=False):
    path = os.path.join(folder, DATABASE)
    if os.path.islink(path):
        raise HistoryError("The history database must not be a symlink.")
    if not create and not os.path.exists(path):
        return None
    if create and not os.path.exists(path):
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
    if os.name != "nt" and stat.S_IMODE(os.stat(path).st_mode) & 0o077:
        raise HistoryError("The history database must be private (mode 0600).")
    db = sqlite3.connect(path, timeout=10)
    db.execute("PRAGMA journal_mode=DELETE")
    if create:
        db.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, payload TEXT NOT NULL, previous_hmac TEXT NOT NULL, hmac TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS chain_head (slot INTEGER PRIMARY KEY CHECK (slot = 1), count INTEGER NOT NULL, last_hmac TEXT NOT NULL, signature TEXT NOT NULL)")
    return db


def _digest(key, number, payload, previous):
    message = json.dumps([number, previous, payload], separators=(",", ":"), ensure_ascii=False)
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def _verify(db, key):
    previous = GENESIS
    expected_id = 1
    for number, payload, linked, signature in db.execute(
        "SELECT id, payload, previous_hmac, hmac FROM history ORDER BY id"
    ):
        if number != expected_id or linked != previous or not hmac.compare_digest(
            signature, _digest(key, number, payload, linked)
        ):
            raise HistoryError("History integrity check failed at record {0}.".format(number))
        previous = signature
        expected_id += 1
    head = db.execute("SELECT count, last_hmac, signature FROM chain_head WHERE slot = 1").fetchone()
    if head is None or head[0] != expected_id - 1 or head[1] != previous or not hmac.compare_digest(
        head[2], _digest(key, 0, str(head[0]), head[1])
    ):
        raise HistoryError("History chain head is missing or does not match the records.")
    return expected_id - 1, previous


def prepare(*, env=None, platform=None):
    """Create private storage before a clean starts; reject existing tampering."""
    folder = _private_state(env, platform, create=True)
    database_exists = os.path.exists(os.path.join(folder, DATABASE))
    key_exists = os.path.exists(os.path.join(folder, KEY))
    if database_exists != key_exists:
        raise HistoryError("The history database or key is missing; history cannot be trusted.")
    key = _key(folder, create=not database_exists)
    db = _connect(folder, create=True)
    try:
        if not database_exists:
            db.execute("INSERT INTO chain_head VALUES (1, 0, ?, ?)",
                       (GENESIS, _digest(key, 0, "0", GENESIS)))
        _verify(db, key)
        db.commit()
    finally:
        db.close()


def append(result, *, env=None, platform=None):
    """Record a completed run atomically, including each item's path and outcome."""
    folder = _private_state(env, platform)
    key = _key(folder)
    db = _connect(folder)
    if db is None:
        raise HistoryError("The history database is missing.")
    try:
        db.execute("BEGIN IMMEDIATE")
        count, previous = _verify(db, key)
        payload = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        number = count + 1
        signature = _digest(key, number, payload, previous)
        db.execute(
            "INSERT INTO history (id, payload, previous_hmac, hmac) VALUES (?, ?, ?, ?)",
            (number, payload, previous, signature),
        )
        db.execute("UPDATE chain_head SET count = ?, last_hmac = ?, signature = ? WHERE slot = 1",
                   (number, signature, _digest(key, 0, str(number), signature)))
        db.commit()
        return number
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def read(*, env=None, platform=None, limit=100, verify=False):
    """Newest records first. Verification always walks the full chain."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")
    folder = state_dir(env, platform)
    if not os.path.exists(folder):
        return {"entries": [], "total": 0, "verified": True}
    folder = _private_state(env, platform)
    db = _connect(folder)
    if db is None:
        if os.path.exists(os.path.join(folder, KEY)):
            raise HistoryError("The history database is missing.")
        return {"entries": [], "total": 0, "verified": True}
    try:
        key = _key(folder)
        count, _ = _verify(db, key)
        rows = db.execute("SELECT id, payload, hmac FROM history ORDER BY id DESC LIMIT ?", (limit,))
        entries = [{"id": number, "result": json.loads(payload), "hmac": signature} for number, payload, signature in rows]
        return {"entries": entries, "total": count, "verified": True}
    finally:
        db.close()
