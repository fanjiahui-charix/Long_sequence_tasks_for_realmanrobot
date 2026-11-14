"""Attribute recorded decisions using their contemporaneous state and feedback."""

from ..schemas import DecisionEvidence


def decision_error_reasons(record: DecisionEvidence) -> list[str]:
    before = record.state_before
    mission = before.get("mission") or {}
    decision = record.decision
    if decision.action_type == "FINISH":
        if record.verification is None or record.verification.verified:
            return []
        reasons = []
        if (
            mission.get("start_location") is not None
            and "current_location" in before
            and before["current_location"] != mission["start_location"]
        ):
            reasons.append("当前状态尚未确认返回起点，却提出结束任务。")
        if ("grasp_state" in before and before["grasp_state"] != "HELD") or (
            mission.get("object_category") is not None
            and "grasped_object" in before
            and before["grasped_object"] != mission["object_category"]
        ):
            reasons.append("当前状态未确认持有目标，却提出结束任务。")
        if before.get("uncertain_action"):
            reasons.append("物理动作尚未核清，却提出结束任务。")
        return reasons
    result = record.tool_result
    if result is None or result.status == "SUCCEEDED" or result.dispatched:
        return []
    reasons = []
    if result.error_code == "INVALID_ARGUMENT":
        reasons.append("提出的工具参数不符合公开的高层工具约定。")
    name = decision.tool_name
    if name == "observe_robot_state":
        return reasons
    if before.get("uncertain_action"):
        reasons.append("已知上一物理动作未核清，仍提出新的物理技能。")
    observation = before.get("latest_observation") or {}
    if (
        observation.get("arm_idle") is False
        or observation.get("motion_settled") is False
        or observation.get("navigation_status") == "MOVING"
    ):
        reasons.append("已知机器人仍在运动或机械臂忙碌，仍提出后续物理技能。")
    if (
        name in {"locate_object", "grasp_object"}
        and mission.get("source_location") is not None
        and before.get("current_location") != mission["source_location"]
    ):
        reasons.append("当前状态未确认到达目标区域，仍提出定位或抓取。")
    if name == "grasp_object":
        if "grasp_state" in before and before["grasp_state"] != "NOT_HELD":
            reasons.append("当前持物状态不允许抓取，仍提出抓取。")
        pose = before.get("pose")
        if "pose" in before and pose is None:
            reasons.append("当前没有有效位姿，却跳过定位提出抓取。")
        elif isinstance(pose, dict) and decision.arguments.get(
            "pose_reference"
        ) != pose.get("pose_id"):
            reasons.append("抓取提案没有引用当前工作记忆中的位姿。")
    return reasons


def classify_failure(record: DecisionEvidence) -> tuple[str, bool]:
    if decision_error_reasons(record):
        return "DECISION_ERROR", True
    if record.tool_result is not None and record.tool_result.dispatched:
        return "EXECUTION_FAILURE", False
    # State may have changed during model latency. A runtime rejection alone
    # does not prove the decision contradicted its original inputs.
    return "UNDETERMINED", False


def project_decision(record: DecisionEvidence) -> dict:
    def project_state(state):
        mission = state.get("mission") or {}
        pose = state.get("pose")
        observation = state.get("latest_observation") or {}
        return {
            "current_location": state.get("current_location"),
            "start_location": mission.get("start_location"),
            "source_location": mission.get("source_location"),
            "grasp_state": state.get("grasp_state"),
            "holding_target": mission.get("object_category") is not None
            and state.get("grasped_object") == mission["object_category"],
            "pose_available": pose is not None,
            "pose_reference_matches_current": bool(
                isinstance(pose, dict)
                and record.decision.arguments.get("pose_reference")
                == pose.get("pose_id")
            ),
            "uncertain_action": state.get("uncertain_action"),
            "last_error": state.get("last_error"),
            "retry_counts": state.get("retry_counts", {}),
            "arm_idle": observation.get("arm_idle"),
            "motion_settled": observation.get("motion_settled"),
        }

    result = record.tool_result
    verification = result.verification if result is not None else record.verification
    return {
        "turn": record.turn,
        "decision": {
            "action_type": record.decision.action_type,
            "tool_name": record.decision.tool_name,
            # Historical pose IDs, file paths and arbitrary raw parameters do not
            # enter a later model prompt. Matching is represented as a boolean.
            "arguments": {
                key: value
                for key, value in record.decision.arguments.items()
                if key in {"target", "object_category"}
            },
        },
        "before": project_state(record.state_before),
        "after": project_state(record.state_after),
        "result": {
            "status": result.status if result is not None else "FINISH_CHECK",
            "error_code": result.error_code
            if result is not None
            else verification.error_code
            if verification is not None
            else None,
            "dispatched": result.dispatched if result is not None else False,
            "postconditions_verified": verification.verified
            if verification is not None
            else False,
        },
    }
