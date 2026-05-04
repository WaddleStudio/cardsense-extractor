import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.taishin_real import _append_richart_plan_conditions


def test_richart_daily_convenience_store_requires_taishin_pay():
    conditions = _append_richart_plan_conditions("TAISHIN_RICHART_DAILY", "CONVENIENCE_STORE", [])
    values_by_type = {}
    for condition in conditions:
        values_by_type.setdefault(condition["type"], set()).add(condition["value"])

    assert "SEVEN_ELEVEN" in values_by_type["VENUE"]
    assert "FAMILY_MART" in values_by_type["VENUE"]
    assert "TAISHIN_PAY" in values_by_type["PAYMENT"]


def test_richart_daily_convenience_store_excludes_other_mobile_payments():
    from extractor.taishin_real import _richart_payment_classification_exclusions

    exclusions = _richart_payment_classification_exclusions(
        plan_id="TAISHIN_RICHART_DAILY",
        subcategory="CONVENIENCE_STORE",
        conditions=[
            {"type": "VENUE", "value": "SEVEN_ELEVEN", "label": "7-ELEVEN"},
            {"type": "PAYMENT", "value": "TAISHIN_PAY", "label": "Taishin Pay"},
        ],
    )
    payment_values = {condition["value"] for condition in exclusions if condition["type"] == "PAYMENT"}

    assert "LINE_PAY" in payment_values
    assert "JKOPAY" in payment_values
    assert "OPEN_WALLET" in payment_values
    assert "FAMIPAY" in payment_values
    assert "TAISHIN_PAY" not in payment_values
