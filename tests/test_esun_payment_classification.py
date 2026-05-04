import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.esun_real import CardRecord, _build_unicard_hundred_store_promotions_for_cluster


def _unicard_card():
    return CardRecord(
        card_code="ESUN_UNICARD",
        card_name="Unicard",
        detail_url="https://example.com/unicard",
        apply_url=None,
        annual_fee_summary=None,
        application_requirements=[],
        sections=[],
    )


def test_unicard_merchant_cluster_excludes_mobile_payments():
    promotions = _build_unicard_hundred_store_promotions_for_cluster(
        card=_unicard_card(),
        eligibility_type="GENERAL",
        valid_from="2025-10-01",
        valid_until="2026-06-30",
        notes="catalog",
        title_suffix="supermarket",
        category="GROCERY",
        subcategory="SUPERMARKET",
        channel="ALL",
        condition_type="VENUE",
        merchant_labels=["PX Mart"],
        condition_overrides={"PX Mart": ("PXMART", "PX Mart")},
    )

    assert promotions
    for promotion in promotions:
        excluded_payment_values = {
            condition["value"]
            for condition in promotion["excludedConditions"]
            if condition["type"] == "PAYMENT"
        }
        assert "MOBILE_PAY" in excluded_payment_values


def test_unicard_mobile_pay_and_location_only_clusters_have_no_self_exclusion():
    mobile_promotions = _build_unicard_hundred_store_promotions_for_cluster(
        card=_unicard_card(),
        eligibility_type="GENERAL",
        valid_from="2025-10-01",
        valid_until="2026-06-30",
        notes="catalog",
        title_suffix="mobile pay",
        category="ONLINE",
        subcategory="GENERAL",
        channel="ONLINE",
        condition_type="PAYMENT",
        merchant_labels=["LINE Pay"],
        condition_overrides={"LINE Pay": ("LINE_PAY", "LINE Pay")},
    )
    location_promotions = _build_unicard_hundred_store_promotions_for_cluster(
        card=_unicard_card(),
        eligibility_type="GENERAL",
        valid_from="2025-10-01",
        valid_until="2026-06-30",
        notes="catalog",
        title_suffix="overseas",
        category="OVERSEAS",
        subcategory="GENERAL",
        channel="OFFLINE",
        condition_type="LOCATION_ONLY",
        merchant_labels=["Japan"],
        condition_overrides={"Japan": ("JP", "Japan")},
    )

    assert mobile_promotions
    assert location_promotions
    assert all(promotion["excludedConditions"] == [] for promotion in mobile_promotions)
    assert all(promotion["excludedConditions"] == [] for promotion in location_promotions)
