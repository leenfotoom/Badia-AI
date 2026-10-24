"""Derived national-priority ranking for one horizon's cells.

This never alters ``risk_score``.  It only orders cells that have a valid
score, so field teams can decide where to begin.  It is a within-snapshot
ordering, NOT a drought probability and NOT a field diagnosis.

Rules (mirrored exactly in frontend/src/priority.js):
* Only cells with a finite risk_score are ranked; others get null fields.
* Competition ranking ("1224"): tied scores share the best (lowest) rank.
* percentile = share (%) of ranked cells whose score is >= this cell's score
  (tie-inclusive), rounded half-up to 2 decimals.  Smaller = higher priority.
* Band thresholds use the same tie-inclusive count with integer arithmetic,
  so a tied cell is never placed in a smaller band than its tie group allows.
* Median is the median of valid scores.
"""

from __future__ import annotations

import math
from typing import Any

BANDS = ((1, "Top 1%"), (5, "Top 5%"), (10, "Top 10%"))
BAND_LABELS = tuple(label for _, label in BANDS)
REMAINING = "Remaining"


def _valid(score: Any) -> bool:
    return (
        isinstance(score, (int, float))
        and not isinstance(score, bool)
        and math.isfinite(score)
    )


def priority_band(at_or_above: int, total: int) -> str:
    for pct, label in BANDS:
        if at_or_above * 100 <= pct * total:
            return label
    return REMAINING


def priority_percentile(at_or_above: int, total: int) -> float:
    """Return a tie-inclusive percentage with deterministic half-up rounding.

    Percentiles are non-negative, so integer arithmetic avoids both Python's
    ties-to-even ``round`` and binary floating-point edge cases in JavaScript.
    The frontend mirrors this exact hundredths-of-a-percent formula.
    """
    if total <= 0 or not 1 <= at_or_above <= total:
        raise ValueError("at_or_above must be between 1 and total")
    numerator = at_or_above * 10_000
    hundredths = (2 * numerator + total) // (2 * total)
    return hundredths / 100


def national_median(cells: list[dict[str, Any]]) -> float | None:
    scores = sorted(c["risk_score"] for c in cells if _valid(c.get("risk_score")))
    if not scores:
        return None
    mid = len(scores) // 2
    return scores[mid] if len(scores) % 2 else (scores[mid - 1] + scores[mid]) / 2


def add_national_priority(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return new cell dicts (input order kept) with national_priority_* fields."""
    scores = sorted(
        (c["risk_score"] for c in cells if _valid(c.get("risk_score"))), reverse=True
    )
    total = len(scores)
    median = national_median(cells)
    first_index: dict[float, int] = {}
    last_index: dict[float, int] = {}
    for i, s in enumerate(scores):
        first_index.setdefault(s, i)
        last_index[s] = i

    out = []
    for cell in cells:
        score = cell.get("risk_score")
        enriched = dict(cell)
        if _valid(score) and total:
            rank = first_index[score] + 1
            at_or_above = last_index[score] + 1
            enriched.update(
                national_priority_rank=rank,
                national_priority_total=total,
                national_priority_percentile=priority_percentile(at_or_above, total),
                national_priority_tied_count=at_or_above - first_index[score],
                priority_band=priority_band(at_or_above, total),
                national_median_score=median,
            )
        else:
            enriched.update(
                national_priority_rank=None,
                national_priority_total=total or None,
                national_priority_percentile=None,
                national_priority_tied_count=None,
                priority_band=None,
                national_median_score=median,
            )
        out.append(enriched)
    return out


def select_priority(
    cells: list[dict[str, Any]],
    band: str | None = None,
    limit: int | None = None,
    include_cutoff_ties: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select ranked cells and report exactly how the cutoff was applied.

    Cells are ordered by (rank, cell_id).  ``limit`` cuts that ordered list.
    Competition ranking means several cells can share the cutoff rank:

    * ``include_cutoff_ties=False`` returns exactly ``limit`` rows, which may
      split a tie group; the metadata then reports the omitted tied cells.
    * ``include_cutoff_ties=True`` also returns every other cell that shares
      the cutoff rank, so a tie group is never split (count may exceed limit).

    Ranks, scores and bands are never altered.
    """
    if band is not None and band not in BAND_LABELS:
        raise ValueError(f"band must be one of: {', '.join(BAND_LABELS)}")
    if limit is not None and limit < 0:
        raise ValueError("limit must be zero or greater")

    ranked = [c for c in cells if c.get("national_priority_rank") is not None]
    if band:
        keep = BAND_LABELS[: BAND_LABELS.index(band) + 1]
        ranked = [c for c in ranked if c["priority_band"] in keep]
    ranked.sort(key=lambda c: (c["national_priority_rank"], str(c["cell_id"])))

    if limit is None or limit >= len(ranked):
        selected = ranked
    else:
        selected = ranked[:limit]

    cutoff_rank = selected[-1]["national_priority_rank"] if selected else None
    if (
        include_cutoff_ties
        and limit is not None
        and selected
        and len(selected) < len(ranked)
    ):
        selected = [c for c in ranked if c["national_priority_rank"] <= cutoff_rank]

    group_size = (
        sum(1 for c in ranked if c["national_priority_rank"] == cutoff_rank)
        if cutoff_rank is not None
        else 0
    )
    included = (
        sum(1 for c in selected if c["national_priority_rank"] == cutoff_rank)
        if cutoff_rank is not None
        else 0
    )
    meta = {
        "requested_limit": limit,
        "include_cutoff_ties": include_cutoff_ties,
        "returned_count": len(selected),
        "cutoff_rank": cutoff_rank,
        "cutoff_tie_group_size": group_size,
        "cutoff_ties_included": included,
        "cutoff_ties_omitted": group_size - included,
        "cutoff_tie_group_split": group_size - included > 0,
        "extra_cells_beyond_limit": (
            max(len(selected) - limit, 0) if limit is not None else 0
        ),
    }
    return selected, meta


def top_priority(
    cells: list[dict[str, Any]],
    band: str | None = None,
    limit: int | None = None,
    include_cutoff_ties: bool = False,
) -> list[dict[str, Any]]:
    """Ranked cells ordered by (rank, cell_id) for deterministic output."""
    return select_priority(cells, band, limit, include_cutoff_ties)[0]
