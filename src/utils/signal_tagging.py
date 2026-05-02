"""
Signal tagging utilities for decision_log (migration 015).

Provides two deterministic hash helpers used when writing signal-tag columns:

    compute_feature_hash(features)   — sha256 of the feature vector dict
    compute_artifact_hash(path)      — sha256 of a model artifact file

Both return 64-character lowercase hex strings suitable for VARCHAR(64) columns.
Both are safe to call with empty/missing input; they return None rather than
raising, which matches the nullable semantics of the DB columns.

The artifact hash is cached by (path, mtime) so that repeated calls within the
same process (e.g. every 5-minute live-trading cycle) do not re-read the file.

Usage (emit site in live_trading_service.py):
    from src.utils.signal_tagging import compute_feature_hash, compute_artifact_hash
    from pathlib import Path

    fhash = compute_feature_hash(feature_dict)          # or None
    ahash = compute_artifact_hash(Path("models/..."))   # or None
"""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level LRU cache for artifact hashes.
# Key: (str(path), mtime_ns)  Value: sha256 hex string
# ---------------------------------------------------------------------------
_artifact_cache: Dict[tuple, str] = {}


def compute_feature_hash(features: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Compute a stable SHA-256 fingerprint of a feature vector.

    The dict is serialised with sort_keys=True so key ordering never affects
    the hash.  Non-JSON-serialisable values (numpy floats, Decimal, etc.) are
    coerced to strings via default=str — this is intentional: we want a
    consistent hash even when the pipeline mixes numeric types.

    Args:
        features: Feature vector dict.  Nested dicts and lists are supported.
            Pass None (or empty dict) when no feature vector was used — the
            function returns None in that case so the DB column stays NULL.

    Returns:
        64-character lowercase hex SHA-256 string, or None if features is
        None or an empty dict.

    Examples:
        >>> compute_feature_hash({"rsi": 45.2, "atr": 0.82})
        'a3f1...'   # 64-char hex
        >>> compute_feature_hash({})
        None
        >>> compute_feature_hash(None)
        None

    Edge cases:
        - numpy.float32 values: coerced to str — hash changes vs float64 for
          the same numeric value.  Callers should normalise types before hashing
          if cross-type stability matters.
        - Circular refs in the dict will raise ValueError from json.dumps.
    """
    if not features:
        return None

    try:
        serialised = json.dumps(features, sort_keys=True, default=str)
        return hashlib.sha256(serialised.encode()).hexdigest()
    except Exception as exc:
        # Never crash the signal pipeline over a hash failure
        logger.warning("compute_feature_hash_failed", error=str(exc))
        return None


def compute_artifact_hash(path: Optional[Path]) -> Optional[str]:
    """
    Compute a SHA-256 fingerprint of a model artifact file's bytes.

    Results are cached by (absolute_path, mtime_ns) so that repeated calls
    within the same process do not re-read the file.  The cache is invalidated
    automatically when the file's mtime changes (i.e. when a new model is
    trained and deployed in-place).

    Args:
        path: Filesystem path to the artifact (model.json, model.pkl, etc.).
            Pass None when no ML model was used — returns None immediately.

    Returns:
        64-character lowercase hex SHA-256 string, or None if path is None,
        the file does not exist, or the file cannot be read.

    Examples:
        >>> compute_artifact_hash(Path("models/reversal_classifier/CrudeOIL_H1/model.json"))
        'b7d9...'   # 64-char hex
        >>> compute_artifact_hash(None)
        None
        >>> compute_artifact_hash(Path("nonexistent.pkl"))
        None

    Edge cases:
        - Very large model files (>500 MB): this reads the whole file into
          memory.  For such files callers should pass the path of a small
          side-car hash file instead (write it at training time).
        - Symlinks: resolved by Path.stat() on the symlink target.
    """
    if path is None:
        return None

    path = Path(path)
    if not path.exists():
        return None

    try:
        stat = path.stat()
        cache_key = (str(path.resolve()), stat.st_mtime_ns)

        cached = _artifact_cache.get(cache_key)
        if cached is not None:
            return cached

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        _artifact_cache[cache_key] = digest
        # Evict stale entries for the same path (old mtime) to avoid unbounded growth
        for stale_key in [k for k in _artifact_cache if k[0] == str(path.resolve()) and k != cache_key]:
            del _artifact_cache[stale_key]
        return digest

    except OSError as exc:
        logger.warning("compute_artifact_hash_read_error", path=str(path), error=str(exc))
        return None
    except Exception as exc:
        logger.warning("compute_artifact_hash_failed", path=str(path), error=str(exc))
        return None
