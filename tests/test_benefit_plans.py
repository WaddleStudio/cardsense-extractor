from extractor.benefit_plans import infer_plan_id


def test_infer_plan_id_matches_cube_title_keywords():
    assert infer_plan_id("CATHAY_CUBE", "ONLINE", title="CUBE 玩數位 指定通路 3%") == "CATHAY_CUBE_DIGITAL"
    assert infer_plan_id("CATHAY_CUBE", "OVERSEAS", title="CUBE 日本賞 海外消費 8%") == "CATHAY_CUBE_JAPAN"


def test_infer_plan_id_matches_richart_title_keywords():
    assert infer_plan_id("TAISHIN_RICHART", "ONLINE") == "TAISHIN_RICHART_DIGITAL"
    assert infer_plan_id("TAISHIN_RICHART", "DINING") == "TAISHIN_RICHART_DINING"


def test_infer_plan_id_matches_unicard_title_keywords():
    assert infer_plan_id("ESUN_UNICARD", "ONLINE") == "ESUN_UNICARD_FLEXIBLE"
    assert infer_plan_id("ESUN_UNICARD", "SHOPPING") == "ESUN_UNICARD_SIMPLE"


def test_infer_plan_id_prefers_travel_plan_for_online_travel_platform_subcategory():
    assert infer_plan_id(
        "CATHAY_CUBE",
        "ONLINE",
        title="CUBE Agoda 指定通路 3%",
        subcategory="TRAVEL_PLATFORM",
    ) == "CATHAY_CUBE_TRAVEL"
