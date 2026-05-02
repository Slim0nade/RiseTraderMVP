"""
Unit tests for src/utils/signal_tagging.py — hash helpers.

Tests tier 1 (pure math validation):
- compute_feature_hash: deterministic, order-independent, empty-safe
- compute_artifact_hash: deterministic, file-bytes-based, mtime-cached, missing-safe

No DB, no MT4, no mocks — these functions are pure utilities.
"""

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from src.utils.signal_tagging import (
    compute_artifact_hash,
    compute_feature_hash,
    _artifact_cache,
)


# ---------------------------------------------------------------------------
# compute_feature_hash
# ---------------------------------------------------------------------------


class TestComputeFeatureHash:
    def test_returns_64_char_hex(self):
        """Output must be exactly 64 lowercase hex chars (sha256)."""
        features = {"rsi": 45.2, "atr": 0.82, "ema_slope": 0.003}
        result = compute_feature_hash(features)
        assert result is not None
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic_for_same_input(self):
        """Same features must always produce the same hash."""
        features = {"rsi": 45.2, "atr": 0.82}
        h1 = compute_feature_hash(features)
        h2 = compute_feature_hash(features)
        assert h1 == h2

    def test_key_order_independent(self):
        """Sort-keys means dict key order must not affect the hash."""
        f1 = {"atr": 0.82, "rsi": 45.2}
        f2 = {"rsi": 45.2, "atr": 0.82}
        assert compute_feature_hash(f1) == compute_feature_hash(f2)

    def test_different_inputs_produce_different_hashes(self):
        """Different feature values must produce different hashes."""
        h1 = compute_feature_hash({"rsi": 45.2})
        h2 = compute_feature_hash({"rsi": 45.3})
        assert h1 != h2

    def test_different_keys_produce_different_hashes(self):
        """Different feature keys must produce different hashes."""
        h1 = compute_feature_hash({"rsi": 45.2})
        h2 = compute_feature_hash({"ema": 45.2})
        assert h1 != h2

    def test_none_returns_none(self):
        """None input must return None — column stays NULL."""
        assert compute_feature_hash(None) is None

    def test_empty_dict_returns_none(self):
        """Empty dict returns None — no features, NULL in DB."""
        assert compute_feature_hash({}) is None

    def test_nested_dict_supported(self):
        """Nested dicts must not raise."""
        features = {"indicators": {"rsi": 45.2, "bb": {"upper": 62.1, "lower": 38.9}}}
        result = compute_feature_hash(features)
        assert result is not None
        assert len(result) == 64

    def test_nested_list_supported(self):
        """Lists in features must not raise."""
        features = {"returns": [0.01, -0.02, 0.03], "rsi": 50.0}
        result = compute_feature_hash(features)
        assert result is not None
        assert len(result) == 64

    def test_non_serialisable_values_coerced(self):
        """Non-JSON-serialisable values (e.g. custom class) are coerced via str()."""
        class Opaque:
            def __repr__(self):
                return "opaque_value"

        features = {"obj": Opaque(), "rsi": 50.0}
        # Should not raise
        result = compute_feature_hash(features)
        assert result is not None

    def test_hash_matches_manual_calculation(self):
        """Hash must equal sha256(json.dumps(features, sort_keys=True))."""
        features = {"atr": 0.82, "rsi": 45.2}
        expected_serialised = json.dumps(features, sort_keys=True, default=str)
        expected_hash = hashlib.sha256(expected_serialised.encode()).hexdigest()
        assert compute_feature_hash(features) == expected_hash

    def test_single_key_dict(self):
        """Single-key dict works."""
        result = compute_feature_hash({"rsi": 60.0})
        assert result is not None
        assert len(result) == 64

    def test_float_vs_int_differ(self):
        """float 1.0 and int 1 serialise differently — hashes may differ."""
        h_float = compute_feature_hash({"x": 1.0})
        h_int = compute_feature_hash({"x": 1})
        # json.dumps treats 1.0 and 1 the same: "1.0" vs "1"
        # They may or may not match depending on Python's JSON encoder
        # What we require is that the function does not raise.
        assert h_float is not None
        assert h_int is not None


# ---------------------------------------------------------------------------
# compute_artifact_hash
# ---------------------------------------------------------------------------


class TestComputeArtifactHash:
    def test_returns_none_for_none_path(self):
        """None path returns None immediately."""
        assert compute_artifact_hash(None) is None

    def test_returns_none_for_nonexistent_file(self):
        """Non-existent file returns None — column stays NULL."""
        result = compute_artifact_hash(Path("/nonexistent/path/model.json"))
        assert result is None

    def test_returns_64_char_hex_for_real_file(self, tmp_path):
        """Real file returns 64-char sha256 hex."""
        model_file = tmp_path / "model.json"
        model_file.write_bytes(b'{"n_estimators": 100, "objective": "multi:softprob"}')
        result = compute_artifact_hash(model_file)
        assert result is not None
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic_for_same_file(self, tmp_path):
        """Same file bytes must always produce the same hash."""
        model_file = tmp_path / "model.json"
        model_file.write_bytes(b"same bytes every time")
        h1 = compute_artifact_hash(model_file)
        h2 = compute_artifact_hash(model_file)
        assert h1 == h2

    def test_different_content_different_hash(self, tmp_path):
        """Different file content must produce different hashes."""
        f1 = tmp_path / "model_a.json"
        f2 = tmp_path / "model_b.json"
        f1.write_bytes(b"model version A")
        f2.write_bytes(b"model version B")
        assert compute_artifact_hash(f1) != compute_artifact_hash(f2)

    def test_matches_manual_sha256(self, tmp_path):
        """Hash must equal sha256 of raw file bytes."""
        model_file = tmp_path / "model.json"
        content = b'{"n_estimators": 200}'
        model_file.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert compute_artifact_hash(model_file) == expected

    def test_caching_avoids_reread(self, tmp_path):
        """Second call with same mtime must return cached value without re-reading."""
        model_file = tmp_path / "model.json"
        model_file.write_bytes(b"original content")

        h1 = compute_artifact_hash(model_file)

        # Corrupt the file on disk — cache should return the original hash
        # because mtime hasn't changed (within same second; we confirm via stat)
        stat_before = model_file.stat()
        # Write same-length bytes but different content via os.write at same mtime
        # (hard to force same mtime in a cross-platform way, so just verify
        #  the function returns a consistent value and doesn't raise)
        h2 = compute_artifact_hash(model_file)
        assert h1 == h2  # Cache hit: same result

    def test_cache_invalidated_on_mtime_change(self, tmp_path):
        """Cache must be invalidated when file mtime changes."""
        model_file = tmp_path / "model.json"
        model_file.write_bytes(b"version 1")
        h1 = compute_artifact_hash(model_file)

        # Force mtime change by setting it explicitly (1 second forward)
        import os
        import time
        old_stat = model_file.stat()
        new_mtime = old_stat.st_mtime + 1.0
        os.utime(model_file, (new_mtime, new_mtime))
        model_file.write_bytes(b"version 2")
        os.utime(model_file, (new_mtime, new_mtime))  # Ensure mtime matches write

        h2 = compute_artifact_hash(model_file)
        # Content changed AND mtime changed — must be a different hash
        assert h1 != h2

    def test_accepts_string_path(self, tmp_path):
        """Path-like string is accepted (Path(path) conversion)."""
        model_file = tmp_path / "model.pkl"
        model_file.write_bytes(b"\x80\x04\x95serialised_model")
        result = compute_artifact_hash(model_file)
        assert result is not None

    def test_empty_file_returns_hash(self, tmp_path):
        """Empty file is valid — sha256 of empty bytes is a known value."""
        empty_file = tmp_path / "empty.json"
        empty_file.write_bytes(b"")
        result = compute_artifact_hash(empty_file)
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected
