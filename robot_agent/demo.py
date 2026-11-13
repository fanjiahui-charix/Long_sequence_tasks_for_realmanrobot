from .schemas import MissionSpec


def demo_mission(mission_id=None):
    values = {
        "instruction": "从 A 出发，到 B 桌子拿起黑色眼镜盒，保持夹持并返回 A。",
        "start_location": "A",
        "source_location": "B",
        "target_object": "black glasses case",
        "object_category": "glasses_case",
        "scene_entities": ["A", "B", "table", "black glasses case"],
        "location_mapping": {"A": "mock_A", "B": "mock_B"},
    }
    if mission_id:
        values["mission_id"] = mission_id
    return MissionSpec(**values)
