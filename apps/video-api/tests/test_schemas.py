from __future__ import annotations

import pytest
from pydantic import ValidationError

from video_api.pipeline.llm import fake_blueprint
from video_api.schemas import VideoBlueprint


def test_fake_blueprint_validates() -> None:
    blueprint = fake_blueprint("Explain syscalls", "linux-fondamentaux")
    assert isinstance(blueprint, VideoBlueprint)
    assert blueprint.scenes[0].key == "Scene1_HookEN"


def test_scene_keys_must_be_ordered() -> None:
    data = fake_blueprint("Explain syscalls").model_dump()
    data["scenes"][1]["key"] = "Scene9_WrongEN"
    with pytest.raises(ValidationError):
        VideoBlueprint.model_validate(data)
