from pathlib import Path


def test_preserved_navigation_resolves_migrated_hardware_config():
    from navigation.run_navigation import DEFAULT_TARGET_MAP_PATH, load_targets

    assert DEFAULT_TARGET_MAP_PATH.is_file()
    assert "planner" not in DEFAULT_TARGET_MAP_PATH.parts
    assert load_targets(DEFAULT_TARGET_MAP_PATH)["table_1"] == "dianA"


def test_core_imports_no_retired_agent_or_hardware_runtime():
    import ast

    root = Path(__file__).resolve().parents[1] / "robot_agent"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("planner"), path
