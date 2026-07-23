from app.services.scoring import final_score, haversine_km, hint_multiplier, score_from_distance


def test_haversine_known_distance():
    d = haversine_km(39.90, 116.40, 31.23, 121.47)  # 北京-上海
    assert 1050 < d < 1100


def test_perfect_score_within_threshold():
    assert score_from_distance(0.0) == 5000
    assert score_from_distance(0.2) == 5000


def test_score_decays_with_distance():
    same_city = score_from_distance(20)
    same_province = score_from_distance(150)
    neighbor = score_from_distance(500)
    far = score_from_distance(2000)
    assert same_city > 4500
    assert 3000 < same_province < 4000
    assert 1000 < neighbor < 2000
    assert far < 100
    assert same_city > same_province > neighbor > far


def test_hint_multiplier_uses_deepest_hint():
    assert hint_multiplier(0) == 1.0
    assert hint_multiplier(0b0001) == 1.0
    assert hint_multiplier(0b0010) == 0.8
    assert hint_multiplier(0b0110) == 0.6
    assert hint_multiplier(0b1111) == 0.4


def test_final_score_applies_multiplier():
    assert final_score(0.0, 0b1000) == 2000
    assert final_score(0.0, 0) == 5000
