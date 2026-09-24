from __future__ import annotations

from app.simulate import propagate
from app.impact import compute_impact


def _toy_graph() -> tuple[dict[str, str], dict[str, list[tuple[str, float, float]]]]:
    names = {"A": "Hub A", "B": "Spoke B", "C": "Spoke C", "D": "Far D"}
    adj = {
        "A": [("B", 0.8, 0.7), ("C", 0.4, 0.3)],
        "B": [("A", 0.8, 0.9), ("D", 0.9, 0.6)],
        "C": [("A", 0.4, 0.9)],
        "D": [("B", 0.9, 0.7)],
    }
    return names, adj


def test_waves_are_ordered_and_decay() -> None:
    names, adj = _toy_graph()
    result = propagate("A", names, adj, origin_risk=0.7, decay=0.6, max_hops=3)
    assert result.waves[0][0].node_id == "A"
    assert result.waves[0][0].arrival_step == 0
    steps = [w[0].arrival_step for w in result.waves]
    assert steps == sorted(steps)
    origin_p = result.waves[0][0].probability_increase
    later = [n.probability_increase for wave in result.waves[1:] for n in wave]
    assert later, "cascade should reach neighbors"
    assert max(later) < origin_p
    ids_by_step = {n.node_id: n.arrival_step for wave in result.waves for n in wave}
    assert ids_by_step["B"] == 1
    assert ids_by_step["D"] == 2


def test_low_risk_edges_do_not_propagate_far() -> None:
    names = {"A": "A", "B": "B"}
    adj = {"A": [("B", 0.01, 0.01)], "B": []}
    result = propagate("A", names, adj, origin_risk=0.2, decay=0.3, max_hops=4)
    flat = [n.node_id for wave in result.waves for n in wave]
    assert "B" not in flat, "quiet edges should fall below the hop-decay cutoff"


def test_impact_dollars_scale_with_units_and_penalty() -> None:
    a = compute_impact(0.5, units=1000, per_day_penalty_usd=10.0, expected_delay_days=4.0)
    b = compute_impact(0.5, units=2000, per_day_penalty_usd=10.0, expected_delay_days=4.0)
    assert b.dollars_at_risk == a.dollars_at_risk * 2
    assert a.dollars_at_risk == 1000 * 4.0 * 10.0 * 0.5


def test_sla_breaches_zero_when_under_threshold() -> None:
    r = compute_impact(0.2, units=5000, expected_delay_days=1.0, sla_threshold_days=2.0)
    assert r.sla_breaches == 0
    hot = compute_impact(0.9, units=5000, expected_delay_days=5.0, sla_threshold_days=2.0)
    assert hot.sla_breaches > 0
