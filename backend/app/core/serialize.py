"""Convert SQLAlchemy rows to camelCase JSON dicts for the frontend."""
from typing import Any


def camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)


def to_dict(row: Any, exclude: tuple[str, ...] = ()) -> dict:
    if row is None:
        return None  # type: ignore[return-value]
    out = {}
    for col in row.__table__.columns:
        if col.key in exclude:
            continue
        out[camel(col.key)] = getattr(row, col.key)
    return out
