from extractor.page_extractors import SectionedPageConfig, extract_sectioned_page


PAGE_CONFIG = SectionedPageConfig(
    section_headings=frozenset({"卡片特色", "專屬優惠", "注意事項"}),
    active_sections=frozenset({"卡片特色", "專屬優惠"}),
    subsection_skip=frozenset({"注意事項", "活動詳情", "立即申辦"}),
    title_prefixes=("玉山",),
    annual_fee_signal_tokens=("首年免年費",),
    application_requirement_tokens=("年滿18歲", "財力證明"),
    ignored_offer_title_tokens=("立即申辦",),
)


def test_extract_sectioned_page_skips_instruction_titles_and_extracts_offer_blocks():
    lines = [
        "玉山測試卡",
        "年費",
        "首年免年費 次年年費3,000元",
        "年滿18歲可申辦",
        "卡片特色",
        "立即申辦",
        "活動期間：2026/1/1~2026/3/31",
        "專屬優惠",
        "海外消費最高3%回饋",
        "活動期間：2026/1/1~2026/3/31 海外消費最高3%回饋，上限500元。",
    ]
    links = [{"text": "立即申辦", "href": "https://example.com/apply"}]

    extracted = extract_sectioned_page(lines, links, PAGE_CONFIG)

    assert extracted.card_name == "玉山測試卡"
    assert extracted.apply_url == "https://example.com/apply"
    assert extracted.annual_fee_summary == "首年免年費 次年年費3,000元"
    assert extracted.application_requirements == ["年滿18歲可申辦"]
    assert extracted.sections == ["卡片特色", "專屬優惠"]
    assert [(block.section, block.title) for block in extracted.offer_blocks] == [("專屬優惠", "海外消費最高3%回饋")]