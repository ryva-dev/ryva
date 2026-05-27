from __future__ import annotations

import pytest

from ryva.backends import LocalFileSystemBackend, StateBackend, get_backend

# ---------------------------------------------------------------------------
# LocalFileSystemBackend
# ---------------------------------------------------------------------------

class TestLocalFileSystemBackend:
    def test_write_and_read(self, tmp_path):
        b = LocalFileSystemBackend(tmp_path)
        b.write("runs", "run001", {"agent": "summarizer", "status": "success"})
        data = b.read("runs", "run001")
        assert data is not None
        assert data["agent"] == "summarizer"

    def test_read_missing_returns_none(self, tmp_path):
        b = LocalFileSystemBackend(tmp_path)
        assert b.read("runs", "nonexistent") is None

    def test_file_created_at_expected_path(self, tmp_path):
        b = LocalFileSystemBackend(tmp_path)
        b.write("lineage", "r01", {"key": "val"})
        assert (tmp_path / "lineage" / "r01.json").exists()

    def test_list_keys_empty_namespace(self, tmp_path):
        b = LocalFileSystemBackend(tmp_path)
        assert b.list_keys("runs") == []

    def test_list_keys_after_writes(self, tmp_path):
        b = LocalFileSystemBackend(tmp_path)
        b.write("runs", "r01", {"x": 1})
        b.write("runs", "r02", {"x": 2})
        b.write("runs", "r03", {"x": 3})
        keys = b.list_keys("runs")
        assert set(keys) == {"r01", "r02", "r03"}
        assert keys == sorted(keys)

    def test_list_keys_different_namespaces(self, tmp_path):
        b = LocalFileSystemBackend(tmp_path)
        b.write("runs", "r01", {})
        b.write("feedback", "f01", {})
        assert b.list_keys("runs") == ["r01"]
        assert b.list_keys("feedback") == ["f01"]

    def test_delete_existing_key(self, tmp_path):
        b = LocalFileSystemBackend(tmp_path)
        b.write("runs", "r01", {})
        assert b.delete("runs", "r01") is True
        assert b.read("runs", "r01") is None

    def test_delete_nonexistent_key(self, tmp_path):
        b = LocalFileSystemBackend(tmp_path)
        assert b.delete("runs", "ghost") is False

    def test_exists_true_after_write(self, tmp_path):
        b = LocalFileSystemBackend(tmp_path)
        b.write("ns", "key1", {"v": 1})
        assert b.exists("ns", "key1") is True

    def test_exists_false_for_missing(self, tmp_path):
        b = LocalFileSystemBackend(tmp_path)
        assert b.exists("ns", "missing") is False

    def test_overwrite_updates_value(self, tmp_path):
        b = LocalFileSystemBackend(tmp_path)
        b.write("ns", "k", {"v": 1})
        b.write("ns", "k", {"v": 99})
        assert b.read("ns", "k")["v"] == 99

    def test_json_round_trip(self, tmp_path):
        b = LocalFileSystemBackend(tmp_path)
        data = {"nested": {"list": [1, 2, 3]}, "flag": True, "score": 0.5}
        b.write("ns", "complex", data)
        result = b.read("ns", "complex")
        assert result == data

    def test_creates_namespace_dir_if_missing(self, tmp_path):
        b = LocalFileSystemBackend(tmp_path)
        b.write("brand_new_ns", "k", {})
        assert (tmp_path / "brand_new_ns").is_dir()

    def test_malformed_json_returns_none(self, tmp_path):
        ns_dir = tmp_path / "broken_ns"
        ns_dir.mkdir()
        (ns_dir / "bad.json").write_text("{not valid json")
        b = LocalFileSystemBackend(tmp_path)
        assert b.read("broken_ns", "bad") is None


# ---------------------------------------------------------------------------
# StateBackend abstract interface
# ---------------------------------------------------------------------------

class TestStateBackendInterface:
    def test_is_abstract(self):
        with pytest.raises(TypeError):
            StateBackend()  # type: ignore[abstract]

    def test_exists_uses_read(self, tmp_path):
        b = LocalFileSystemBackend(tmp_path)
        b.write("ns", "k", {"v": 1})
        assert b.exists("ns", "k") is True
        assert b.exists("ns", "missing") is False


# ---------------------------------------------------------------------------
# get_backend factory
# ---------------------------------------------------------------------------

class TestGetBackend:
    def test_local_backend_default(self, tmp_path):
        b = get_backend({"type": "local"}, root=tmp_path)
        assert isinstance(b, LocalFileSystemBackend)

    def test_local_backend_uses_root(self, tmp_path):
        b = get_backend({"type": "local"}, root=tmp_path)
        b.write("ns", "k", {"v": 1})
        assert (tmp_path / "ns" / "k.json").exists()

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown backend type"):
            get_backend({"type": "ftp"})

    def test_postgres_missing_dsn_raises(self):
        with pytest.raises(ValueError, match="dsn"):
            get_backend({"type": "postgres"})

    def test_s3_missing_bucket_raises(self):
        with pytest.raises(ValueError, match="bucket"):
            get_backend({"type": "s3"})
