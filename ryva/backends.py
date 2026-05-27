from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class StateBackend(ABC):
    """Abstract key-value state store for runs, lineage, and feedback records."""

    @abstractmethod
    def write(self, namespace: str, key: str, data: dict) -> None:
        """Persist a JSON-serialisable record."""

    @abstractmethod
    def read(self, namespace: str, key: str) -> dict | None:
        """Return a record or None if not found."""

    @abstractmethod
    def list_keys(self, namespace: str) -> list[str]:
        """Return all keys in a namespace."""

    @abstractmethod
    def delete(self, namespace: str, key: str) -> bool:
        """Delete a record. Returns True if it existed."""

    def exists(self, namespace: str, key: str) -> bool:
        return self.read(namespace, key) is not None


# ---------------------------------------------------------------------------
# LocalFileSystem backend (default, no extra deps)
# ---------------------------------------------------------------------------

class LocalFileSystemBackend(StateBackend):
    """Stores records as JSON files under root/<namespace>/<key>.json."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, namespace: str, key: str) -> Path:
        return self.root / namespace / f"{key}.json"

    def write(self, namespace: str, key: str, data: dict) -> None:
        p = self._path(namespace, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2, default=str))

    def read(self, namespace: str, key: str) -> dict | None:
        p = self._path(namespace, key)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def list_keys(self, namespace: str) -> list[str]:
        ns_dir = self.root / namespace
        if not ns_dir.exists():
            return []
        return sorted(p.stem for p in ns_dir.glob("*.json"))

    def delete(self, namespace: str, key: str) -> bool:
        p = self._path(namespace, key)
        if p.exists():
            p.unlink()
            return True
        return False


# ---------------------------------------------------------------------------
# PostgreSQL backend (requires asyncpg; used synchronously via run_coroutine)
# ---------------------------------------------------------------------------

class PostgresBackend(StateBackend):
    """
    Stores records in a Postgres table: ryva_state(namespace, key, data JSONB).
    Requires asyncpg. Connection string via dsn parameter.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._pool: Any = None
        self._ensure_table()

    def _run(self, coro):
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    future = ex.submit(asyncio.run, coro)
                    return future.result()
            return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    async def _get_conn(self):
        import asyncpg
        return await asyncpg.connect(self.dsn)

    def _ensure_table(self) -> None:
        async def _create():
            conn = await self._get_conn()
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS ryva_state (
                        namespace TEXT NOT NULL,
                        key       TEXT NOT NULL,
                        data      JSONB NOT NULL,
                        PRIMARY KEY (namespace, key)
                    )
                """)
            finally:
                await conn.close()
        try:
            self._run(_create())
        except Exception:
            pass  # table may already exist or db unavailable at import time

    def write(self, namespace: str, key: str, data: dict) -> None:
        async def _write():
            conn = await self._get_conn()
            try:
                await conn.execute(
                    """
                    INSERT INTO ryva_state (namespace, key, data)
                    VALUES ($1, $2, $3::jsonb)
                    ON CONFLICT (namespace, key) DO UPDATE SET data = EXCLUDED.data
                    """,
                    namespace, key, json.dumps(data, default=str),
                )
            finally:
                await conn.close()
        self._run(_write())

    def read(self, namespace: str, key: str) -> dict | None:
        async def _read():
            conn = await self._get_conn()
            try:
                row = await conn.fetchrow(
                    "SELECT data FROM ryva_state WHERE namespace=$1 AND key=$2",
                    namespace, key,
                )
                return dict(row["data"]) if row else None
            finally:
                await conn.close()
        return self._run(_read())

    def list_keys(self, namespace: str) -> list[str]:
        async def _list():
            conn = await self._get_conn()
            try:
                rows = await conn.fetch(
                    "SELECT key FROM ryva_state WHERE namespace=$1 ORDER BY key",
                    namespace,
                )
                return [r["key"] for r in rows]
            finally:
                await conn.close()
        return self._run(_list())

    def delete(self, namespace: str, key: str) -> bool:
        async def _del():
            conn = await self._get_conn()
            try:
                result = await conn.execute(
                    "DELETE FROM ryva_state WHERE namespace=$1 AND key=$2",
                    namespace, key,
                )
                return result != "DELETE 0"
            finally:
                await conn.close()
        return self._run(_del())


# ---------------------------------------------------------------------------
# S3 backend (requires boto3)
# ---------------------------------------------------------------------------

class S3Backend(StateBackend):
    """
    Stores records as JSON objects in an S3 bucket.
    Object key pattern: <prefix>/<namespace>/<key>.json
    Requires boto3.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "ryva",
        region: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
    ) -> None:
        import boto3
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        self._s3 = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )

    def _object_key(self, namespace: str, key: str) -> str:
        return f"{self.prefix}/{namespace}/{key}.json"

    def write(self, namespace: str, key: str, data: dict) -> None:
        body = json.dumps(data, indent=2, default=str).encode()
        self._s3.put_object(
            Bucket=self.bucket,
            Key=self._object_key(namespace, key),
            Body=body,
            ContentType="application/json",
        )

    def read(self, namespace: str, key: str) -> dict | None:
        try:
            response = self._s3.get_object(
                Bucket=self.bucket,
                Key=self._object_key(namespace, key),
            )
            return json.loads(response["Body"].read())
        except Exception:
            return None

    def list_keys(self, namespace: str) -> list[str]:
        prefix = f"{self.prefix}/{namespace}/"
        paginator = self._s3.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                k = obj["Key"][len(prefix):]
                if k.endswith(".json"):
                    keys.append(k[:-5])
        return sorted(keys)

    def delete(self, namespace: str, key: str) -> bool:
        try:
            self._s3.delete_object(
                Bucket=self.bucket,
                Key=self._object_key(namespace, key),
            )
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_backend(config: dict, root: Path | None = None) -> StateBackend:
    """
    Instantiate a backend from a config dict.

    Config shapes:
      {"type": "local", "root": "/path/to/project"}
      {"type": "postgres", "dsn": "postgresql://user:pass@host/db"}
      {"type": "s3", "bucket": "my-bucket", "prefix": "ryva", "region": "us-east-1"}
    """
    backend_type = config.get("type", "local")

    if backend_type == "local":
        effective_root = Path(config.get("root", ".")) if root is None else root
        return LocalFileSystemBackend(effective_root)

    if backend_type == "postgres":
        dsn = config.get("dsn")
        if not dsn:
            raise ValueError("Postgres backend requires 'dsn' in config")
        return PostgresBackend(dsn)

    if backend_type == "s3":
        bucket = config.get("bucket")
        if not bucket:
            raise ValueError("S3 backend requires 'bucket' in config")
        return S3Backend(
            bucket=bucket,
            prefix=config.get("prefix", "ryva"),
            region=config.get("region"),
            aws_access_key_id=config.get("aws_access_key_id"),
            aws_secret_access_key=config.get("aws_secret_access_key"),
        )

    raise ValueError(f"Unknown backend type: '{backend_type}'")
