from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from ..schemas import Episode, ExperienceSummary


class EpisodicMemory:
    def __init__(self, path: str | Path):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), timeout=5)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS episodes (
              episode_id TEXT PRIMARY KEY, mission_id TEXT NOT NULL,
              task_type TEXT NOT NULL, object_category TEXT NOT NULL,
              executed_skill TEXT NOT NULL, failure_type TEXT,
              verified INTEGER NOT NULL DEFAULT 0 CHECK(verified IN (0,1)),
              created_at REAL NOT NULL, payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS episode_lookup
              ON episodes(task_type, object_category, executed_skill, failure_type, verified, created_at);
            CREATE TABLE IF NOT EXISTS missions (
              mission_id TEXT PRIMARY KEY, status TEXT NOT NULL, verified INTEGER NOT NULL,
              updated_at REAL NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS skill_events (
              id INTEGER PRIMARY KEY, mission_id TEXT NOT NULL, skill TEXT NOT NULL,
              status TEXT NOT NULL, failure_type TEXT, created_at REAL NOT NULL, payload TEXT NOT NULL);
        """)

    def save(self, episode: Episode) -> str:
        self.connection.execute(
            "INSERT INTO episodes VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(episode_id) DO UPDATE SET verified=excluded.verified,payload=excluded.payload",
            (
                episode.episode_id,
                episode.mission_id,
                episode.task_type,
                episode.object_category,
                episode.executed_skill,
                episode.failure_type,
                int(episode.verified),
                episode.created_at,
                episode.model_dump_json(),
            ),
        )
        self.connection.commit()
        return episode.episode_id

    def get(self, episode_id: str) -> Episode:
        row = self.connection.execute(
            "SELECT payload FROM episodes WHERE episode_id=?", (episode_id,)
        ).fetchone()
        if row is None:
            raise KeyError(episode_id)
        return Episode.model_validate_json(row[0])

    def mark_recovered(self, episode_id, strategy, evidence) -> Episode:
        """Record recovery evidence without producing model analysis."""
        payload = self.get(episode_id).model_dump()
        payload.update(
            recovery_strategy=strategy,
            verification_result=evidence,
            verified=True,
            recovery_result="VERIFIED_SUCCESS",
            experience=None,
            experience_status="PENDING",
            experience_provider=None,
            experience_error=None,
        )
        episode = Episode.model_validate(payload)
        self.save(episode)
        return episode

    def save_experience(
        self, episode_id: str, summary: ExperienceSummary, provider: str
    ) -> Episode:
        """Save analysis without changing the recovery's verification status."""
        payload = self.get(episode_id).model_dump()
        payload.update(
            experience=ExperienceSummary.model_validate(summary).model_dump(),
            experience_status="READY",
            experience_provider=provider,
            experience_error=None,
        )
        episode = Episode.model_validate(payload)
        self.save(episode)
        return episode

    def fail_experience(self, episode_id: str, error_code: str) -> Episode:
        payload = self.get(episode_id).model_dump()
        payload.update(
            experience=None,
            experience_status="FAILED",
            experience_provider=None,
            experience_error=error_code,
        )
        episode = Episode.model_validate(payload)
        self.save(episode)
        return episode

    def pending_experiences(self, mission_id: str) -> list[Episode]:
        rows = self.connection.execute(
            "SELECT payload FROM episodes WHERE mission_id=? ORDER BY created_at,episode_id",
            (mission_id,),
        )
        try:
            episodes = (Episode.model_validate_json(row[0]) for row in rows)
            return [
                episode
                for episode in episodes
                if episode.experience_status in {"PENDING", "FAILED"}
            ]
        finally:
            rows.close()

    def retrieve(
        self,
        *,
        skill=None,
        failure_type=None,
        object_category=None,
        task_type="mobile_pick_and_return",
        limit=3,
    ):
        clauses, values = ["task_type=?", "verified=1"], [task_type]
        for column, value in [
            ("executed_skill", skill),
            ("failure_type", failure_type),
            ("object_category", object_category),
        ]:
            if value is not None:
                clauses.append(column + "=?")
                values.append(value)
        limit = max(1, min(int(limit), 3))
        # Old JSON payloads default to PENDING. Limit only after READY filtering,
        # so newer unsummarized rows cannot hide older usable experience.
        rows = self.connection.execute(
            "SELECT payload FROM episodes WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC,episode_id",
            values,
        )
        found = []
        try:
            for row in rows:
                episode = Episode.model_validate_json(row[0])
                if not episode.verified or episode.experience_status != "READY":
                    continue
                found.append(episode)
                if len(found) >= limit:
                    break
        finally:
            rows.close()
        return found

    def record_skill(self, mission_id, result):
        self.connection.execute(
            "INSERT INTO skill_events(mission_id,skill,status,failure_type,created_at,payload) VALUES (?,?,?,?,?,?)",
            (
                mission_id,
                result.tool_name,
                result.status,
                result.error_code,
                result.finished_at,
                result.model_dump_json(),
            ),
        )
        self.connection.commit()

    def record_mission(self, state, *, verified=False):
        self.connection.execute(
            "INSERT INTO missions VALUES(?,?,?,?,?) ON CONFLICT(mission_id) DO UPDATE SET status=excluded.status,verified=excluded.verified,updated_at=excluded.updated_at,payload=excluded.payload",
            (
                state.mission.mission_id,
                state.mission_status,
                int(verified),
                time.time(),
                state.model_dump_json(),
            ),
        )
        self.connection.commit()

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
