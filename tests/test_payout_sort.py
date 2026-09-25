"""Sort order + Gemini half-Kelly. No network."""
from app.main import app
from app.strategy.kelly import gemini_nash_payoff, kelly_from_payout_odds
from app.strategy.scanner import enrich_market, sort_scan_rows


def test_import_app():
    assert app.title


def test_gemini_half_kelly_formula():
    # p=0.6, b=5 → f* = (0.6*5 - 0.4)/5 = 0.52; half = 0.26; $1000 → $260
    r = kelly_from_payout_odds(0.6, 5.0, 1000.0, 0.5)
    assert abs(r.kelly_f - 0.52) < 1e-9
    assert abs(r.fractional - 0.26) < 1e-9
    assert abs(r.allocation - 260.0) < 1e-6
    assert abs(gemini_nash_payoff(0.6, 5.0) - 2.6) < 1e-9
    neg = kelly_from_payout_odds(0.1, 2.0, 1000.0, 0.5)
    assert neg.allocation == 0.0


def test_sort_payout_before_score():
    rows = [
        {
            "best_payout_multiple": 3.0,
            "score": 100,
            "nash_payoff_gemini": 5,
            "kelly": {"expected_value_per_contract": 1},
            "gemini_kelly": {"allocation": 50},
        },
        {
            "best_payout_multiple": 13.0,
            "score": 1,
            "nash_payoff_gemini": 0.1,
            "kelly": {"expected_value_per_contract": 0},
            "gemini_kelly": {"allocation": 0},
        },
    ]
    sort_scan_rows(rows, "payout")
    assert [r["best_payout_multiple"] for r in rows] == [13.0, 3.0]


def test_enrich_explainer_and_order():
    cheap = {
        "ticker": "KXTEST-CHEAP",
        "title": "Will the cheap side hit?",
        "yes_sub_title": "cheap side hits",
        "no_sub_title": "cheap side misses",
        "rules_primary": "Resolves YES if it hits.",
        "yes_ask_dollars": 0.08,
        "no_ask_dollars": 0.93,
        "yes_bid_dollars": 0.07,
        "volume": 500,
        "open_interest": 500,
        "status": "open",
    }
    pricey = {
        "ticker": "KXTEST-PRICEY",
        "title": "Closer to even",
        "yes_sub_title": "even side",
        "no_sub_title": "other side",
        "yes_ask_dollars": 0.40,
        "no_ask_dollars": 0.62,
        "volume": 500,
        "open_interest": 500,
        "status": "open",
    }
    assert enrich_market({"ticker": "KXCROSSCATEGORY-1", "yes_ask_dollars": 0.1, "no_ask_dollars": 0.9}) is None
    rows = [enrich_market(pricey), enrich_market(cheap)]
    assert all(rows)
    sort_scan_rows(rows, "payout")
    assert rows[0]["ticker"] == "KXTEST-CHEAP"
    assert rows[0]["best_payout_multiple"] >= rows[1]["best_payout_multiple"]
    assert rows[0]["best_side"] == "yes"
    assert rows[0]["payout_odds"] == rows[0]["best_payout_multiple"] or abs(
        rows[0]["payout_odds"] - rows[0]["yes_payout_multiple"]
    ) < 0.02
    ex = rows[0]["explainer"]
    for key in (
        "win_if",
        "lose_if",
        "price_plain",
        "payout_plain",
        "why_odds",
        "edge_plain",
        "size_plain",
        "risk_plain",
    ):
        assert ex[key]
    assert "guaranteed" in ex["risk_plain"].lower() or "not a likely" in ex["risk_plain"].lower()
    assert "100%" not in ex["price_plain"]
    assert rows[0]["signal"] in {"GO", "NO-GO"}
    assert "allocation" in rows[0]["gemini_kelly"]
    assert rows[0]["model_p_source"] == "market_shrink"
    assert rows[0]["prob_source"] == "market_shrink"
    assert rows[0]["sports_game"] is False
    assert rows[0]["espn"] is None
    multiples = [r["best_payout_multiple"] for r in rows]
    assert multiples == sorted(multiples, reverse=True)
