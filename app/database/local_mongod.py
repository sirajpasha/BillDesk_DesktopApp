"""Start (and, optionally, initialise as a single-node replica set) the bundled local MongoDB.

Only ever acts on a LOCAL url (127.0.0.1 / localhost). A remote or Atlas URL is left alone.
Single-node replica set is what enables multi-document transactions (see MongoDatabase.transaction()).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app import paths

log = logging.getLogger(__name__)
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class LocalMongoError(RuntimeError):
    pass


def parse_local_url(url: str) -> Optional[tuple]:
    """(host, port) when `url` points at this machine, else None (remote servers are never touched)."""
    if url.startswith("mongodb+srv://"):
        return None
    p = urlparse(url)
    host = p.hostname or ""
    if host not in LOCAL_HOSTS:
        return None
    return ("127.0.0.1" if host == "localhost" else host, p.port or 27017)


def find_mongod() -> Optional[Path]:
    candidates = [paths.resource_path("resources/mongo/win32-x64/mongod.exe")]
    for v in ("8.0", "7.0", "6.0"):
        candidates.append(Path(rf"C:\Program Files\MongoDB\Server\{v}\bin\mongod.exe"))
    which = shutil.which("mongod")
    if which:
        candidates.append(Path(which))
    return next((c for c in candidates if c.exists()), None)


def _ping(host: str, port: int, timeout_ms: int = 1500) -> Optional[Dict[str, Any]]:
    """hello document if a server answers, else None."""
    client = MongoClient(host, port, serverSelectionTimeoutMS=timeout_ms, directConnection=True)
    try:
        return client.admin.command("hello")
    except PyMongoError:
        return None
    finally:
        client.close()


def _initiate_replica_set(host: str, port: int, name: str, timeout: float = 30.0) -> None:
    client = MongoClient(host, port, serverSelectionTimeoutMS=5000, directConnection=True)
    try:
        hello = client.admin.command("hello")
        if not hello.get("setName"):
            log.info("Initiating single-node replica set %s on %s:%s", name, host, port)
            client.admin.command("replSetInitiate", {"_id": name, "members": [{"_id": 0, "host": f"{host}:{port}"}]})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if client.admin.command("hello").get("isWritablePrimary"):
                return
            time.sleep(0.3)
        raise LocalMongoError(f"Replica set {name} did not elect a primary within {timeout:.0f}s")
    finally:
        client.close()


def ensure_local_mongod(url: str, db_dir: Optional[Path] = None, log_file: Optional[Path] = None,
                        replica_set: str = "", wait_seconds: float = 30.0) -> str:
    """Make sure a MongoDB answers at `url`. Returns 'remote' | 'running' | 'started'.

    Raises LocalMongoError if a local server is needed but cannot be started."""
    target = parse_local_url(url)
    if target is None:
        return "remote"
    host, port = target

    hello = _ping(host, port)
    if hello is not None:
        if replica_set and not hello.get("setName"):
            log.warning("MONGO_REPLICA_SET=%s is set but the MongoDB already running on %s:%s is standalone, so transactions are "
                        "NOT available. Stop that MongoDB and start BillDesk again to let it start the server as a replica set.",
                        replica_set, host, port)
        return "running"

    exe = find_mongod()
    if exe is None:
        raise LocalMongoError(f"MongoDB is not running on {host}:{port} and no mongod.exe was found to start it.")
    db_dir = Path(db_dir) if db_dir else paths.user_data_dir() / "db"
    log_file = Path(log_file) if log_file else paths.user_data_dir() / "logs" / "mongod.log"
    db_dir.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [str(exe), "--dbpath", str(db_dir), "--bind_ip", host, "--port", str(port),
           "--logpath", str(log_file), "--logappend", "--wiredTigerCacheSizeGB", "0.5"]
    if replica_set:
        cmd += ["--replSet", replica_set]
    log.info("Starting MongoDB: %s", " ".join(cmd))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if _ping(host, port, 800) is not None:
            break
        time.sleep(0.4)
    else:
        raise LocalMongoError(f"MongoDB did not start within {wait_seconds:.0f}s - see {log_file}")
    if replica_set:
        _initiate_replica_set(host, port, replica_set)
    return "started"


def stop_local_mongod(url: str) -> bool:
    """Ask the local server to shut down cleanly (used by the self-test; never touches a remote server)."""
    target = parse_local_url(url)
    if target is None:
        return False
    client = MongoClient(target[0], target[1], serverSelectionTimeoutMS=3000, directConnection=True)
    try:
        client.admin.command("shutdown", force=True)
    except PyMongoError:
        pass                                # the connection drops as the server exits - that is success
    finally:
        client.close()
    return True
