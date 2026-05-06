"""Place menu observation aggregation and menu name cleaning.

Builds monthly_place_menu_observations from raw place_reviews.
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from discoursekit.core.db import get_connection, upsert_observation


_PRICE_RE = re.compile(
    r"[\d,]+원|[\d,]+₩|\d{3,}[,.]?\d*\s*$"
)
_OPTION_RE = re.compile(
    r"\(.*?\)|\[.*?\]"
)
_SIZE_RE = re.compile(
    r"\b(소|중|대|S|M|L|XL|레귤러|라지|그란데|벤티|톨)\b",
    re.IGNORECASE,
)
_TRAILING_JUNK = re.compile(
    r"[_\-·/]+$|^[_\-·/]+"
)


def normalize_menu_name(raw: str) -> str:
    """Clean a raw menu_item string to a standard menu name.

    Removes prices, size/option modifiers, parenthetical info,
    and extraneous whitespace.
    """
    if not raw:
        return ""
    name = str(raw).strip()
    name = _PRICE_RE.sub("", name)
    name = _OPTION_RE.sub("", name)
    name = _SIZE_RE.sub("", name)
    name = _TRAILING_JUNK.sub("", name)
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) < 2:
        return ""
    return name


@dataclass
class ObservationSummary:
    """Summary returned after building observations."""
    total_reviews: int
    reviews_with_menu: int
    unique_places: int
    unique_menus: int
    observations_written: int


def build_observations(
    db_path: "str | Any",
    project_id: str,
    region_id: str = "",
    progress_callback: Any = None,
) -> ObservationSummary:
    """Build monthly_place_menu_observations from place_reviews.

    Groups reviews by (place_id, review_month, normalized_menu_name),
    computes review_count, first_seen_flag, continued_flag.
    """
    from pathlib import Path
    conn = get_connection(Path(db_path) if not isinstance(db_path, Path) else db_path)

    try:
        rows = conn.execute(
            """
            SELECT place_id, place_name, review_month, menu_item
            FROM place_reviews
            WHERE project_id = ? AND menu_item IS NOT NULL AND menu_item != ''
            """,
            (project_id,),
        ).fetchall()

        total_reviews_row = conn.execute(
            "SELECT COUNT(*) AS n FROM place_reviews WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        total_reviews = int(total_reviews_row["n"])

        if progress_callback:
            progress_callback(f"메뉴 정제 중... ({len(rows)}건)")

        agg: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        place_names: dict[str, str] = {}

        for row in rows:
            normalized = normalize_menu_name(row["menu_item"])
            if not normalized:
                continue
            key = (row["place_id"], row["review_month"] or "", normalized)
            agg[key].append(row["menu_item"])
            place_names[row["place_id"]] = row["place_name"]

        first_seen: dict[tuple[str, str], str] = {}
        for place_id, month, menu_name in sorted(agg.keys()):
            combo = (place_id, menu_name)
            if combo not in first_seen:
                first_seen[combo] = month

        month_counts: dict[tuple[str, str], int] = defaultdict(int)
        for (place_id, month, menu_name) in agg:
            month_counts[(place_id, menu_name)] += 1

        if progress_callback:
            progress_callback(f"관측 테이블 생성 중... ({len(agg)}건)")

        conn.execute(
            "DELETE FROM monthly_place_menu_observations WHERE project_id = ?",
            (project_id,),
        )

        written = 0
        for (place_id, month, menu_name), raw_items in agg.items():
            examples = sorted(set(raw_items))[:5]
            is_first = first_seen.get((place_id, menu_name)) == month
            is_continued = month_counts.get((place_id, menu_name), 0) > 1

            upsert_observation(conn, {
                "project_id": project_id,
                "region_id": region_id,
                "place_id": place_id,
                "place_name": place_names.get(place_id, ""),
                "review_month": month,
                "normalized_menu_name": menu_name,
                "raw_menu_examples": "|".join(examples),
                "review_count": len(raw_items),
                "first_seen_flag": int(is_first),
                "continued_flag": int(is_continued),
            })
            written += 1

        conn.commit()

        unique_places = len(place_names)
        unique_menus = len({
            menu for (_, _, menu) in agg
        })

        return ObservationSummary(
            total_reviews=total_reviews,
            reviews_with_menu=len(rows),
            unique_places=unique_places,
            unique_menus=unique_menus,
            observations_written=written,
        )
    finally:
        conn.close()


def get_place_summary(
    conn: sqlite3.Connection,
    project_id: str,
) -> list[dict[str, Any]]:
    """Return per-place summary: review count, menu count, first observed month."""
    rows = conn.execute(
        """
        SELECT
            place_id,
            place_name,
            COUNT(*) AS review_count,
            COUNT(DISTINCT normalized_menu_name) AS menu_count,
            MIN(review_month) AS first_observed
        FROM monthly_place_menu_observations
        WHERE project_id = ?
        GROUP BY place_id, place_name
        ORDER BY review_count DESC
        """,
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_menu_summary(
    conn: sqlite3.Connection,
    project_id: str,
) -> list[dict[str, Any]]:
    """Return per-menu summary: place count, total reviews, first observed month."""
    rows = conn.execute(
        """
        SELECT
            normalized_menu_name,
            COUNT(DISTINCT place_id) AS place_count,
            SUM(review_count) AS total_reviews,
            MIN(review_month) AS first_observed
        FROM monthly_place_menu_observations
        WHERE project_id = ?
        GROUP BY normalized_menu_name
        ORDER BY place_count DESC, total_reviews DESC
        """,
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_first_seen_by_channel(
    conn: sqlite3.Connection,
    project_id: str,
    keyword: str,
) -> list[dict[str, Any]]:
    """Find first occurrence of a keyword across all channels (articles + place reviews).

    Returns list of {channel, first_seen_at, first_seen_text}.
    """
    results: list[dict[str, Any]] = []

    article_rows = conn.execute(
        """
        SELECT a.source, a.date AS first_date, a.title
        FROM articles a
        INNER JOIN (
            SELECT source, MIN(date) AS min_date
            FROM articles
            WHERE project_id = ? AND is_active = 1
              AND (title LIKE ? OR body_excerpt LIKE ?)
            GROUP BY source
        ) m ON a.source = m.source AND a.date = m.min_date
        WHERE a.project_id = ? AND a.is_active = 1
        ORDER BY a.date
        """,
        (project_id, f"%{keyword}%", f"%{keyword}%", project_id),
    ).fetchall()
    for row in article_rows:
        results.append({
            "channel": row["source"],
            "first_seen_at": row["first_date"],
            "first_seen_text": row["title"],
        })

    place_row = conn.execute(
        """
        SELECT review_month AS first_month, place_name, menu_item
        FROM place_reviews
        WHERE project_id = ?
          AND (menu_item LIKE ? OR body LIKE ?)
        ORDER BY review_month
        LIMIT 1
        """,
        (project_id, f"%{keyword}%", f"%{keyword}%"),
    ).fetchone()
    if place_row and place_row["first_month"]:
        results.append({
            "channel": "naver_place",
            "first_seen_at": place_row["first_month"],
            "first_seen_text": place_row["menu_item"] or place_row["place_name"],
        })

    results.sort(key=lambda r: r.get("first_seen_at") or "9999")
    return results
