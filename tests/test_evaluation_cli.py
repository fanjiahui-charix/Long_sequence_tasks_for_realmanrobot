import json
import subprocess
import sys
from pathlib import Path

from robot_agent.evaluation import evaluate


def test_ab_evaluation_has_honest_denominators_and_persistent_memory(tmp_path):
    result = evaluate(repetitions=2, output_dir=tmp_path)
    assert result["evaluation"] == "Mock/API-level Evaluation"
    assert set(result["groups"]) == {"A", "B"}
    for metrics in result["groups"].values():
        assert metrics["mission_count"] == 20
        assert metrics["false_completion_count"] == 0
        assert metrics["llm_calls"] == 0
        assert metrics["task_completion_rate"] < 1
        assert metrics["recovery_success_rate"] <= 1
    assert result["groups"]["B"]["episodes_retrieved"] > 0
    assert (tmp_path / "metrics.json").is_file()
    assert (tmp_path / "missions.jsonl").is_file()


def test_demo_cli_runs_from_a_clean_process(tmp_path):
    root = Path(__file__).resolve().parents[1]
    cp = subprocess.run(
        [
            sys.executable,
            "-m",
            "robot_agent",
            "demo",
            "--output-dir",
            str(tmp_path),
            "--memory",
            "--fault",
            "POSE_STALE",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert cp.returncode == 0, cp.stderr
    data = json.loads((tmp_path / "mission_report.json").read_text(encoding="utf-8"))
    assert data["status"] == "COMPLETED"
    assert data["metrics"]["recoveries"] >= 1
    assert "Mock/API-level Evaluation" in cp.stdout
