"""Keyword trajectory and discourse-flow analysis."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from discoursekit.analyze.network import (
    NetworkResult,
    _extract_tokens,
    build_keyword_network_from_rows,
)
from discoursekit.core.db import get_connection


@dataclass(frozen=True)
class PeriodSnapshot:
    """Network and focus-keyword state for one period."""

    period: str
    phase: str
    article_count: int
    network: NetworkResult
    focus_count: int
    focus_role: str
    focus_neighbors: list[dict]
    dominant_cluster: str


@dataclass(frozen=True)
class KeywordTrajectoryResult:
    """Keyword movement across period networks."""

    focus_keyword: str
    period_type: str
    cutoff_date: str | None
    periods: list[str]
    snapshots: list[PeriodSnapshot]
    keyword_paths: list[dict]
    role_changes: list[dict]
    discourse_flows: list[dict]
    sankey_nodes: list[dict]
    sankey_links: list[dict]
    summary: str


def compute_keyword_trajectory(
    db_path: Path,
    project_id: str,
    focus_keyword: str,
    *,
    cutoff_date: str | None = None,
    period_type: str = "month",
    top_n: int = 30,
    min_count: int = 1,
    min_cooccurrence: int = 1,
) -> KeywordTrajectoryResult:
    """Track how a focus keyword and related terms move across period networks."""
    focus = _normalize_keyword(focus_keyword)
    rows = _active_article_rows(db_path, project_id)
    grouped = _group_rows_by_period(rows, period_type)
    snapshots: list[PeriodSnapshot] = []
    path_by_keyword: dict[str, list[dict]] = defaultdict(list)
    cutoff_period = _period_for_date(cutoff_date, period_type) if cutoff_date else None

    for period in sorted(grouped):
        period_rows = grouped[period]
        network = build_keyword_network_from_rows(
            period_rows,
            top_n=top_n,
            min_count=min_count,
            min_cooccurrence=min_cooccurrence,
        )
        token_counts = _period_token_counts(period_rows)
        node_by_keyword = {node["keyword"]: node for node in network.nodes}
        role_by_keyword = {
            keyword: _role_for_node(node, rank + 1)
            for rank, node in enumerate(
                sorted(network.nodes, key=lambda item: (-item["degree"], -item["count"], item["keyword"]))
            )
            for keyword in [node["keyword"]]
        }
        community_labels = _community_labels(network)
        focus_neighbors = _focus_neighbors(focus, network)
        focus_node = node_by_keyword.get(focus)
        focus_role = (
            role_by_keyword.get(focus)
            if focus_node
            else ("mentioned" if token_counts.get(focus, 0) else "absent")
        )
        dominant_cluster = _dominant_cluster_label(network)
        snapshots.append(
            PeriodSnapshot(
                period=period,
                phase=_phase_for_period(period, cutoff_period),
                article_count=len(period_rows),
                network=network,
                focus_count=int(token_counts.get(focus, 0)),
                focus_role=focus_role,
                focus_neighbors=focus_neighbors,
                dominant_cluster=dominant_cluster,
            )
        )

        for keyword, count in token_counts.items():
            if keyword not in node_by_keyword and count < min_count:
                continue
            node = node_by_keyword.get(keyword, {})
            community_id = int(node.get("community", -1)) if node else -1
            path_by_keyword[keyword].append(
                {
                    "period": period,
                    "phase": _phase_for_period(period, cutoff_period),
                    "keyword": keyword,
                    "count": int(count),
                    "degree": float(node.get("degree", 0.0)) if node else 0.0,
                    "betweenness": float(node.get("betweenness", 0.0)) if node else 0.0,
                    "community": community_id,
                    "community_label": community_labels.get(community_id, "미분류"),
                    "role": role_by_keyword.get(keyword, "mentioned"),
                }
            )

    keyword_paths = _summarize_keyword_paths(path_by_keyword)
    role_changes = _role_changes(keyword_paths)
    discourse_flows = _build_discourse_flows(snapshots)
    sankey_nodes, sankey_links = _build_sankey(discourse_flows)
    summary = _build_summary(focus, snapshots, role_changes, discourse_flows, cutoff_date)
    return KeywordTrajectoryResult(
        focus_keyword=focus,
        period_type=period_type,
        cutoff_date=cutoff_date,
        periods=sorted(grouped),
        snapshots=snapshots,
        keyword_paths=keyword_paths,
        role_changes=role_changes,
        discourse_flows=discourse_flows,
        sankey_nodes=sankey_nodes,
        sankey_links=sankey_links,
        summary=summary,
    )


def _active_article_rows(db_path: Path, project_id: str) -> list[dict]:
    conn = get_connection(db_path)
    try:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT date, title, body_excerpt, keywords
                FROM articles
                WHERE project_id = ? AND is_active = 1
                ORDER BY date, article_id
                """,
                (project_id,),
            ).fetchall()
        ]
    finally:
        conn.close()


def _group_rows_by_period(rows: list[dict], period_type: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        period = _period_for_date(str(row.get("date") or ""), period_type)
        if period:
            grouped[period].append(row)
    return dict(grouped)


def _period_for_date(value: str, period_type: str) -> str:
    try:
        parsed = date.fromisoformat(value[:10])
    except ValueError:
        return value[:7] if len(value) >= 7 else value
    if period_type == "week":
        iso_year, iso_week, _ = parsed.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    return f"{parsed.year:04d}-{parsed.month:02d}"


def _phase_for_period(period: str, cutoff_period: str | None) -> str:
    if not cutoff_period:
        return "all"
    return "before" if period < cutoff_period else "on_or_after"


def _period_token_counts(rows: list[dict]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter.update(_extract_tokens(row))
    return counter


def _focus_neighbors(focus: str, network: NetworkResult) -> list[dict]:
    neighbors = []
    node_lookup = {node["keyword"]: node for node in network.nodes}
    for edge in network.edges:
        neighbor = None
        if edge["source"] == focus:
            neighbor = edge["target"]
        elif edge["target"] == focus:
            neighbor = edge["source"]
        if neighbor:
            node = node_lookup.get(neighbor, {})
            neighbors.append(
                {
                    "keyword": neighbor,
                    "weight": int(edge["weight"]),
                    "degree": float(node.get("degree", 0.0)),
                    "community": int(node.get("community", -1)),
                }
            )
    return sorted(neighbors, key=lambda item: (-item["weight"], -item["degree"], item["keyword"]))


def _role_for_node(node: dict, rank: int) -> str:
    degree = float(node.get("degree", 0.0))
    betweenness = float(node.get("betweenness", 0.0))
    if rank <= 3 or degree >= 0.5:
        return "center"
    if betweenness > 0:
        return "bridge"
    if degree > 0:
        return "connected"
    return "peripheral"


def _community_labels(network: NetworkResult) -> dict[int, str]:
    labels = {-1: "미분류"}
    for community in network.communities:
        keywords = community.get("keywords", [])
        label = ", ".join(keywords[:3]) if keywords else str(community.get("label", "미분류"))
        labels[int(community.get("id", 0))] = label
    return labels


def _dominant_cluster_label(network: NetworkResult) -> str:
    if not network.communities:
        return "미분류"
    dominant = max(network.communities, key=lambda item: len(item.get("keywords", [])))
    keywords = dominant.get("keywords", [])
    return ", ".join(keywords[:3]) if keywords else str(dominant.get("label", "미분류"))


def _summarize_keyword_paths(path_by_keyword: dict[str, list[dict]]) -> list[dict]:
    paths = []
    for keyword, points in path_by_keyword.items():
        ordered = sorted(points, key=lambda item: item["period"])
        first = ordered[0]
        last = ordered[-1]
        peak = max(ordered, key=lambda item: (item["count"], item["degree"]))
        paths.append(
            {
                "keyword": keyword,
                "first_period": first["period"],
                "last_period": last["period"],
                "periods_active": len(ordered),
                "first_role": first["role"],
                "last_role": last["role"],
                "peak_period": peak["period"],
                "peak_count": peak["count"],
                "peak_degree": round(float(peak["degree"]), 4),
                "first_community": first["community_label"],
                "last_community": last["community_label"],
                "path": ordered,
            }
        )
    paths.sort(
        key=lambda item: (
            -item["periods_active"],
            -item["peak_count"],
            item["keyword"],
        )
    )
    return paths


def _role_changes(keyword_paths: list[dict]) -> list[dict]:
    changes = []
    for path in keyword_paths:
        if path["first_role"] == path["last_role"] and path["first_community"] == path["last_community"]:
            continue
        changes.append(
            {
                "keyword": path["keyword"],
                "first_period": path["first_period"],
                "last_period": path["last_period"],
                "from_role": path["first_role"],
                "to_role": path["last_role"],
                "from_cluster": path["first_community"],
                "to_cluster": path["last_community"],
                "peak_period": path["peak_period"],
                "peak_count": path["peak_count"],
            }
        )
    return changes[:30]


def _build_discourse_flows(snapshots: list[PeriodSnapshot]) -> list[dict]:
    flows = []
    for previous, current in zip(snapshots, snapshots[1:]):
        flows.append(
            {
                "source_period": previous.period,
                "target_period": current.period,
                "source_cluster": previous.dominant_cluster,
                "target_cluster": current.dominant_cluster,
                "weight": max(1, current.article_count),
            }
        )
    return flows


def _build_sankey(flows: list[dict]) -> tuple[list[dict], list[dict]]:
    node_index: dict[str, int] = {}
    nodes: list[dict] = []
    links: list[dict] = []
    for flow in flows:
        source_label = f"{flow['source_period']} | {flow['source_cluster']}"
        target_label = f"{flow['target_period']} | {flow['target_cluster']}"
        for label in (source_label, target_label):
            if label not in node_index:
                node_index[label] = len(nodes)
                nodes.append({"id": len(nodes), "label": label})
        links.append(
            {
                "source": node_index[source_label],
                "target": node_index[target_label],
                "value": int(flow["weight"]),
                "source_label": source_label,
                "target_label": target_label,
            }
        )
    return nodes, links


def _build_summary(
    focus: str,
    snapshots: list[PeriodSnapshot],
    role_changes: list[dict],
    flows: list[dict],
    cutoff_date: str | None,
) -> str:
    if not snapshots:
        return "분석 가능한 기간별 키워드 이동 데이터가 없습니다."
    focus_periods = [snapshot for snapshot in snapshots if snapshot.focus_count > 0]
    if focus_periods:
        first = focus_periods[0]
        last = focus_periods[-1]
        lead = (
            f"'{focus}'는 {first.period}에 {first.focus_role} 역할로 나타나고 "
            f"{last.period}에는 {last.focus_role} 역할로 관찰됩니다."
        )
    else:
        lead = f"'{focus}'는 선택한 자료에서 직접 추출되지 않았습니다."
    change_text = f" 역할/클러스터 변화 후보는 {len(role_changes)}개입니다."
    flow_text = ""
    if flows:
        first_flow = flows[0]
        last_flow = flows[-1]
        flow_text = (
            f" 지배적 담론군은 {first_flow['source_cluster']}에서 "
            f"{last_flow['target_cluster']} 방향으로 이어지는 흐름으로 요약됩니다."
        )
    cutoff_text = f" 기준일은 {cutoff_date}입니다." if cutoff_date else ""
    return f"{lead}{change_text}{flow_text}{cutoff_text}"


def _normalize_keyword(value: str) -> str:
    return value.strip().lower()
