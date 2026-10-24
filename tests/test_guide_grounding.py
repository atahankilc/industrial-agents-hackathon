from agent.guide.grounding import fallback_text, grounded_tokens, ungrounded

G = grounded_tokens([{"optimal_length_m": 37.42, "ref": "1.14", "name": "Generic room 03.08.033", "options": [1, 2]}])


def test_rounding_and_comma_decimals_are_grounded():
    assert ungrounded("About 37 m, exactly 37.4 m or 37,42 m.", G) == []


def test_invented_and_over_rounded_numbers_are_caught():
    assert ungrounded("It is about 40 m from room 9.99.", G) == ["40", "9.99"]


def test_refs_names_option_counts_and_list_markers():
    assert ungrounded("1. Go to 1.14\n2) then Generic room 03.08.033. I found 2 options.", G) == []


def test_3d_is_not_a_number():
    assert ungrounded("The 3D printer is in 1.14.", G) == []


def test_turkish_reply_with_comma_decimal():
    assert ungrounded("3D yazıcı 1.14 numaralı odada, yaklaşık 37,4 m.", G) == []


def test_fallback_uses_summaries_and_steps():
    text = fallback_text([{"status": "ok", "summary": "A → B: 37 m.", "result": {"steps": ["Start in A.", "Arrive at B."]}}])
    assert "A → B: 37 m." in text and "1. Start in A." in text
    assert fallback_text([])


def test_numeric_lists_do_not_ground_their_length():
    assert "3" not in grounded_tokens([{"c": [1.5, 8.5, 9.5]}])
    assert "2" in grounded_tokens([{"options": [{"a": 1}, {"a": 2}]}])
    assert ungrounded("3 rooms", grounded_tokens([{"c": [0.1, 0.2, 0.3], "floor": "Level 2", "n": 37}])) == ["3"]


def test_half_up_rounding():
    g = grounded_tokens([{"a": 2.5, "b": 36.5}])
    assert ungrounded("about 3 m and 37 m", g) == []


def test_thousands_separators():
    g = grounded_tokens([{"area": 1234.0}])
    assert ungrounded("1.234 m2 or 1,234 m2", g) == []


def test_marker_styles_and_times():
    assert ungrounded("- 1. go\n* 2. go\n**3.** go\nStep 4: go\nStep 5. go\nOpen 08:30", grounded_tokens(["x"])) == []


def test_trailing_zeros():
    assert ungrounded("37.40 m, 37.0 m, 5.", grounded_tokens([{"a": 37.4, "b": 37, "c": 5}])) == []


def test_fallback_skips_non_dicts():
    assert fallback_text(["x", None, {"summary": "S"}]) == "S"


def test_thousands_do_not_collapse_to_small_numbers():
    assert ungrounded("3,000 m", grounded_tokens([{"n": 3}])) == ["3.000"]
    assert ungrounded("3,000 m and 3.000 m", grounded_tokens([{"n": 3000.0}])) == []
    assert "3" not in grounded_tokens(["1,000"])


def test_long_leading_number_is_not_a_marker():
    assert ungrounded("42. far", grounded_tokens(["x"])) == []
    assert ungrounded("120: far", grounded_tokens(["x"])) == ["120"]
