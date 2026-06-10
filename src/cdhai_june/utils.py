from __future__ import annotations

import json
import math
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def slugify(value: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "-", value.strip()).strip("-").lower()
    return slug or fallback


def safe_path_segment(value: str, fallback: str = "item", max_length: int = 80) -> str:
    """Return a stable single path segment for untrusted identifiers."""
    original = str(value)
    slug = slugify(original, fallback=fallback)
    reserved_windows_names = {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
    if slug in reserved_windows_names:
        slug = fallback
    needs_hash = slug != original.strip().lower() or len(slug) > max_length
    if needs_hash:
        digest = sha256(original.encode("utf-8")).hexdigest()[:8]
        room = max(1, max_length - len(digest) - 1)
        slug = f"{slug[:room].rstrip('-')}-{digest}"
    return slug[:max_length].strip("-") or fallback


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        number = float(value)
        return None if math.isnan(number) or math.isinf(number) else number
    if isinstance(value, (np.ndarray,)):
        return [to_jsonable(item) for item in value.tolist()]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(to_jsonable(payload), handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def compact_text(text: str, max_chars: int = 1200) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."
