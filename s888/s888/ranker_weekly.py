"""Weekly ranker — gate by Stage ∈ {1,2,3} AND catalyst ≥ N AND WTS ≥ M.

Per spec §9. Stage 4 is hard-blocked. Sort: WTS → breakout → catalyst →
stage-priority (2>1>3) → DTS.
"""

from __future__ import annotations

from .config import CFG
from .ranker_daily import ScoredTicker


def _stage_priority(stage: int) -> int:
    return {2: 0, 1: 1, 3: 2}.get(stage, 9)


def filter_weekly(scored: list[ScoredTicker], stages: dict[str, int],
                  catalyst_threshold: int | None = None,
                  wts_threshold: int | None = None) -> list[ScoredTicker]:
    """Apply the weekly gate (Stage hard-block + catalyst + WTS thresholds)."""
    cat_th = catalyst_threshold if catalyst_threshold is not None \
             else CFG.weekly_catalyst_threshold
    wts_th = wts_threshold if wts_threshold is not None \
             else CFG.weekly_wts_threshold
    out = []
    for t in scored:
        stage = stages.get(t.ticker, 4)
        if stage == 4:
            continue
        if t.catalyst_score < cat_th:
            continue
        if t.wts_total < wts_th:
            continue
        out.append(t)
    return out


def rank_weekly(scored: list[ScoredTicker], stages: dict[str, int],
                top_n: int | None = None) -> list[ScoredTicker]:
    qualifying = filter_weekly(scored, stages)
    qualifying.sort(key=lambda t: (
        -t.wts_total,
        -t.dts_breakout,
        -t.catalyst_score,
        _stage_priority(stages.get(t.ticker, 4)),
        -t.dts_total,
    ))
    top_n = top_n if top_n is not None else CFG.weekly_top_n
    return qualifying[:top_n]
