from __future__ import annotations

import base64
import os
from binascii import Error as Base64Error

_MB = 1024 * 1024


class UploadSizeError(ValueError):
    """Raised when an uploaded Dash data URL exceeds the configured size limit."""


def _limit_bytes(env_name: str, default_mb: int) -> int:
    raw = os.getenv(env_name)
    if raw is None:
        return default_mb * _MB
    try:
        value = float(raw)
    except ValueError:
        return default_mb * _MB
    return max(1, int(value * _MB))


MAX_PMID_UPLOAD_BYTES = _limit_bytes("NETMEDEX_MAX_PMID_UPLOAD_MB", 5)
MAX_PUBTATOR_UPLOAD_BYTES = _limit_bytes("NETMEDEX_MAX_PUBTATOR_UPLOAD_MB", 50)
MAX_GRAPH_UPLOAD_BYTES = _limit_bytes("NETMEDEX_MAX_GRAPH_UPLOAD_MB", 100)


def format_size(num_bytes: int) -> str:
    return f"{num_bytes / _MB:.0f} MB"


def split_upload_data(contents: str, *, label: str) -> tuple[str, str]:
    try:
        content_type, content_string = str(contents).split(",", 1)
    except ValueError as exc:
        raise ValueError(f"{label} upload is not a valid data URL.") from exc
    return content_type, content_string


def estimate_upload_bytes(contents: str, *, label: str) -> int:
    _, content_string = split_upload_data(contents, label=label)
    compact = "".join(content_string.split())
    if not compact:
        return 0
    padding = compact.count("=")
    return max(0, (len(compact) * 3) // 4 - padding)


def validate_upload_size(contents: str, *, max_bytes: int, label: str) -> None:
    estimated = estimate_upload_bytes(contents, label=label)
    if estimated > max_bytes:
        raise UploadSizeError(
            f"{label} upload is too large ({format_size(estimated)}). "
            f"The limit is {format_size(max_bytes)}."
        )


def decode_upload_bytes(contents: str, *, max_bytes: int, label: str) -> tuple[str, bytes]:
    content_type, content_string = split_upload_data(contents, label=label)
    validate_upload_size(contents, max_bytes=max_bytes, label=label)
    compact = "".join(content_string.split())
    try:
        return content_type, base64.b64decode(compact, validate=True)
    except Base64Error as exc:
        raise ValueError(f"{label} upload is not valid base64 data.") from exc


def decode_upload_text(contents: str, *, max_bytes: int, label: str) -> tuple[str, str]:
    content_type, decoded_bytes = decode_upload_bytes(
        contents,
        max_bytes=max_bytes,
        label=label,
    )
    try:
        return content_type, decoded_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return content_type, decoded_bytes.decode("latin-1")
