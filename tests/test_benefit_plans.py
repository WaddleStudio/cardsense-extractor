from extractor.benefit_plans import infer_plan_id


def test_infer_plan_id_matches_cube_title_keywords():
    assert infer_plan_id("CATHAY_CUBE", "ONLINE", title="CUBE 玩數位 指定通路 3%") == "CATHAY_CUBE_DIGITAL"
    assert infer_plan_id("CATHAY_CUBE", "OVERSEAS", title="CUBE 日本賞 海外消費 8%") == "CATHAY_CUBE_JAPAN"


def test_infer_plan_id_matches_richart_title_keywords():
    assert infer_plan_id("TAISHIN_RICHART", "ONLINE", title="Richart Pay著刷 LINE Pay 最高 3.8%") == "TAISHIN_RICHART_PAY"
    assert infer_plan_id("TAISHIN_RICHART", "ENTERTAINMENT", title="Richart 數趣刷 指定影音 4.8%") == "TAISHIN_RICHART_DIGITAL"


def test_infer_plan_id_matches_unicard_title_keywords():
    assert infer_plan_id("ESUN_UNICARD", "ONLINE", title="Unicard 任意選 LINE Pay 3.5%") == "ESUN_UNICARD_FLEXIBLE"
    assert infer_plan_id("ESUN_UNICARD", "SHOPPING", title="Unicard UP選 百貨 4.5%") == "ESUN_UNICARD_UP"
