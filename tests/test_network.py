"""Network analysis tests."""

from discoursekit.analyze.network import compare_networks, compute_keyword_network, export_gexf, to_gexf_string
from tests.analysis_fixtures import make_analysis_db


def test_basic_network(tmp_path):
    db_path = make_analysis_db(tmp_path)
    result = compute_keyword_network(db_path, "test", top_n=20, min_cooccurrence=1)

    assert result.num_nodes > 0
    assert result.num_edges >= 0
    assert isinstance(result.density, float)


def test_nodes_have_centrality(tmp_path):
    db_path = make_analysis_db(tmp_path)
    result = compute_keyword_network(db_path, "test", top_n=20, min_cooccurrence=1)

    if result.nodes:
        node = result.nodes[0]
        assert "keyword" in node
        assert "degree" in node
        assert "betweenness" in node
        assert "community" in node


def test_communities_detected(tmp_path):
    db_path = make_analysis_db(tmp_path)
    result = compute_keyword_network(db_path, "test", top_n=20, min_cooccurrence=1)

    assert isinstance(result.communities, list)
    for community in result.communities:
        assert "keywords" in community
        assert len(community["keywords"]) > 0


def test_edges_are_weighted(tmp_path):
    db_path = make_analysis_db(tmp_path)
    result = compute_keyword_network(db_path, "test", top_n=20, min_cooccurrence=1)

    for edge in result.edges:
        assert "source" in edge
        assert "target" in edge
        assert "weight" in edge
        assert edge["weight"] >= 1


def test_min_cooccurrence_filter(tmp_path):
    db_path = make_analysis_db(tmp_path)
    result_low = compute_keyword_network(db_path, "test", top_n=20, min_cooccurrence=1)
    result_high = compute_keyword_network(db_path, "test", top_n=20, min_cooccurrence=3)

    assert result_high.num_edges <= result_low.num_edges


def test_compare_networks(tmp_path):
    db_path = make_analysis_db(tmp_path)
    comparison = compare_networks(
        db_path,
        "test",
        cutoff_date="2022-11-01",
        top_n=20,
        min_cooccurrence=1,
    )

    assert comparison.before.num_nodes >= 0
    assert comparison.after.num_nodes >= 0
    assert isinstance(comparison.new_connections, list)
    assert isinstance(comparison.lost_connections, list)
    assert isinstance(comparison.centrality_shifts, list)


def test_empty_project(tmp_path):
    db_path = make_analysis_db(tmp_path)
    result = compute_keyword_network(db_path, "nonexistent", top_n=20)

    assert result.num_nodes == 0
    assert result.num_edges == 0


def test_export_gexf(tmp_path):
    db_path = make_analysis_db(tmp_path)
    result = compute_keyword_network(db_path, "test", top_n=20, min_cooccurrence=1)

    output_path = export_gexf(result, tmp_path / "network.gexf")
    text = output_path.read_text(encoding="utf-8")

    assert output_path.exists()
    assert "<gexf" in text
    assert "<nodes>" in text
    assert "<edges>" in text
    assert "degree_centrality" in text


def test_to_gexf_string_escapes_xml():
    # Use a minimal object to exercise XML escaping without depending on fixture content.
    network_result = type(
        "NetworkResult",
        (),
        {
            "nodes": [
                {
                    "keyword": 'a&"b',
                    "count": 1,
                    "degree": 0.0,
                    "betweenness": 0.0,
                    "closeness": 0.0,
                    "community": 0,
                }
            ],
            "edges": [],
        },
    )()

    text = to_gexf_string(network_result)

    assert "a&amp;&quot;b" in text
