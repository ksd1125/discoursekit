"""Topic-structure summaries built from semantic keyword networks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from discoursekit.analyze.network import compute_keyword_network


@dataclass(frozen=True)
class TopicStructureResult:
    """Discourse topic structure summary."""

    dominant_community: dict
    peripheral_keywords: list[str]
    bridge_keywords: list[str]
    concentration_index: float
    structural_summary: str
    num_nodes: int
    num_edges: int
    community_count: int


def compute_topic_structure(
    db_path: Path,
    project_id: str,
    top_n: int = 40,
) -> TopicStructureResult:
    """Compute a compact structural reading of the discourse network."""
    network = compute_keyword_network(db_path, project_id, top_n=top_n)
    dominant = (
        max(network.communities, key=lambda item: len(item["keywords"]))
        if network.communities
        else {"id": 0, "keywords": [], "label": "없음"}
    )

    if network.nodes:
        ordered_by_degree = sorted(network.nodes, key=lambda item: item["degree"])
        cutoff = max(1, len(ordered_by_degree) // 5)
        peripheral = [node["keyword"] for node in ordered_by_degree[:cutoff]]
    else:
        peripheral = []

    bridge = [
        node["keyword"]
        for node in sorted(network.nodes, key=lambda item: item["betweenness"], reverse=True)[:5]
    ]
    total_degree = sum(float(node["degree"]) for node in network.nodes)
    top5_degree = sum(
        float(node["degree"])
        for node in sorted(network.nodes, key=lambda item: item["degree"], reverse=True)[:5]
    )
    concentration = top5_degree / total_degree * 100 if total_degree else 0.0
    summary = _build_structure_summary(network, dominant, bridge, concentration)
    return TopicStructureResult(
        dominant_community=dominant,
        peripheral_keywords=peripheral,
        bridge_keywords=bridge,
        concentration_index=round(concentration, 1),
        structural_summary=summary,
        num_nodes=network.num_nodes,
        num_edges=network.num_edges,
        community_count=len(network.communities),
    )


def _build_structure_summary(network, dominant: dict, bridge: list[str], concentration: float) -> str:
    if network.num_nodes == 0:
        return "의미망을 구성할 만큼 충분한 키워드 연결이 아직 없습니다."

    parts = [
        f"총 {network.num_nodes}개 키워드와 {network.num_edges}개 연결로 구성된 의미망입니다."
    ]
    if network.communities:
        parts.append(f"{len(network.communities)}개의 의미 클러스터가 감지되었습니다.")
    if dominant.get("keywords"):
        top_terms = ", ".join(dominant["keywords"][:3])
        parts.append(
            f"가장 큰 클러스터는 {len(dominant['keywords'])}개 키워드로 구성되며 "
            f"{top_terms} 등이 포함됩니다."
        )
    if bridge:
        parts.append(f"{', '.join(bridge[:3])} 등은 클러스터 사이를 잇는 후보 키워드입니다.")
    parts.append(f"상위 5개 키워드가 전체 연결 중심성의 {concentration:.0f}%를 차지합니다.")
    return " ".join(parts)
