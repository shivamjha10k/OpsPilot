from __future__ import annotations

from .models import ScenarioGroundTruth


def load_ground_truth() -> dict[str, ScenarioGroundTruth]:
    """Build benchmark labels from the simulator's real scenario definitions."""
    import importlib.util
    from pathlib import Path

    scenarios_path = Path(__file__).resolve().parents[1] / "simulator" / "scenarios.py"
    spec = importlib.util.spec_from_file_location("opspilot_benchmark_scenarios", scenarios_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load simulator scenarios from {scenarios_path}")
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    SCENARIOS = module.SCENARIOS

    result: dict[str, ScenarioGroundTruth] = {}
    for name, scenario in SCENARIOS.items():
        action_aliases = {"rollback": "rollback_deployment"}
        action_list = [action_aliases.get(part.strip(), part.strip()) for part in scenario.recommended_action.split(" or ")]
        actions = frozenset(action_list)
        result[name] = ScenarioGroundTruth(
            scenario=name,
            trigger_condition=scenario.trigger,
            expected_root_cause=scenario.expected_root_cause,
            acceptable_root_causes=frozenset({scenario.expected_root_cause}),
            expected_evidence=scenario.expected_evidence,
            expected_action=action_list[0],
            acceptable_actions=actions,
            expected_risk_level=scenario.risk_level,
            recovery_conditions=scenario.recovery_conditions,
        )
    return result
