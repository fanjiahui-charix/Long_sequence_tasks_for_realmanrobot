from robot_agent.memory.episodic import EpisodicMemory
from robot_agent.schemas import Episode


def test_sqlite_persists_filters_and_excludes_unverified(tmp_path):
    path = tmp_path / "memory.sqlite3"
    with EpisodicMemory(path) as store:
        failure = Episode(
            mission_id="m1",
            object_category="glasses_case",
            executed_skill="grasp_object",
            failure_type="POSE_STALE",
            failure_observation={"pose_valid": False},
        )
        episode_id = store.save(failure)
        assert store.retrieve(object_category="glasses_case") == []
        store.mark_recovered(
            episode_id, ["locate_object", "grasp_object"], {"grasp_state": "HELD"}
        )
    with EpisodicMemory(path) as store:
        found = store.retrieve(
            skill="grasp_object",
            failure_type="POSE_STALE",
            object_category="glasses_case",
        )
        assert len(found) == 1 and found[0].verified
        assert found[0].recovery_strategy == ["locate_object", "grasp_object"]
        assert store.retrieve(object_category="mug") == []
        assert store.retrieve(skill="navigate_to") == []
        assert store.retrieve(failure_type="x' OR 1=1 --") == []
        assert store.retrieve(limit=1000) == found


def test_unverified_success_cannot_be_written(tmp_path):
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Episode(
            mission_id="m",
            object_category="glasses_case",
            executed_skill="grasp_object",
            recovery_result="VERIFIED_SUCCESS",
            verified=False,
        )
