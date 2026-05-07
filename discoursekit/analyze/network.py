"""Semantic keyword network analysis."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from discoursekit.analyze.keywords import (
    DEFAULT_STOPWORDS,
    _clean_token,
    _split_meta_keywords,
    _tokenize_with_kiwi,
)
from discoursekit.core.db import get_connection


@dataclass(frozen=True)
class NetworkResult:
    """Keyword co-occurrence network analysis result."""

    nodes: list[dict]
    edges: list[dict]
    communities: list[dict]
    density: float
    num_nodes: int
    num_edges: int
    top_central: list[dict]


@dataclass(frozen=True)
class NetworkComparisonResult:
    """Before/after network structural comparison."""

    before: NetworkResult
    after: NetworkResult
    new_connections: list[dict]
    lost_connections: list[dict]
    centrality_shifts: list[dict]


def compute_keyword_network(
    db_path: Path,
    project_id: str,
    top_n: int = 40,
    min_count: int = 2,
    min_cooccurrence: int = 2,
    before: str | None = None,
    after_or_on: str | None = None,
) -> NetworkResult:
    """Build an article-level keyword co-occurrence network from active articles."""
    rows = _active_article_rows(db_path, project_id, before=before, after_or_on=after_or_on)
    return build_keyword_network_from_rows(
        rows,
        top_n=top_n,
        min_count=min_count,
        min_cooccurrence=min_cooccurrence,
    )


def build_keyword_network_from_rows(
    rows: list[dict],
    top_n: int = 40,
    min_count: int = 2,
    min_cooccurrence: int = 2,
) -> NetworkResult:
    """Build a keyword co-occurrence network from already fetched article rows."""
    keyword_counts = _count_tokens(rows)
    top_keywords = {
        keyword
        for keyword, count in keyword_counts.most_common(max(1, int(top_n)))
        if count >= max(1, int(min_count))
    }
    if not top_keywords:
        return _empty_network()

    pair_counts = _build_cooccurrence_matrix(rows, top_keywords)
    edges_raw = [
        (source, target, weight)
        for (source, target), weight in pair_counts.items()
        if weight >= max(1, int(min_cooccurrence))
    ]
    edges_raw.sort(key=lambda item: (-item[2], item[0], item[1]))

    connected_keywords = {keyword for edge in edges_raw for keyword in edge[:2]}
    node_names = [
        keyword
        for keyword, _ in keyword_counts.most_common(max(1, int(top_n)))
        if keyword in top_keywords and (keyword in connected_keywords or not edges_raw)
    ]
    if not node_names:
        return _empty_network()

    centrality = _compute_centrality(node_names, edges_raw)
    communities = _detect_communities(node_names, edges_raw)
    community_by_keyword = {
        keyword: community["id"]
        for community in communities
        for keyword in community.get("keywords", [])
    }

    nodes = [
        {
            "keyword": keyword,
            "count": int(keyword_counts[keyword]),
            "degree": round(float(centrality["degree"].get(keyword, 0.0)), 4),
            "betweenness": round(float(centrality["betweenness"].get(keyword, 0.0)), 4),
            "closeness": round(float(centrality["closeness"].get(keyword, 0.0)), 4),
            "community": int(community_by_keyword.get(keyword, 0)),
        }
        for keyword in node_names
    ]
    nodes.sort(key=lambda item: (-item["degree"], -item["count"], item["keyword"]))

    edges = [
        {"source": source, "target": target, "weight": int(weight)}
        for source, target, weight in edges_raw
        if source in node_names and target in node_names
    ]
    density = _density(len(node_names), len(edges))
    return NetworkResult(
        nodes=nodes,
        edges=edges,
        communities=communities,
        density=round(density, 4),
        num_nodes=len(nodes),
        num_edges=len(edges),
        top_central=nodes[:10],
    )


def compare_networks(
    db_path: Path,
    project_id: str,
    cutoff_date: str,
    top_n: int = 40,
    min_cooccurrence: int = 2,
) -> NetworkComparisonResult:
    """Compare keyword network structure before and after a cutoff date."""
    before_net = compute_keyword_network(
        db_path,
        project_id,
        top_n=top_n,
        min_cooccurrence=min_cooccurrence,
        before=cutoff_date,
    )
    after_net = compute_keyword_network(
        db_path,
        project_id,
        top_n=top_n,
        min_cooccurrence=min_cooccurrence,
        after_or_on=cutoff_date,
    )

    before_edges = {_edge_key(edge) for edge in before_net.edges}
    after_edges = {_edge_key(edge) for edge in after_net.edges}
    new_connections = [edge for edge in after_net.edges if _edge_key(edge) not in before_edges]
    lost_connections = [edge for edge in before_net.edges if _edge_key(edge) not in after_edges]

    before_rank = _centrality_rank(before_net)
    after_rank = _centrality_rank(after_net)
    centrality_shifts = []
    for keyword in set(before_rank) & set(after_rank):
        before_position = before_rank[keyword]
        after_position = after_rank[keyword]
        shift = before_position - after_position
        if abs(shift) >= 5:
            centrality_shifts.append(
                {
                    "keyword": keyword,
                    "before_rank": before_position + 1,
                    "after_rank": after_position + 1,
                    "shift": shift,
                }
            )
    centrality_shifts.sort(key=lambda item: abs(item["shift"]), reverse=True)
    return NetworkComparisonResult(
        before=before_net,
        after=after_net,
        new_connections=new_connections,
        lost_connections=lost_connections,
        centrality_shifts=centrality_shifts,
    )


def export_gexf(result: NetworkResult, output_path: Path) -> Path:
    """Export a keyword network as a Gephi-compatible GEXF file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(to_gexf_string(result), encoding="utf-8")
    return output_path


def to_gexf_string(result: NetworkResult) -> str:
    """Return a Gephi-compatible GEXF representation of a network result."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gexf xmlns="http://gexf.net/1.3" version="1.3">',
        '  <graph defaultedgetype="undirected" mode="static">',
        '    <attributes class="node">',
        '      <attribute id="count" title="count" type="integer" />',
        '      <attribute id="degree_centrality" title="degree_centrality" type="float" />',
        '      <attribute id="betweenness" title="betweenness" type="float" />',
        '      <attribute id="closeness" title="closeness" type="float" />',
        '      <attribute id="community" title="community" type="integer" />',
        "    </attributes>",
        "    <nodes>",
    ]
    for node in result.nodes:
        node_id = _xml_value(node["keyword"])
        lines.extend(
            [
                f'      <node id="{node_id}" label="{node_id}">',
                "        <attvalues>",
                f'          <attvalue for="count" value="{int(node["count"])}" />',
                f'          <attvalue for="degree_centrality" value="{float(node["degree"]):.4f}" />',
                f'          <attvalue for="betweenness" value="{float(node["betweenness"]):.4f}" />',
                f'          <attvalue for="closeness" value="{float(node["closeness"]):.4f}" />',
                f'          <attvalue for="community" value="{int(node["community"])}" />',
                "        </attvalues>",
                "      </node>",
            ]
        )
    lines.append("    </nodes>")
    lines.append("    <edges>")
    for idx, edge in enumerate(result.edges):
        source = _xml_value(edge["source"])
        target = _xml_value(edge["target"])
        weight = int(edge["weight"])
        lines.append(
            f'      <edge id="{idx}" source="{source}" target="{target}" weight="{weight}" />'
        )
    lines.extend(["    </edges>", "  </graph>", "</gexf>"])
    return "\n".join(lines)


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


def _count_tokens(rows: list[dict]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter.update(_extract_tokens(row))
    return counter


def _build_cooccurrence_matrix(rows: list[dict], top_keywords: set[str]) -> Counter[tuple[str, str]]:
    pair_counts: Counter[tuple[str, str]] = Counter()
    for row in rows:
        unique_tokens = sorted(set(token for token in _extract_tokens(row) if token in top_keywords))
        for idx, source in enumerate(unique_tokens):
            for target in unique_tokens[idx + 1 :]:
                pair_counts[(source, target)] += 1
    return pair_counts


def _extract_tokens(row: dict) -> list[str]:
    text = f"{row.get('title') or ''} {row.get('body_excerpt') or ''}"
    stopwords = set(DEFAULT_STOPWORDS)
    try:
        tokens = _tokenize_with_kiwi(text)
        if tokens:
            return _filter_tokens(tokens, stopwords)
    except Exception:
        pass
    return _filter_tokens(_split_meta_keywords(row.get("keywords") or ""), stopwords)


def _filter_tokens(tokens: list[str], stopwords: set[str]) -> list[str]:
    filtered = []
    for token in tokens:
        cleaned = _clean_token(token)
        if not cleaned or cleaned in stopwords or len(cleaned) <= 1 or cleaned.isdigit():
            continue
        filtered.append(cleaned)
    return filtered


def _compute_centrality(nodes: list[str], edges: list[tuple[str, str, int]]) -> dict[str, dict[str, float]]:
    try:
        import networkx as nx

        graph = nx.Graph()
        graph.add_nodes_from(nodes)
        graph.add_weighted_edges_from(edges)
        return {
            "degree": nx.degree_centrality(graph),
            "betweenness": nx.betweenness_centrality(graph, weight="weight"),
            "closeness": nx.closeness_centrality(graph),
        }
    except ImportError:
        return _fallback_centrality(nodes, edges)


def _fallback_centrality(
    nodes: list[str],
    edges: list[tuple[str, str, int]],
) -> dict[str, dict[str, float]]:
    adjacency: dict[str, set[str]] = {node: set() for node in nodes}
    for source, target, _ in edges:
        if source in adjacency and target in adjacency:
            adjacency[source].add(target)
            adjacency[target].add(source)
    denominator = max(1, len(nodes) - 1)
    degree = {node: len(neighbors) / denominator for node, neighbors in adjacency.items()}
    closeness = {
        node: _fallback_closeness(node, adjacency)
        for node in nodes
    }
    return {
        "degree": degree,
        "betweenness": {node: 0.0 for node in nodes},
        "closeness": closeness,
    }


def _fallback_closeness(node: str, adjacency: dict[str, set[str]]) -> float:
    distances = _shortest_distances(node, adjacency)
    reachable = [distance for other, distance in distances.items() if other != node and distance > 0]
    if not reachable:
        return 0.0
    return len(reachable) / sum(reachable)


def _shortest_distances(source: str, adjacency: dict[str, set[str]]) -> dict[str, int]:
    distances = {source: 0}
    queue = [source]
    for node in queue:
        for neighbor in adjacency.get(node, set()):
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                queue.append(neighbor)
    return distances


def _detect_communities(nodes: list[str], edges: list[tuple[str, str, int]]) -> list[dict]:
    try:
        import networkx as nx
        from networkx.algorithms.community import greedy_modularity_communities

        graph = nx.Graph()
        graph.add_nodes_from(nodes)
        graph.add_weighted_edges_from(edges)
        communities = list(greedy_modularity_communities(graph, weight="weight"))
        return [
            {"id": idx, "keywords": sorted(community), "label": f"의미 클러스터 {idx + 1}"}
            for idx, community in enumerate(communities)
            if community
        ]
    except ImportError:
        return _fallback_communities(nodes, edges)


def _fallback_communities(nodes: list[str], edges: list[tuple[str, str, int]]) -> list[dict]:
    parent = {node: node for node in nodes}

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(source: str, target: str) -> None:
        root_source = find(source)
        root_target = find(target)
        if root_source != root_target:
            parent[root_source] = root_target

    for source, target, _ in edges:
        if source in parent and target in parent:
            union(source, target)

    groups: dict[str, list[str]] = {}
    for node in nodes:
        groups.setdefault(find(node), []).append(node)
    ordered_groups = sorted(groups.values(), key=lambda group: (-len(group), sorted(group)[0]))
    return [
        {"id": idx, "keywords": sorted(group), "label": f"의미 클러스터 {idx + 1}"}
        for idx, group in enumerate(ordered_groups)
        if group
    ]


def _density(num_nodes: int, num_edges: int) -> float:
    if num_nodes <= 1:
        return 0.0
    possible_edges = num_nodes * (num_nodes - 1) / 2
    return num_edges / possible_edges


def _centrality_rank(network: NetworkResult) -> dict[str, int]:
    ordered = sorted(network.nodes, key=lambda item: (-item["degree"], -item["count"], item["keyword"]))
    return {node["keyword"]: idx for idx, node in enumerate(ordered)}


def _edge_key(edge: dict) -> tuple[str, str]:
    return tuple(sorted((str(edge["source"]), str(edge["target"]))))


def _xml_value(value: object) -> str:
    return escape(str(value), {'"': "&quot;"})


def _empty_network() -> NetworkResult:
    return NetworkResult(
        nodes=[],
        edges=[],
        communities=[],
        density=0.0,
        num_nodes=0,
        num_edges=0,
        top_central=[],
    )
