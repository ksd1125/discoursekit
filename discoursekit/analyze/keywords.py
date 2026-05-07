"""Keyword frequency and before/after keyword trend analysis."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import statistics
from typing import Iterable

from discoursekit.core.db import get_connection


_kiwi_instance = None


DEFAULT_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "news",
    "article",
    "기자",
    "뉴스",
    "관련",
    "대한",
    "이번",
    "지난",
    "오늘",
    "내일",
    "했다",
    "한다",
}


@dataclass(frozen=True)
class KeywordFrequencyResult:
    """Keyword frequency result for active articles."""

    keywords: list[tuple[str, int]]
    total_tokens: int
    unique_tokens: int
    source_field: str
    tokenizer: str
    stopwords_applied: int
    frequency_stats: dict
    core_cutoff: int
    core_keywords: list[tuple[str, int]]
    main_keywords: list[tuple[str, int]]
    longtail_count: int
    concentration: float


@dataclass(frozen=True)
class KeywordTrendsResult:
    """Keyword movement result around a cutoff date."""

    before_keywords: list[tuple[str, int]]
    after_keywords: list[tuple[str, int]]
    risers: list[tuple[str, int, int]]
    decliners: list[tuple[str, int, int]]
    new_entries: list[tuple[str, int]]
    cutoff_date: str


def compute_keyword_frequency(
    db_path: Path,
    project_id: str,
    top_n: int = 50,
    min_count: int = 2,
    stopwords: list[str] | None = None,
    use_morpheme: bool = True,
) -> KeywordFrequencyResult:
    """Compute keyword frequencies for active articles."""
    rows = _active_article_rows(db_path, project_id)
    counter, total_tokens, source_field, tokenizer, stopwords_applied = _count_keywords(
        rows,
        min_count=min_count,
        stopwords=stopwords,
        use_morpheme=use_morpheme,
    )
    ranked = counter.most_common(top_n)
    all_keywords = counter.most_common()
    counts = [count for _, count in all_keywords]
    frequency_stats = compute_keyword_stats(counts)
    core_cutoff = int(round(frequency_stats["mean"] + frequency_stats["std"])) if counts else 0
    if counts and core_cutoff < 1:
        core_cutoff = 1
    mean_cutoff = float(frequency_stats["mean"])
    core_keywords = [(keyword, count) for keyword, count in all_keywords if count >= core_cutoff]
    main_keywords = [(keyword, count) for keyword, count in all_keywords if count >= mean_cutoff]
    longtail_count = len([count for count in counts if count < mean_cutoff])
    top_sum = sum(count for _, count in ranked)
    concentration = top_sum / total_tokens * 100.0 if total_tokens else 0.0

    return KeywordFrequencyResult(
        keywords=ranked,
        total_tokens=total_tokens,
        unique_tokens=len(counter),
        source_field=source_field,
        tokenizer=tokenizer,
        stopwords_applied=stopwords_applied,
        frequency_stats=frequency_stats,
        core_cutoff=core_cutoff,
        core_keywords=core_keywords,
        main_keywords=main_keywords,
        longtail_count=longtail_count,
        concentration=round(concentration, 1),
    )


def compute_keyword_stats(counts: list[int]) -> dict:
    """Return descriptive statistics for keyword frequency counts."""
    if not counts:
        return {"mean": 0, "std": 0, "median": 0, "q1": 0, "q3": 0}
    sorted_counts = sorted(counts)
    n = len(sorted_counts)
    mean = statistics.mean(sorted_counts)
    std = statistics.stdev(sorted_counts) if n > 1 else 0
    return {
        "mean": round(mean, 1),
        "std": round(std, 1),
        "median": sorted_counts[n // 2],
        "q1": sorted_counts[n // 4],
        "q3": sorted_counts[(3 * n) // 4],
    }


def compute_keyword_trends(
    db_path: Path,
    project_id: str,
    cutoff_date: str,
    top_n: int = 20,
    min_count: int = 2,
    stopwords: list[str] | None = None,
) -> KeywordTrendsResult:
    """Compare keyword ranks before and after ``cutoff_date``."""
    before_rows = _active_article_rows(db_path, project_id, before=cutoff_date)
    after_rows = _active_article_rows(db_path, project_id, after_or_on=cutoff_date)
    before_counter, _, _, _, _ = _count_keywords(
        before_rows,
        min_count=min_count,
        stopwords=stopwords,
        use_morpheme=True,
    )
    after_counter, _, _, _, _ = _count_keywords(
        after_rows,
        min_count=min_count,
        stopwords=stopwords,
        use_morpheme=True,
    )
    before_keywords = before_counter.most_common(top_n)
    after_keywords = after_counter.most_common(top_n)
    before_ranks = {keyword: idx + 1 for idx, (keyword, _) in enumerate(before_keywords)}
    after_ranks = {keyword: idx + 1 for idx, (keyword, _) in enumerate(after_keywords)}

    risers = []
    decliners = []
    for keyword in set(before_ranks) & set(after_ranks):
        before_rank = before_ranks[keyword]
        after_rank = after_ranks[keyword]
        if before_rank - after_rank >= 5:
            risers.append((keyword, before_rank, after_rank))
        elif after_rank - before_rank >= 5:
            decliners.append((keyword, before_rank, after_rank))

    new_entries = [
        (keyword, count)
        for keyword, count in after_keywords
        if keyword not in before_ranks
    ]
    return KeywordTrendsResult(
        before_keywords=before_keywords,
        after_keywords=after_keywords,
        risers=sorted(risers, key=lambda item: item[1] - item[2], reverse=True),
        decliners=sorted(decliners, key=lambda item: item[2] - item[1], reverse=True),
        new_entries=new_entries,
        cutoff_date=cutoff_date,
    )


def _active_article_rows(
    db_path: Path,
    project_id: str,
    before: str | None = None,
    after_or_on: str | None = None,
) -> list[dict]:
    where = "WHERE project_id = ? AND is_active = 1"
    params: list[str] = [project_id]
    if before is not None:
        where += " AND date < ?"
        params.append(before)
    if after_or_on is not None:
        where += " AND date >= ?"
        params.append(after_or_on)

    conn = get_connection(db_path)
    try:
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT title, body_excerpt, keywords
                FROM articles
                {where}
                ORDER BY date, article_id
                """,
                tuple(params),
            ).fetchall()
        ]
    finally:
        conn.close()


def _count_keywords(
    rows: Iterable[dict],
    min_count: int,
    stopwords: list[str] | None,
    use_morpheme: bool,
) -> tuple[Counter[str], int, str, str, int]:
    stopword_set = set(DEFAULT_STOPWORDS)
    stopword_set.update(stopwords or [])
    raw_tokens: list[str] = []
    source_field = "meta_keywords"
    tokenizer = "split"

    if use_morpheme:
        try:
            for row in rows:
                text = f"{row.get('title') or ''} {row.get('body_excerpt') or ''}"
                raw_tokens.extend(_tokenize_with_kiwi(text))
            if not raw_tokens:
                raise ValueError("No morpheme tokens extracted")
            source_field = "morpheme"
            tokenizer = "kiwipiepy"
        except Exception:
            raw_tokens = []
            for row in rows:
                raw_tokens.extend(_split_meta_keywords(row.get("keywords") or ""))
            source_field = "meta_keywords"
            tokenizer = "split"
    else:
        for row in rows:
            raw_tokens.extend(_split_meta_keywords(row.get("keywords") or ""))

    filtered: list[str] = []
    stopwords_applied = 0
    for token in raw_tokens:
        cleaned = _clean_token(token)
        if not cleaned or len(cleaned) <= 1 or cleaned.isdigit() or cleaned in stopword_set:
            stopwords_applied += 1
            continue
        filtered.append(cleaned)

    counter = Counter(filtered)
    counter = Counter({keyword: count for keyword, count in counter.items() if count >= min_count})
    return counter, len(filtered), source_field, tokenizer, stopwords_applied


def _get_kiwi():
    global _kiwi_instance
    if _kiwi_instance is None:
        from kiwipiepy import Kiwi

        _kiwi_instance = Kiwi()
    return _kiwi_instance


def _tokenize_with_kiwi(text: str) -> list[str]:
    kiwi = _get_kiwi()
    tokens = []
    for token in kiwi.tokenize(text or ""):
        tag = getattr(token, "tag", "")
        if tag in {"NNG", "NNP"}:
            tokens.append(str(getattr(token, "form", "")))
    return tokens


def _split_meta_keywords(text: str) -> list[str]:
    return [part.strip() for part in str(text).split(",") if part.strip()]


def _clean_token(token: str) -> str:
    return str(token).strip().strip(".,!?()[]{}<>:;\"'“”‘’").lower()
