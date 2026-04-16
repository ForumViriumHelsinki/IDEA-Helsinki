"""Analyze how often FCD segment replacements straddle processing-cycle boundaries.

Read-only, throwaway diagnostic for issue #297. Compares each new segment in
``data/master_segment_history.json`` against ``data/archived_segment_history.json``
using the same geo-matching used in ``FcdUtils.update_segment_changelog``
(5 m buffer, 0.70 overlap threshold), bucketed by the gap between the archive
and add timestamps.

Usage::

    uv run --package idea-shared --directory shared python \
        ../../scripts/analyze_cross_cycle_replacements.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from idea_shared.lib.FcdUtils import find_matching_historical_segments

REPO_ROOT = Path(__file__).resolve().parent.parent
MASTER_PATH = REPO_ROOT / "data" / "master_segment_history.json"
ARCHIVE_PATH = REPO_ROOT / "data" / "archived_segment_history.json"

BUCKETS: list[tuple[str, timedelta | None]] = [
    ("same cycle (<=1m)", timedelta(minutes=1)),
    ("<1h", timedelta(hours=1)),
    ("1-6h", timedelta(hours=6)),
    ("6-24h", timedelta(hours=24)),
    ("1-7d", timedelta(days=7)),
    (">7d", None),
]


def _parse(dt: str | None) -> datetime | None:
    if not dt:
        return None
    try:
        return datetime.fromisoformat(dt).replace(tzinfo=None)
    except ValueError:
        return None


def _bucket(gap: timedelta) -> str:
    for name, upper in BUCKETS:
        if upper is None or gap <= upper:
            return name
    return ">7d"


def main() -> int:
    """Run cross-cycle replacement analysis and print a markdown summary."""
    if not MASTER_PATH.exists() or not ARCHIVE_PATH.exists():
        print(f"Missing data files: {MASTER_PATH} / {ARCHIVE_PATH}", file=sys.stderr)
        return 1

    master = json.loads(MASTER_PATH.read_text())
    archive = json.loads(ARCHIVE_PATH.read_text())

    # Index archive by date for cheap per-segment matching.
    archive_records = {
        old_id: rec
        for old_id, rec in archive.items()
        if _parse(rec.get("date_archived")) is not None
        and rec.get("current_geometry") is not None
    }

    counts: Counter[str] = Counter()
    already_inherited = 0
    no_match = 0
    total_new = 0

    for new_id, rec in master.items():
        date_added = _parse(rec.get("date_added"))
        current_geom = rec.get("current_geometry")
        if date_added is None or current_geom is None:
            continue
        total_new += 1

        if "geo_inherited_from" in rec:
            already_inherited += 1
            continue

        # Only consider archive entries older than this new segment.
        candidates = {
            old_id: arec
            for old_id, arec in archive_records.items()
            if (_parse(arec.get("date_archived")) or datetime.max) <= date_added
        }
        if not candidates:
            no_match += 1
            continue

        matches = find_matching_historical_segments({new_id: current_geom}, candidates)
        if new_id not in matches:
            no_match += 1
            continue

        old_id = matches[new_id]
        date_archived = _parse(archive_records[old_id].get("date_archived"))
        gap = date_added - date_archived  # type: ignore[operator]
        if gap.total_seconds() < 0:
            gap = timedelta(0)
        counts[_bucket(gap)] += 1

    print("# Cross-cycle segment replacement analysis\n")
    print(f"- Total new segments scanned: **{total_new}**")
    print(f"- Already marked `geo_inherited_from`: **{already_inherited}**")
    print(f"- Orphan (no geo match in archive): **{no_match}**")
    print("\n## Gap distribution for new segments with an archive match\n")
    print("| Bucket | Count |")
    print("|--------|------:|")
    for name, _ in BUCKETS:
        print(f"| {name} | {counts.get(name, 0)} |")

    cross_cycle = sum(counts[b] for b, _ in BUCKETS if b != "same cycle (<=1m)")
    matched = sum(counts.values())
    print()
    if matched:
        pct = 100.0 * cross_cycle / matched
        print(f"Cross-cycle matches: **{cross_cycle} / {matched}** ({pct:.1f}%)")
    if total_new:
        pct_all = 100.0 * cross_cycle / total_new
        print(f"Cross-cycle as share of all new segments: **{pct_all:.1f}%**")
    return 0


if __name__ == "__main__":
    sys.exit(main())
