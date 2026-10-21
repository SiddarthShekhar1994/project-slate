"""Object storage for uploads and cached lesson audio.

``LocalStorage`` keeps files under ``STORAGE_DIR``; ``S3Storage`` uses any
S3-compatible bucket (``S3_BUCKET``, optional ``S3_ENDPOINT_URL`` for MinIO).
Keys are relative paths such as ``tts/ab12….mp3`` or ``uploads/<user>/<id>.pdf``.
Files are served to the browser through ``/api/media/{key}``, which checks the
session and the key's owner before streaming.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Protocol

from ..config import get_settings


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def local_path(self, key: str) -> Path | None: ...


def _safe_key(key: str) -> str:
    parts = Path(key).parts
    if not parts or key.startswith("/") or any(p in ("..", "") for p in parts):
        raise ValueError(f"bad storage key {key!r}")
    return key


@dataclass
class LocalStorage:
    root: Path

    def _path(self, key: str) -> Path:
        return self.root / _safe_key(key)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def local_path(self, key: str) -> Path | None:
        path = self._path(key)
        return path if path.is_file() else None


@dataclass
class S3Storage:
    bucket: str
    endpoint_url: str | None = None

    def __post_init__(self) -> None:
        import boto3

        self._client = boto3.client("s3", endpoint_url=self.endpoint_url or None)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self.bucket, Key=_safe_key(key), Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self._client.get_object(Bucket=self.bucket, Key=_safe_key(key))["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=_safe_key(key))
            return True
        except self._client.exceptions.ClientError:
            return False

    def local_path(self, key: str) -> Path | None:
        return None


@cache
def get_storage() -> Storage:
    bucket = os.environ.get("S3_BUCKET")
    if bucket:
        return S3Storage(bucket=bucket, endpoint_url=os.environ.get("S3_ENDPOINT_URL"))
    return LocalStorage(Path(get_settings().storage_dir).resolve())
