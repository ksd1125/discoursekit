"""Representative article sampling tests."""

from discoursekit.analyze.sampling import sample_representative_articles
from tests.analysis_fixtures import make_analysis_db


def test_sample_random(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = sample_representative_articles(db_path, "test", strategy="random", n=3)

    assert result.sample_size == 3
    assert result.population_size == 8


def test_sample_size_exceeds_population(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = sample_representative_articles(db_path, "test", strategy="recent", n=20)

    assert result.sample_size == 8


def test_sample_keyword_match(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = sample_representative_articles(
        db_path,
        "test",
        strategy="keyword_match",
        n=10,
        keyword="policy",
    )

    assert result.sample_size == 2
    assert all("keyword_match" in article["reason"] for article in result.articles)


def test_sample_stratified(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = sample_representative_articles(db_path, "test", strategy="stratified", n=4)

    assert result.sample_size == 4
    assert len({article["publisher"] for article in result.articles}) == 4


def test_sample_reason_field(tmp_path):
    db_path = make_analysis_db(tmp_path)

    result = sample_representative_articles(db_path, "test", strategy="peak_period", n=2)

    assert result.articles
    assert all(article["reason"] for article in result.articles)
    assert "body_internal" not in result.articles[0]
