"""Helpers shared across tools/*.py."""
from __future__ import annotations

import enum


class Unset(enum.Enum):
    """Marks an update argument the caller didn't pass.

    Update tools need to tell "leave this field alone" apart from "clear it",
    and None already means the latter for nullable columns (a due date, a
    project link). `UNSET` is the default for the former.
    """

    UNSET = "UNSET"

    def __repr__(self) -> str:
        return "UNSET"


UNSET = Unset.UNSET
