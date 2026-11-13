from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import StrictBool, model_validator
from .schemas import Contract, MissionSpec


class MissionDraft(Contract):
    start_location: Literal["A"]
    source_location: Literal["B"]
    target_object: str
    object_category: Literal["glasses_case"]
    scene_entities: list[str]
    scene_supported: StrictBool = True

    @model_validator(mode="after")
    def supported(self):
        if not self.scene_supported or not {
            "A",
            "B",
            "table",
            "black glasses case",
        }.issubset(self.scene_entities):
            raise ValueError(
                "V1 requires an image-grounded A/B/table/black-glasses-case scene"
            )
        return self


async def understand_mission(client, instruction, image_path, location_mapping):
    import json

    image = Path(image_path)
    prompt = (Path(__file__).parent / "prompts/mission_understanding.md").read_text(
        encoding="utf-8"
    )
    draft = await client.structured(
        MissionDraft,
        prompt,
        json.dumps(
            {
                "instruction": instruction,
                "allowed_location_labels": sorted(location_mapping),
            },
            ensure_ascii=False,
        ),
        image_path=image,
    )
    return MissionSpec(
        instruction=instruction,
        start_location=draft.start_location,
        source_location=draft.source_location,
        target_object=draft.target_object,
        object_category=draft.object_category,
        scene_entities=draft.scene_entities,
        location_mapping=dict(location_mapping),
        scene_image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
    )
