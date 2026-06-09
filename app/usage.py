from __future__ import annotations

import json
import os
from pathlib import Path

from app.schemas import UsageStatus


class UsageLimitExceeded(Exception):
    pass


def _max_tests() -> int:
    return int(os.getenv("MAX_TESTS", "10"))


def _usage_file() -> Path:
    path = Path(os.getenv("USAGE_FILE", "data/usage_count.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_count_file() -> int:
    path = _usage_file()
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("count", 0))
    except (json.JSONDecodeError, ValueError, OSError):
        return 0


def _write_count_file(count: int) -> None:
    _usage_file().write_text(json.dumps({"count": count}), encoding="utf-8")


def _use_firestore() -> bool:
    return (
        os.getenv("USAGE_STORE", "file").lower() == "firestore"
        and bool(os.getenv("GOOGLE_CLOUD_PROJECT"))
    )


def _read_count() -> int:
    if not _use_firestore():
        return _read_count_file()
    from google.cloud import firestore

    client = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
    doc = client.collection("usage").document("global").get()
    if not doc.exists:
        return 0
    return int(doc.to_dict().get("count", 0))


def _write_count(count: int) -> None:
    if not _use_firestore():
        _write_count_file(count)
        return
    from google.cloud import firestore

    client = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
    client.collection("usage").document("global").set({"count": count})


def get_usage_status(*, unlimited: bool = False) -> UsageStatus:
    max_tests = _max_tests()
    if unlimited or max_tests <= 0:
        return UsageStatus(used=0, max_tests=0, remaining=999999)
    used = _read_count()
    return UsageStatus(used=used, max_tests=max_tests, remaining=max(0, max_tests - used))


def reserve_tests(count: int = 1, *, unlimited: bool = False) -> UsageStatus:
    max_tests = _max_tests()
    if unlimited or max_tests <= 0:
        return UsageStatus(used=0, max_tests=0, remaining=999999)

    used = _read_count()
    if used + count > max_tests:
        raise UsageLimitExceeded(
            f"QUOTA EXCEEDED: prototype limited to {max_tests} verifications"
        )
    new_count = used + count
    _write_count(new_count)
    return UsageStatus(used=new_count, max_tests=max_tests, remaining=max_tests - new_count)
