"""Rule-based keyword taxonomy for dashboard-level topic grouping."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class KeywordTaxonomyResult:
    """Hierarchical keyword grouping result."""

    rows: list[dict]
    category_totals: list[dict]
    excluded_keywords: list[str]
    uncategorized: list[dict]
    summary: str


TAXONOMY_RULES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    # ── 메뉴/상품 (상권 분석 핵심) ──
    (
        "메뉴/상품",
        "음식·식사",
        "한식/일식/중식/양식",
        (
            "돈카츠",
            "라멘",
            "초밥",
            "우동",
            "파스타",
            "피자",
            "햄버거",
            "스테이크",
            "삼겹살",
            "갈비",
            "냉면",
            "국밥",
            "칼국수",
            "떡볶이",
            "비빔밥",
            "치킨",
            "곱창",
            "보쌈",
            "짜장",
            "짬뽕",
            "덮밥",
            "김밥",
            "분식",
            "족발",
            "찜닭",
        ),
    ),
    (
        "메뉴/상품",
        "디저트·카페",
        "쿠키/케이크/빵/음료",
        (
            "쿠키",
            "두쫀쿠",
            "마카롱",
            "케이크",
            "크로플",
            "크루아상",
            "붕어빵",
            "빵",
            "베이커리",
            "아이스크림",
            "젤라또",
            "와플",
            "타르트",
            "디저트",
            "커피",
            "카페",
            "라떼",
            "에스프레소",
            "스무디",
            "밀크티",
            "버블티",
        ),
    ),
    (
        "메뉴/상품",
        "메뉴 속성",
        "식감/형태/조리법",
        (
            "쫀득",
            "바삭",
            "두툼",
            "촉촉",
            "매콤",
            "달콤",
            "고소",
            "담백",
            "비주얼",
            "토핑",
            "수제",
            "시그니처",
            "한정",
            "신메뉴",
            "세트",
            "메뉴",
        ),
    ),
    (
        "메뉴/상품",
        "주류·바",
        "술/안주/바",
        (
            "맥주",
            "와인",
            "칵테일",
            "소주",
            "막걸리",
            "하이볼",
            "위스키",
            "바",
            "펍",
            "안주",
            "포차",
        ),
    ),
    # ── 업소/브랜드 ──
    (
        "업소/브랜드",
        "업종·형태",
        "식당/카페/숍",
        (
            "식당",
            "음식점",
            "레스토랑",
            "카페",
            "베이커리",
            "편의점",
            "마트",
            "약국",
            "미용실",
            "네일",
            "헬스",
            "노래방",
            "pc방",
        ),
    ),
    (
        "업소/브랜드",
        "프랜차이즈·브랜드",
        "체인/브랜드명",
        (
            "스타벅스",
            "올리브영",
            "다이소",
            "이디야",
            "투썸",
            "메가커피",
            "맘스터치",
            "버거킹",
            "맥도날드",
            "프랜차이즈",
            "체인",
            "브랜드",
            "편집숍",
            "팝업",
            "플래그십",
        ),
    ),
    (
        "업소/브랜드",
        "운영·상태",
        "개업/폐업/변화",
        (
            "오픈",
            "개업",
            "폐업",
            "이전",
            "리뉴얼",
            "인테리어",
            "창업",
            "입점",
            "퇴점",
            "공실",
            "임대",
        ),
    ),
    # ── 방문/경험 ──
    (
        "방문/경험",
        "방문·후기",
        "후기/추천/평가",
        (
            "후기",
            "리뷰",
            "추천",
            "솔직",
            "재방문",
            "단골",
            "평점",
            "별점",
            "맛있",
            "맛없",
            "가성비",
            "가심비",
            "인생",
        ),
    ),
    (
        "방문/경험",
        "서비스·환경",
        "웨이팅/친절/분위기",
        (
            "웨이팅",
            "대기",
            "예약",
            "친절",
            "불친절",
            "서비스",
            "분위기",
            "인테리어",
            "뷰",
            "청결",
            "주차",
            "접근성",
            "위생",
        ),
    ),
    (
        "방문/경험",
        "관광·여행",
        "관광/데이트/코스",
        (
            "관광",
            "관광객",
            "외국인",
            "여행",
            "데이트",
            "코스",
            "산책",
            "나들이",
            "핫플",
            "핫플레이스",
            "포토",
            "인스타",
            "sns",
        ),
    ),
    # ── 장소/상권 ──
    (
        "장소/상권",
        "지역·공간",
        "거리/장소",
        (
            "거리",
            "골목",
            "광장",
            "상가",
            "가게",
            "공간",
            "지하상가",
            "백화점",
            "쇼핑몰",
            "아케이드",
            "지하철",
            "역세권",
        ),
    ),
    (
        "장소/상권",
        "상권·유동인구",
        "상권/유동/임대",
        (
            "상권",
            "유동인구",
            "통행량",
            "쇼핑",
            "호텔",
            "숙소",
            "게스트하우스",
            "특구",
            "시장",
            "야시장",
            "노점",
            "노포",
        ),
    ),
    # ── 경제/소비 ──
    (
        "경제/소비",
        "매출·가격",
        "경제 지표",
        (
            "매출",
            "소비",
            "판매",
            "투자",
            "임대료",
            "가격",
            "수익",
            "회복",
            "경제",
            "기업",
            "권리금",
            "월세",
        ),
    ),
    # ── 문화/엔터테인먼트 ──
    (
        "문화/엔터테인먼트",
        "영화·드라마·방송",
        "제작/출연/인물",
        (
            "영화",
            "드라마",
            "방송",
            "배우",
            "감독",
            "제작",
            "출연",
            "촬영",
            "작품",
            "콘텐츠",
            "시리즈",
        ),
    ),
    (
        "문화/엔터테인먼트",
        "행사·홍보",
        "발표/공연/이벤트",
        (
            "공연",
            "콘서트",
            "축제",
            "무대",
            "전시",
            "행사",
            "페스티벌",
            "마켓",
            "플리마켓",
        ),
    ),
    # ── 사회/정책 ──
    (
        "사회/정책",
        "정책·행정",
        "정부/지자체",
        (
            "정책",
            "정부",
            "서울시",
            "구청",
            "행정",
            "지원",
            "대책",
            "규제",
            "계획",
            "사업",
            "조례",
        ),
    ),
    (
        "사회/정책",
        "안전·갈등",
        "위험/사건",
        (
            "안전",
            "사고",
            "참사",
            "위험",
            "경찰",
            "책임",
            "갈등",
            "논란",
            "수사",
            "피해",
            "추모",
            "소음",
            "민원",
        ),
    ),
    # ── 공동체/생활 ──
    (
        "공동체/생활",
        "주민·커뮤니티",
        "사람/일상",
        (
            "주민",
            "시민",
            "청년",
            "커뮤니티",
            "모금",
            "생활",
            "가족",
            "사람",
            "마을",
            "동네",
            "이웃",
        ),
    ),
)


def build_keyword_taxonomy(
    keywords: list[tuple[str, int]],
    *,
    query: str = "",
    excluded: list[str] | None = None,
    max_terms: int = 80,
) -> KeywordTaxonomyResult:
    """Group keywords into broad/mid/small topic categories."""
    excluded_set = _excluded_terms(query, excluded or [])
    rows = []
    uncategorized = []
    for keyword, count in keywords[:max_terms]:
        cleaned = str(keyword).strip().lower()
        if cleaned in excluded_set:
            continue
        category = _classify(cleaned)
        row = {
            "keyword": keyword,
            "count": int(count),
            "large": category[0],
            "middle": category[1],
            "small": category[2],
        }
        rows.append(row)
        if category[0] == "기타":
            uncategorized.append(row)

    totals = defaultdict(int)
    for row in rows:
        totals[(row["large"], row["middle"])] += row["count"]
    category_totals = [
        {"large": large, "middle": middle, "count": count}
        for (large, middle), count in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    ]
    summary = _build_summary(category_totals, excluded_set)
    return KeywordTaxonomyResult(
        rows=rows,
        category_totals=category_totals,
        excluded_keywords=sorted(excluded_set),
        uncategorized=uncategorized,
        summary=summary,
    )


def _classify(keyword: str) -> tuple[str, str, str]:
    for large, middle, small, terms in TAXONOMY_RULES:
        if any(term.lower() in keyword for term in terms):
            return large, middle, small
    if _looks_like_korean_person(keyword):
        return "인물/조직", "인물명 후보", "고유명사"
    return "기타", "미분류", "검토 필요"


def _excluded_terms(query: str, extra: list[str]) -> set[str]:
    terms = set()
    for value in [query, *extra]:
        for term in re.split(r"[\s,;/|]+", str(value or "")):
            cleaned = term.strip().lower()
            if cleaned:
                terms.add(cleaned)
    return terms


_KNOWN_PLACE_NAMES: set[str] = {
    "서울", "부산", "인천", "대구", "대전", "광주", "울산", "세종",
    "명동", "이태원", "성수", "홍대", "강남", "신촌", "종로",
    "한남", "연남", "을지로", "익선", "경리단", "해방촌", "삼청",
    "중구", "용산", "마포", "강남", "송파", "성동", "종로",
    "거리", "골목", "상권", "관광", "안전", "정책", "경제", "시장",
    "맛집", "카페", "디저트", "브랜드", "메뉴", "후기", "리뷰",
    "서비스", "분위기", "웨이팅", "가격", "매출", "소비",
    "행사", "축제", "공연", "전시", "사업", "지원",
}


def _looks_like_korean_person(keyword: str) -> bool:
    return bool(re.fullmatch(r"[가-힣]{2,4}", keyword)) and keyword not in _KNOWN_PLACE_NAMES


def _build_summary(category_totals: list[dict], excluded_set: set[str]) -> str:
    if not category_totals:
        return "분류할 키워드가 충분하지 않습니다."
    top = category_totals[0]
    excluded_text = f" 검색 기준어({', '.join(sorted(excluded_set))})는 제외했습니다." if excluded_set else ""
    return (
        f"가장 큰 묶음은 {top['large']} > {top['middle']}입니다 "
        f"({top['count']:,}회).{excluded_text}"
    )
