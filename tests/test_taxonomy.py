"""Keyword taxonomy tests."""

from discoursekit.analyze.taxonomy import build_keyword_taxonomy


def test_query_keyword_is_excluded():
    result = build_keyword_taxonomy(
        [("명동", 100), ("돈카츠", 30), ("카페", 20)],
        query="명동",
    )

    assert "명동" in result.excluded_keywords
    assert "명동" not in [row["keyword"] for row in result.rows]


def test_entertainment_terms_group_together():
    result = build_keyword_taxonomy(
        [("제작", 20), ("공연", 18), ("배우", 15)],
        query="명동",
    )

    large_groups = {row["large"] for row in result.rows}
    assert "문화/엔터테인먼트" in large_groups


def test_category_totals_are_sorted():
    result = build_keyword_taxonomy(
        [("상권", 10), ("돈카츠", 30), ("정책", 5)],
        query="",
    )

    assert result.category_totals[0]["count"] == 30
    assert result.summary


# ── 상권 분류표 신규 테스트 ──


def test_menu_food_classification():
    """메뉴/상품 > 음식 분류 확인."""
    result = build_keyword_taxonomy(
        [("돈카츠", 50), ("라멘", 40), ("초밥", 30), ("파스타", 20)],
        query="명동",
    )

    for row in result.rows:
        assert row["large"] == "메뉴/상품"
        assert row["middle"] == "음식·식사"


def test_dessert_cafe_classification():
    """메뉴/상품 > 디저트·카페 분류 확인."""
    result = build_keyword_taxonomy(
        [("두쫀쿠", 80), ("마카롱", 40), ("커피", 35), ("크루아상", 20)],
        query="성수",
    )

    for row in result.rows:
        assert row["large"] == "메뉴/상품"
        assert row["middle"] == "디저트·카페"


def test_menu_attribute_classification():
    """메뉴/상품 > 메뉴 속성 분류 확인."""
    result = build_keyword_taxonomy(
        [("바삭", 15), ("쫀득", 12), ("시그니처", 10)],
        query="",
    )

    for row in result.rows:
        assert row["large"] == "메뉴/상품"
        assert row["middle"] == "메뉴 속성"


def test_shop_type_classification():
    """업소/브랜드 > 업종 분류 확인."""
    result = build_keyword_taxonomy(
        [("식당", 30), ("레스토랑", 20), ("미용실", 10)],
        query="",
    )

    for row in result.rows:
        assert row["large"] == "업소/브랜드"
        assert row["middle"] == "업종·형태"


def test_franchise_classification():
    """업소/브랜드 > 프랜차이즈 분류 확인."""
    result = build_keyword_taxonomy(
        [("스타벅스", 60), ("올리브영", 50), ("팝업", 25)],
        query="명동",
    )

    for row in result.rows:
        assert row["large"] == "업소/브랜드"
        assert row["middle"] == "프랜차이즈·브랜드"


def test_shop_status_classification():
    """업소/브랜드 > 운영·상태 분류 확인."""
    result = build_keyword_taxonomy(
        [("폐업", 15), ("오픈", 12), ("공실", 8)],
        query="",
    )

    for row in result.rows:
        assert row["large"] == "업소/브랜드"
        assert row["middle"] == "운영·상태"


def test_visit_review_classification():
    """방문/경험 > 후기 분류 확인."""
    result = build_keyword_taxonomy(
        [("후기", 40), ("추천", 35), ("재방문", 20), ("가성비", 15)],
        query="",
    )

    for row in result.rows:
        assert row["large"] == "방문/경험"
        assert row["middle"] == "방문·후기"


def test_service_environment_classification():
    """방문/경험 > 서비스·환경 분류 확인."""
    result = build_keyword_taxonomy(
        [("웨이팅", 30), ("친절", 25), ("분위기", 20)],
        query="",
    )

    for row in result.rows:
        assert row["large"] == "방문/경험"
        assert row["middle"] == "서비스·환경"


def test_tourism_classification():
    """방문/경험 > 관광 분류 확인."""
    result = build_keyword_taxonomy(
        [("관광객", 50), ("데이트", 30), ("핫플", 20)],
        query="",
    )

    for row in result.rows:
        assert row["large"] == "방문/경험"
        assert row["middle"] == "관광·여행"


def test_mixed_commercial_district_keywords():
    """상권 분석 시 다양한 대분류가 혼합되는 시나리오."""
    result = build_keyword_taxonomy(
        [
            ("돈카츠", 80),      # 메뉴/상품
            ("스타벅스", 60),     # 업소/브랜드
            ("후기", 40),         # 방문/경험
            ("상권", 30),         # 장소/상권
            ("매출", 20),         # 경제/소비
            ("정책", 10),         # 사회/정책
        ],
        query="명동",
    )

    large_groups = {row["large"] for row in result.rows}
    assert "메뉴/상품" in large_groups
    assert "업소/브랜드" in large_groups
    assert "방문/경험" in large_groups
    assert "장소/상권" in large_groups
    assert result.category_totals[0]["large"] == "메뉴/상품"


def test_alcohol_bar_classification():
    """메뉴/상품 > 주류·바 분류 확인."""
    result = build_keyword_taxonomy(
        [("칵테일", 20), ("하이볼", 15), ("포차", 10)],
        query="",
    )

    for row in result.rows:
        assert row["large"] == "메뉴/상품"
        assert row["middle"] == "주류·바"


def test_place_names_not_classified_as_person():
    """상권 지명이 인물로 분류되지 않는지 확인."""
    result = build_keyword_taxonomy(
        [("성수", 50), ("한남", 40), ("을지로", 30)],
        query="",
    )

    for row in result.rows:
        assert row["large"] != "인물/조직", f"{row['keyword']}이 인물로 분류됨"
