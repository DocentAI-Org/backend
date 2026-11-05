"""Text search for list endpoints (specs/016): every word of the query must appear,
ignoring case and accents, in at least one of the list's fields."""

from typing import Annotated

from fastapi import Query
from sqlalchemy import ColumnElement, and_, func, literal, or_, true


def _folded(value) -> ColumnElement[str]:
    return func.lower(func.extensions.unaccent(func.coalesce(value, "")))


def words(q: str | None) -> list[str]:
    """The words of a query, with LIKE's wildcards escaped; none for a blank query."""
    return [
        w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        for w in (q or "").split()
    ]


def contains(field, word: str) -> ColumnElement[bool]:
    """True when `field` contains `word` (from `words`), ignoring case and accents."""
    pattern = func.concat("%", _folded(literal(word)), "%")
    return _folded(field).like(pattern, escape="\\")


def matches(q: str | None, *fields) -> ColumnElement[bool]:
    """True when each word of `q` is in some field; always true for a blank `q`."""
    terms = words(q)
    if not terms:
        return true()
    return and_(*(or_(*(contains(f, w) for f in fields)) for w in terms))


Search = Annotated[str | None, Query(max_length=200, description="Words to look for.")]
