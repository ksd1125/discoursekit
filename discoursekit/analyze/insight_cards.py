"""Insight card payload builders for analysis dashboard results."""

from __future__ import annotations

from dataclasses import dataclass
from math import isinf
from typing import Any


FORBIDDEN_HEADLINE_PATTERNS = [
    "because",
    "proves",
    "proven",
    "caused by",
    "shows that",
    "think",
    "때문이다",
    "입증",
    "보여준다",
    "생각된다",
]


@dataclass(frozen=True)
class InsightCardPayload:
    """UI-ready insight card payload."""

    card_id: str
    headline: str
    subhead: str
    chart_data: dict | None
    callouts: list[str]
    evidence_items: list[dict]
    method_note: str
    caveat: str
    download_key: str | None = None


def build_insight_card_payload(
    card_id: str,
    analysis_result: Any,
    project_config: dict,
) -> InsightCardPayload:
    """Convert a backend analysis result into a dashboard card payload."""
    if card_id == "overview":
        payload = _overview_payload(analysis_result, project_config)
    elif card_id == "keywords":
        payload = _keywords_payload(analysis_result, project_config)
    elif card_id == "keyword_trends":
        payload = _keyword_trends_payload(analysis_result, project_config)
    elif card_id == "before_after":
        payload = _before_after_payload(analysis_result, project_config)
    elif card_id == "sampling":
        payload = _sampling_payload(analysis_result, project_config)
    elif card_id == "publishers":
        payload = _publishers_payload(analysis_result, project_config)
    elif card_id == "time_series":
        payload = _time_series_payload(analysis_result, project_config)
    elif card_id == "network":
        payload = _network_payload(analysis_result, project_config)
    else:
        raise ValueError(f"Unsupported insight card id: {card_id}")

    if not validate_headline(payload.headline):
        raise ValueError(f"Forbidden headline wording: {payload.headline}")
    return payload


def validate_headline(headline: str) -> bool:
    """Return False when a headline contains causal or overclaiming language."""
    lowered = headline.lower()
    return not any(pattern.lower() in lowered for pattern in FORBIDDEN_HEADLINE_PATTERNS)


def _overview_payload(result: Any, config: dict) -> InsightCardPayload:
    publisher_count = len(getattr(result, "publisher_counts", {}) or {})
    active = int(getattr(result, "active_articles", 0) or 0)
    total = int(getattr(result, "total_articles", 0) or 0)
    return InsightCardPayload(
        card_id="overview",
        headline=f"분석 가능한 기사 {active:,}건이 준비되었습니다",
        subhead=f"전체 {total:,}건 / 기간 {getattr(result, 'date_min', '')} ~ {getattr(result, 'date_max', '')} / 출처 {publisher_count}개",
        chart_data=None,
        callouts=[f"분석 가능 비율: {_pct(active, total):.1f}%", f"출처: {publisher_count:,}개"],
        evidence_items=[],
        method_note=_method_note(config, "SQLite COUNT/GROUP BY"),
        caveat=_caveat(config),
    )


def _time_series_payload(result: Any, config: dict) -> InsightCardPayload:
    periods = list(getattr(result, "periods", []) or [])
    counts = list(getattr(result, "total_counts", []) or [])
    if counts:
        max_idx = max(range(len(counts)), key=lambda idx: counts[idx])
        peak_period = periods[max_idx]
        peak_count = counts[max_idx]
        headline = f"{config.get('query', '검색어')} 기사는 {peak_period}에 가장 많이 모였습니다"
    else:
        peak_period = "-"
        peak_count = 0
        headline = "선택한 기간에 기사량이 분포되어 있습니다"
    return InsightCardPayload(
        card_id="time_series",
        headline=headline,
        subhead=f"최대 {peak_count:,}건 / {len(periods)}개 기간",
        chart_data={"periods": periods, "counts": counts},
        callouts=[f"최대 시기: {peak_period}", f"최대 건수: {peak_count:,}"],
        evidence_items=[],
        method_note=_method_note(config, "월별 분석 가능 기사 수"),
        caveat=_caveat(config),
    )


def _publishers_payload(result: Any, config: dict) -> InsightCardPayload:
    counts = list((getattr(result, "publisher_counts", {}) or {}).items())
    active = int(getattr(result, "active_articles", 0) or config.get("active_count", 0) or 0)
    top5 = counts[:5]
    top5_count = sum(count for _, count in top5)
    top5_share = _pct(top5_count, active)
    top_pub, top_count = counts[0] if counts else ("-", 0)
    return InsightCardPayload(
        card_id="publishers",
        headline=f"상위 {len(top5)}개 출처가 기사 {top5_share:.0f}%를 차지합니다",
        subhead=f"가장 많은 출처: {top_pub} ({top_count:,}건)",
        chart_data={"publishers": counts[:20]},
        callouts=[f"최다 출처: {top_pub}", f"상위 5개 비중: {top5_share:.0f}%"],
        evidence_items=[],
        method_note=_method_note(config, "출처별 기사 수 집계"),
        caveat=_caveat(config),
    )


def _keywords_payload(result: Any, config: dict) -> InsightCardPayload:
    top_keyword, top_count = result.keywords[0] if result.keywords else ("-", 0)
    stats = getattr(result, "frequency_stats", {}) or {}
    core_count = len(getattr(result, "core_keywords", []) or [])
    caveat = _caveat(config, keyword_card=True)
    return InsightCardPayload(
        card_id="keywords",
        headline=f"'{top_keyword}' 키워드가 가장 자주 등장했습니다 ({top_count:,}회)",
        subhead=f"상위 키워드 / 처리 방식: {result.tokenizer}",
        chart_data={"keywords": result.keywords},
        callouts=[
            f"최상위 키워드: {top_keyword}",
            f"고유 키워드: {result.unique_tokens:,}",
            f"핵심 구간: {core_count:,}개",
            f"평균 빈도: {stats.get('mean', 0)}",
        ],
        evidence_items=[],
        method_note=_method_note(config, f"키워드 빈도; tokenizer={result.tokenizer}; 최소 빈도 기준 적용"),
        caveat=caveat,
    )


def _keyword_trends_payload(result: Any, config: dict) -> InsightCardPayload:
    if result.new_entries:
        headline = f"'{result.new_entries[0][0]}' 키워드가 {result.cutoff_date} 이후 새로 상위권에 들어왔습니다"
    elif result.risers:
        headline = f"'{result.risers[0][0]}' 키워드 순위가 {result.cutoff_date} 이후 상승했습니다"
    else:
        headline = f"{result.cutoff_date} 전후 키워드 구성은 큰 변동이 적습니다"
    return InsightCardPayload(
        card_id="keyword_trends",
        headline=headline,
        subhead=f"기준일: {result.cutoff_date}",
        chart_data={"before": result.before_keywords, "after": result.after_keywords},
        callouts=_nonempty_callouts(
            [
                f"신규: {result.new_entries[0][0]}" if result.new_entries else "",
                f"상승: {result.risers[0][0]}" if result.risers else "",
                f"하락: {result.decliners[0][0]}" if result.decliners else "",
            ]
        ),
        evidence_items=[],
        method_note=_method_note(config, "기준일 전후 키워드 순위 비교"),
        caveat=_caveat(config),
    )


def _before_after_payload(result: Any, config: dict) -> InsightCardPayload:
    if isinf(result.ratio):
        headline = f"{result.cutoff_date} 이전 기사는 없고 이후 기사 {result.after_count:,}건이 있습니다"
    elif result.ratio >= 2.0:
        headline = f"{result.cutoff_date} 이후 기사량이 이전보다 {result.ratio:.1f}배 높습니다"
    elif result.ratio > 1.0:
        headline = f"{result.cutoff_date} 전후 기사량 차이가 있습니다"
    else:
        headline = f"{result.cutoff_date} 이후 기사량 증가는 뚜렷하지 않습니다"
    return InsightCardPayload(
        card_id="before_after",
        headline=headline,
        subhead=f"이전 {result.before_count:,}건 / 이후 {result.after_count:,}건",
        chart_data={"before": result.before_count, "after": result.after_count},
        callouts=[
            f"이전: {result.before_count:,}",
            f"이후: {result.after_count:,}",
            f"비율: {'inf' if isinf(result.ratio) else f'{result.ratio:.1f}x'}",
        ],
        evidence_items=[],
        method_note=_method_note(config, f"기준일 전후 건수 비교; 기준일={result.cutoff_date}"),
        caveat=_before_after_caveat(config),
    )


def _sampling_payload(result: Any, config: dict) -> InsightCardPayload:
    return InsightCardPayload(
        card_id="sampling",
        headline=f"'{result.strategy}' 전략으로 기사 {result.sample_size:,}건을 표본으로 뽑았습니다",
        subhead=f"모집단 {result.population_size:,}건 / 표본 {result.sample_size:,}건",
        chart_data=None,
        callouts=[f"표본: {result.sample_size:,}건", f"전략: {result.strategy}"],
        evidence_items=result.articles,
        method_note=_method_note(config, f"표본 추출 전략={result.strategy}"),
        caveat="이 표본은 정성 검토의 출발점이며 통계적 대표성을 보장하지 않습니다.",
    )


def _network_payload(result: Any, config: dict) -> InsightCardPayload:
    community_count = len(getattr(result, "communities", []) or [])
    top_central = list(getattr(result, "top_central", []) or [])
    top_nodes = ", ".join(node["keyword"] for node in top_central[:3]) if top_central else "없음"
    return InsightCardPayload(
        card_id="network",
        headline=f"키워드 의미망은 {result.num_nodes:,}개 노드와 {result.num_edges:,}개 연결로 구성됩니다",
        subhead=f"{community_count}개 의미 클러스터 / 중심 키워드 후보: {top_nodes}",
        chart_data=None,
        callouts=[
            f"의미망 밀도: {float(getattr(result, 'density', 0.0)):.3f}",
            f"클러스터: {community_count:,}개",
            f"노드: {int(getattr(result, 'num_nodes', 0)):,}개",
        ],
        evidence_items=[],
        method_note=_method_note(
            config,
            "기사 단위 키워드 동시출현 의미망; 중심성/커뮤니티 계산",
        ),
        caveat=(
            "동시출현 의미망은 함께 등장한 패턴을 보여주는 참고 구조입니다. "
            "키워드 사이의 인과관계나 의미 동일성을 보장하지 않습니다. "
            f"{_caveat(config)}"
        ).strip(),
    )


def _method_note(config: dict, computation_method: str) -> str:
    return (
        f"데이터: 분석 가능 기사 / 기간: {config.get('date_min', '')}~{config.get('date_max', '')} / "
        f"기사 {int(config.get('active_count', 0) or 0):,}건 / 계산 방법: {computation_method} / "
        f"자료 깊이: {_source_depth_label(config.get('source_depth', ''))}"
    )


def _caveat(config: dict, keyword_card: bool = False) -> str:
    caveats = []
    if config.get("source_depth") == "excerpt_only":
        caveats.append("NAVER API 자료는 제목과 요약문 기반이므로 기사 전문 의미 분석에는 한계가 있습니다.")
        if keyword_card:
            caveats.append("키워드 결과는 기사 전문의 실제 표현을 모두 반영하지 않을 수 있습니다.")
    if int(config.get("active_count", 0) or 0) < 50:
        caveats.append("분석 가능 기사가 50건 미만이므로 패턴 해석에는 주의가 필요합니다.")
    return " ".join(caveats)


def _before_after_caveat(config: dict) -> str:
    base = "전후 비교는 사건의 인과 효과를 입증하지 않습니다."
    extra = _caveat(config)
    return f"{base} {extra}".strip()


def _pct(numerator: int, denominator: int) -> float:
    return numerator / denominator * 100.0 if denominator else 0.0


def _nonempty_callouts(callouts: list[str]) -> list[str]:
    return [callout for callout in callouts if callout]


def _source_depth_label(value: str) -> str:
    if value == "excerpt_only":
        return "요약문만 제공"
    if value == "full_body":
        return "전문 포함"
    return value or "-"
