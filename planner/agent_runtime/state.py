from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .models import FailureCode, jsonable


@dataclass
class ObjectPoseState:
    pose: list[list[float]] | None = None
    frame_id: str | None = None
    timestamp: float | None = None
    source: str | None = None
    confidence: float | None = None
    valid: bool = False

    def is_fresh(self, *, now: float, ttl_s: float) -> bool:
        return self.valid and self.timestamp is not None and 0.0 <= now - self.timestamp <= ttl_s

    def to_dict(self) -> dict[str, Any]:
        return {
            "pose": jsonable(self.pose),
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "confidence": self.confidence,
            "valid": self.valid,
        }


@dataclass
class ObjectState:
    name: str
    visible: bool | None = None
    pose: ObjectPoseState | None = None
    grasped: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "visible": self.visible,
            "pose": self.pose.to_dict() if self.pose else None,
            "grasped": self.grasped,
        }


@dataclass
class WorldState:
    current_location: str | None = None
    robot_pose: dict[str, Any] | None = None
    objects: dict[str, ObjectState] = field(default_factory=dict)
    holding_object: str | None = None
    facts: set[str] = field(default_factory=lambda: {"HandEmpty"})
    completed_steps: list[str] = field(default_factory=list)
    last_failure: FailureCode | None = None
    revision: int = 0

    def snapshot(self) -> dict[str, Any]:
        return {
            "current_location": self.current_location,
            "robot_pose": jsonable(self.robot_pose),
            "objects": {
                name: self.objects[name].to_dict()
                for name in sorted(self.objects)
            },
            "holding_object": self.holding_object,
            "facts": sorted(self.facts),
            "completed_steps": list(self.completed_steps),
            "last_failure": self.last_failure.value if self.last_failure else None,
            "revision": self.revision,
        }

    def stable_hash(self) -> str:
        encoded = json.dumps(
            self.snapshot(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def commit(
        self,
        *,
        step_id: str,
        produced: set[str],
        invalidated: set[str],
        updates: dict[str, Any] | None = None,
    ) -> None:
        if step_id in self.completed_steps:
            raise ValueError(f"step already committed: {step_id}")
        updates = dict(updates or {})
        self.facts.difference_update(invalidated)
        self.facts.update(produced)
        if "current_location" in updates:
            self.current_location = updates["current_location"]
        if "robot_pose" in updates:
            self.robot_pose = updates["robot_pose"]
        if "holding_object" in updates:
            self.holding_object = updates["holding_object"]
        object_updates = updates.get("objects", {})
        for name, value in object_updates.items():
            if isinstance(value, ObjectState):
                self.objects[name] = value
            elif isinstance(value, dict):
                raw_pose = value.get("pose")
                pose = raw_pose if isinstance(raw_pose, ObjectPoseState) else None
                if isinstance(raw_pose, dict):
                    pose = ObjectPoseState(**raw_pose)
                self.objects[name] = ObjectState(
                    name=name,
                    visible=value.get("visible"),
                    pose=pose,
                    grasped=value.get("grasped"),
                )
        self.completed_steps.append(step_id)
        self.last_failure = None
        self.revision += 1
