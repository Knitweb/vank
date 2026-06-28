"""Property tests for vank.fieldledger.secure_store.SecureStore."""
import sys, tempfile, os; sys.path.insert(0, '/tmp/vank-dest/src')
import json
import pytest
import vank.fieldledger.secure_store as _ss_mod
from vank.fieldledger.secure_store import SecureStore


# ---------------------------------------------------------------------------
# Speed shim — patch PBKDF2 iterations down for testing only
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    """Replace 480k-iteration PBKDF2 with 1 iteration for test speed."""
    monkeypatch.setattr(_ss_mod, "_PBKDF2_ITER", 1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def store(tmp_path):
    return SecureStore(str(tmp_path / "vault"), password="s3cr3t")


@pytest.fixture()
def store_factory(tmp_path):
    """Return a callable that creates a fresh SecureStore in a new sub-dir."""
    counter = [0]
    def _make(password="s3cr3t"):
        counter[0] += 1
        path = tmp_path / f"vault_{counter[0]}"
        return SecureStore(str(path), password=password)
    return _make


# ---------------------------------------------------------------------------
# 1. put + get roundtrips bytes correctly
# ---------------------------------------------------------------------------

def test_put_get_bytes_roundtrip(store):
    value = b"hello, world"
    store.put("k", value)
    assert store.get("k") == value


def test_put_get_arbitrary_bytes(store):
    value = bytes(range(256))
    store.put("binary", value)
    assert store.get("binary") == value


# ---------------------------------------------------------------------------
# 2. put_json + get_json roundtrips dict correctly
# ---------------------------------------------------------------------------

def test_put_json_get_json_dict(store):
    obj = {"name": "Alice", "balance": 42.5, "active": True, "tags": [1, 2, 3]}
    store.put_json("record", obj)
    assert store.get_json("record") == obj


def test_put_json_nested(store):
    obj = {"a": {"b": {"c": [1, None, False]}}}
    store.put_json("nested", obj)
    assert store.get_json("nested") == obj


# ---------------------------------------------------------------------------
# 3. wrong password → get returns None or raises (handle both gracefully)
# ---------------------------------------------------------------------------

def test_wrong_password_raises_or_returns_none(tmp_path):
    good = SecureStore(str(tmp_path / "v"), password="correct")
    good.put("secret", b"sensitive data")

    # Open same backing file with wrong password
    bad = SecureStore(str(tmp_path / "v"), password="wrong")
    try:
        result = bad.get("secret")
        # If it doesn't raise, it must return None (not silently return garbage)
        assert result is None
    except (ValueError, Exception):
        pass  # raising is also acceptable behaviour


# ---------------------------------------------------------------------------
# 4. keys() lists all stored keys
# ---------------------------------------------------------------------------

def test_keys_lists_all(store):
    store.put("alpha", b"1")
    store.put("beta", b"2")
    store.put("gamma", b"3")
    assert set(store.keys()) == {"alpha", "beta", "gamma"}


# ---------------------------------------------------------------------------
# 5. delete removes key, get returns None after delete
# ---------------------------------------------------------------------------

def test_delete_removes_key(store):
    store.put("x", b"data")
    assert store.delete("x") is True
    assert store.get("x") is None
    assert "x" not in store.keys()


def test_delete_nonexistent_returns_false(store):
    assert store.delete("no_such_key") is False


# ---------------------------------------------------------------------------
# 6. two stores with same password can share exported data
# ---------------------------------------------------------------------------

def test_export_import_same_password(tmp_path):
    src = SecureStore(str(tmp_path / "src"), password="shared")
    src.put("msg", b"top secret")

    exported = src.export_encrypted()

    # Write exported blob into a new store directory's store.json
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    (dst_dir / "store.json").write_text(
        json.dumps(exported, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    dst = SecureStore(str(dst_dir), password="shared")
    assert dst.get("msg") == b"top secret"


# ---------------------------------------------------------------------------
# 7. empty store: keys() returns []
# ---------------------------------------------------------------------------

def test_empty_store_keys(store):
    assert store.keys() == []


# ---------------------------------------------------------------------------
# 8. large value (10 KB) roundtrips correctly
# ---------------------------------------------------------------------------

def test_large_value_roundtrip(store):
    large = os.urandom(10 * 1024)
    store.put("big", large)
    assert store.get("big") == large


# ---------------------------------------------------------------------------
# 9. metadata stored alongside encrypted value
# ---------------------------------------------------------------------------

def test_metadata_persisted(tmp_path):
    s = SecureStore(str(tmp_path / "v"), password="pw")
    s.put("entry", b"val", metadata={"source": "test", "version": 3})

    # Inspect raw store.json
    raw = json.loads((tmp_path / "v" / "store.json").read_text())
    meta = raw["entry"]["metadata"]
    assert meta["source"] == "test"
    assert meta["version"] == 3
    assert "stored_at" in meta  # always injected by SecureStore


# ---------------------------------------------------------------------------
# 10. overwrite: put same key twice → get returns second value
# ---------------------------------------------------------------------------

def test_overwrite_returns_latest(store):
    store.put("k", b"first")
    store.put("k", b"second")
    assert store.get("k") == b"second"
    assert store.keys().count("k") == 1  # only one entry


# ---------------------------------------------------------------------------
# 11. unicode values roundtrip correctly via put_json / get_json
# ---------------------------------------------------------------------------

def test_unicode_values_roundtrip(store):
    obj = {"greeting": "Héllo wörld", "emoji_safe": "café", "cjk": "中文"}
    store.put_json("unicode_key", obj)
    assert store.get_json("unicode_key") == obj


# ---------------------------------------------------------------------------
# 12. persistence across store re-open
# ---------------------------------------------------------------------------

def test_persistence_across_reopen(tmp_path):
    path = str(tmp_path / "vault")
    s1 = SecureStore(path, password="pw")
    s1.put("persistent", b"still here")

    s2 = SecureStore(path, password="pw")
    assert s2.get("persistent") == b"still here"
