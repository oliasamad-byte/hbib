"""Per-track ranking state — incremental diffs for 🆕 / 👋 annotations."""

from __future__ import annotations

from . import cache

TRACKS = ("daily_small", "daily_mlm", "weekly")


def diff(track: str, current: list[str]) -> tuple[list[str], list[str]]:
    """Returns (added_now, dropped_since_last). Track is one of TRACKS."""
    if track not in TRACKS:
        raise ValueError(f"unknown track: {track}")
    return cache.diff_prior(track, current)


def commit(track: str, current: list[str]) -> None:
    """Save current list as the new "prior" for next scan."""
    if track not in TRACKS:
        raise ValueError(f"unknown track: {track}")
    cache.save_prior_ranking(track, current)
