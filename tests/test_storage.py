import pytest

from app import storage


def test_build_key_is_namespaced_and_safe():
    key = storage.build_key(execution_id=7, artifact_type="log", title="My Trace #1.txt")
    assert key.startswith("exec/7/log/")
    assert " " not in key and "#" not in key
    assert key.endswith("my-trace-1.txt")


def test_put_object_calls_client(monkeypatch):
    calls = {}

    class FakeClient:
        def bucket_exists(self, bucket):
            return True

        def make_bucket(self, bucket):
            calls["made"] = bucket

        def put_object(self, bucket, key, data, length, content_type):
            calls.update(bucket=bucket, key=key, length=length, content_type=content_type)

    monkeypatch.setattr(storage, "_client", lambda: FakeClient())
    returned = storage.put_object("exec/1/log/x.txt", b"hello", "text/plain")
    assert returned == "exec/1/log/x.txt"
    assert calls["bucket"] == storage._settings.s3_bucket
    assert calls["length"] == 5
    assert calls["content_type"] == "text/plain"


@pytest.mark.skipif(True, reason="integration: requires live MinIO; flip to False to run locally")
def test_roundtrip_against_real_minio():
    storage.ensure_bucket()
    key = storage.put_object("exec/test/log/it.txt", b"roundtrip", "text/plain")
    assert storage.get_object(key) == b"roundtrip"
