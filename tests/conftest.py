"""Shared test fixtures for Step 2."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest


@pytest.fixture
def sample_bigkinds_xlsx(tmp_path) -> Path:
    """Create a sample BIGKinds XLSX in tmp_path."""
    data = [
        ["뉴스 식별자", "일자", "언론사", "제목", "본문", "키워드", "URL"],
        [
            "NK001",
            "20221029",
            "한국일보",
            "이태원 핼러윈 축제 앞두고 인파 몰려",
            "29일 저녁 이태원역 일대에 핼러윈 축제를 즐기려는 인파가 몰렸다.",
            "이태원,핼러윈",
            "https://example.com/1",
        ],
        [
            "NK002",
            "20221030",
            "조선일보",
            "이태원 압사 사고 발생",
            "30일 새벽 이태원 골목에서 대규모 압사 사고가 발생했다.",
            "이태원,압사,사고",
            "https://example.com/2",
        ],
        [
            "NK003",
            "20221030",
            "중앙일보",
            "이태원 참사 사망자 수 증가",
            "이태원 압사 사고로 인한 사망자가 계속 증가하고 있다.",
            "이태원,참사,사망",
            "https://example.com/3",
        ],
        [
            "NK004",
            "20221031",
            "동아일보",
            "정부 애도기간 선포",
            "정부가 이태원 참사와 관련해 국가 애도기간을 선포했다.",
            "정부,애도,이태원",
            "https://example.com/4",
        ],
        [
            "NK005",
            "20221101",
            "한겨레",
            "이태원 참사 원인 규명 촉구",
            "시민단체들이 이태원 참사 원인 규명을 촉구하고 나섰다.",
            "시민단체,원인규명",
            "https://example.com/5",
        ],
    ]
    xlsx_path = tmp_path / "sample_bigkinds.xlsx"
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    for row in data:
        worksheet.append(row)
    workbook.save(xlsx_path)
    return xlsx_path


@pytest.fixture
def sample_csv(tmp_path) -> Path:
    """Create a sample CSV in tmp_path."""
    csv_content = """date,title,body,publisher,keywords,url
2022-10-29,이태원 핼러윈 축제,29일 저녁 이태원 일대 인파,한국일보,"이태원,핼러윈",https://example.com/c1
2022-10-30,이태원 압사 사고,30일 새벽 이태원 압사 사고 발생,조선일보,"이태원,압사",https://example.com/c2
2022-10-30,사망자 수 증가,사망자 계속 증가 중,중앙일보,"이태원,사망",https://example.com/c3
2022-10-31,정부 애도기간,정부 국가 애도기간 선포,동아일보,"정부,애도",https://example.com/c4
2022-11-01,원인 규명 촉구,시민단체 원인 규명 촉구,한겨레,"시민단체,원인",https://example.com/c5
"""
    csv_path = tmp_path / "sample_articles.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    return csv_path
