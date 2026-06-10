from app.ocr_service import _label_readability_score, _looks_upright, _skew_correction_worth_apply


def test_garbled_upside_down_not_upright():
    garbled = "suaiqold 4lleay asne) Keu pue"
    assert _label_readability_score(garbled) < 0.35
    assert _looks_upright(garbled, 89.7) is False


def test_real_label_text_is_upright():
    text = (
        "OLD TOM DISTILLERY Kentucky Straight Bourbon Whiskey 45% Alc./Vol. "
        "750 mL GOVERNMENT WARNING: (1) According to the Surgeon General"
    )
    assert _label_readability_score(text) >= 0.55
    assert _looks_upright(text, 200) is True


def test_skew_gate_rejects_three_degree_noise():
    assert _skew_correction_worth_apply(3, baseline=0.50, improved=0.54) is False


def test_skew_gate_accepts_meaningful_eight_degree_gain():
    assert _skew_correction_worth_apply(-9, baseline=0.45, improved=0.52) is True
