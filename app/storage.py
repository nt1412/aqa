"""Thin MinIO blob storage wrapper.

Service code calls the module-level functions (put_object/get_object); unit tests
monkeypatch `_client` so no live MinIO is needed. Bucket auto-created on first use.
"""

import io
import re
import uuid

from minio import Minio

from app.config import get_settings

_settings = get_settings()


def _client() -> Minio:
    endpoint = _settings.s3_endpoint.replace("http://", "").replace("https://", "")
    secure = _settings.s3_endpoint.startswith("https://")
    return Minio(
        endpoint,
        access_key=_settings.s3_access_key,
        secret_key=_settings.s3_secret_key,
        secure=secure,
    )


def ensure_bucket() -> None:
    client = _client()
    if not client.bucket_exists(_settings.s3_bucket):
        client.make_bucket(_settings.s3_bucket)


def _slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    return text.strip("-") or "artifact"


def build_key(execution_id: int, artifact_type: str, title: str) -> str:
    return f"exec/{execution_id}/{artifact_type}/{uuid.uuid4().hex[:8]}-{_slug(title)}"


def put_object(key: str, data: bytes, content_type: str) -> str:
    client = _client()
    if not client.bucket_exists(_settings.s3_bucket):
        client.make_bucket(_settings.s3_bucket)
    client.put_object(
        _settings.s3_bucket, key, io.BytesIO(data), length=len(data), content_type=content_type
    )
    return key


def get_object(key: str) -> bytes:
    client = _client()
    response = client.get_object(_settings.s3_bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
