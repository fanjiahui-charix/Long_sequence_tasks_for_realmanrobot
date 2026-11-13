from __future__ import annotations

import json
import time
from ..schemas import Observation
from .process import ProcessRunner


class JsonStateReader:
    """Platform-neutral read-only bridge. Command comes from operator config,
    never the model. Its stdout is a timestamped Observation JSON object.
    Unsupported facts must remain None/UNKNOWN; requested actuator values must
    never be emitted as measured samples. See docs/BACKEND_API.md.
    """

    def __init__(self, command, *, runner=None, timeout_s=5):
        self.command = list(command)
        self.runner = runner or ProcessRunner()
        self.timeout_s = timeout_s

    async def read(self, mission):
        output = await self.runner.run(self.command, timeout_s=self.timeout_s)
        payload = json.loads(output.stdout)
        if "timestamp" not in payload:
            raise ValueError(
                "state bridge must supply its measurement/receipt timestamp"
            )
        return Observation.model_validate(payload)

    async def localization_valid(self, mission, *, max_age_s=5):
        obs = await self.read(mission)
        if not 0 <= time.time() - obs.timestamp <= max_age_s:
            return None
        return obs.localization_confirmed
