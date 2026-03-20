from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from extractor.html_utils import collapse_text


@dataclass(frozen=True)
class OfferBlock:
    section: str
    title: str
    body: str


@dataclass(frozen=True)
class SectionedPageConfig:
    section_headings: frozenset[str]
    active_sections: frozenset[str]
    subsection_skip: frozenset[str]
    title_prefixes: tuple[str, ...] = ()
    title_required_tokens: tuple[str, ...] = ("卡",)
    annual_fee_heading: str = "年費"
    annual_fee_signal_tokens: tuple[str, ...] = ()
    application_requirement_tokens: tuple[str, ...] = ()
    apply_link_pattern: str = r"申辦|申請"
    ignored_subsection_prefixes: tuple[str, ...] = ("活動期間", "本活動", "活動回饋", "1.", "2.", "3.")
    ignored_subsection_tokens: tuple[str, ...] = ("http", "https", "活動詳情", "立即登錄", "了解更多")
    ignored_offer_title_tokens: tuple[str, ...] = ()
    subsection_min_length: int = 2
    subsection_max_length: int = 40
    offer_body_min_length: int = 40
    card_title_scan_limit: int = 80
    card_title_max_length: int = 30


@dataclass(frozen=True)
class ExtractedPage:
    card_name: str | None
    apply_url: str | None
    annual_fee_summary: str | None
    application_requirements: List[str]
    sections: List[str]
    offer_blocks: List[OfferBlock]


def extract_sectioned_page(lines: List[str], links: List[dict[str, str]], config: SectionedPageConfig) -> ExtractedPage:
    return ExtractedPage(
        card_name=extract_card_title(lines, config),
        apply_url=extract_apply_url(links, config),
        annual_fee_summary=extract_annual_fee_summary(lines, config),
        application_requirements=extract_application_requirements(lines, config),
        sections=extract_sections(lines, config),
        offer_blocks=extract_offer_blocks(lines, config),
    )


def extract_card_title(lines: List[str], config: SectionedPageConfig) -> str | None:
    for line in lines[:config.card_title_scan_limit]:
        if config.title_prefixes and not any(line.startswith(prefix) for prefix in config.title_prefixes):
            continue
        if any(token not in line for token in config.title_required_tokens):
            continue
        if len(line) <= config.card_title_max_length:
            return line
    return None


def extract_apply_url(links: List[dict[str, str]], config: SectionedPageConfig) -> str | None:
    for link in links:
        if re.search(config.apply_link_pattern, link["text"]):
            return link["href"]
    return None


def extract_sections(lines: List[str], config: SectionedPageConfig) -> List[str]:
    return [line for line in lines if line in config.section_headings]


def extract_annual_fee_summary(lines: List[str], config: SectionedPageConfig) -> str | None:
    for index, line in enumerate(lines):
        if line == config.annual_fee_heading:
            summary_lines: List[str] = []
            for candidate in lines[index + 1:index + 8]:
                if candidate in config.section_headings:
                    break
                if summary_lines and any(token in candidate for token in config.application_requirement_tokens):
                    break
                if summary_lines and is_subsection_title(candidate, config):
                    break
                summary_lines.append(candidate)
            if summary_lines:
                return collapse_text(" ".join(summary_lines))
    for line in lines:
        if any(token in line for token in config.annual_fee_signal_tokens):
            return line
    return None


def extract_application_requirements(lines: List[str], config: SectionedPageConfig) -> List[str]:
    requirements: List[str] = []
    for line in lines:
        if any(token in line for token in config.application_requirement_tokens):
            requirements.append(line)
    return list(dict.fromkeys(requirements))[:6]


def extract_offer_blocks(lines: List[str], config: SectionedPageConfig) -> List[OfferBlock]:
    blocks: List[OfferBlock] = []
    current_section = ""
    current_title = ""
    current_body: List[str] = []

    def flush() -> None:
        nonlocal current_title, current_body
        if not current_title:
            return
        body = collapse_text(" ".join(current_body))
        if is_real_offer_block(current_title, body, config):
            blocks.append(OfferBlock(section=current_section, title=current_title, body=body))
        current_title = ""
        current_body = []

    for line in lines:
        if line in config.section_headings:
            flush()
            current_section = line
            continue

        if current_section not in config.active_sections:
            continue

        if is_subsection_title(line, config):
            flush()
            current_title = line
            continue

        if current_title:
            current_body.append(line)

    flush()
    return blocks


def is_subsection_title(line: str, config: SectionedPageConfig) -> bool:
    if line in config.subsection_skip:
        return False
    if len(line) < config.subsection_min_length or len(line) > config.subsection_max_length:
        return False
    if line.startswith("•"):
        return False
    if re.search(r"\d{4}/\d{1,2}/\d{1,2}", line):
        return False
    if any(line.startswith(prefix) for prefix in config.ignored_subsection_prefixes):
        return False
    if any(token in line for token in config.ignored_subsection_tokens):
        return False
    return True


def is_real_offer_block(title: str, body: str, config: SectionedPageConfig) -> bool:
    if len(body) < config.offer_body_min_length:
        return False
    if any(token in title for token in config.ignored_offer_title_tokens):
        return False
    has_value = bool(re.search(r"\d+(?:\.\d+)?%|[\d,]+元|[\d,]+P幣|[\d,]+點|折扣", body))
    has_period = bool(re.search(r"\d{4}/\d{1,2}/\d{1,2}\s*[~～-]\s*\d{4}/\d{1,2}/\d{1,2}", body))
    return has_value and has_period and title not in config.subsection_skip