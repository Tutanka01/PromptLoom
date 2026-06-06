from __future__ import annotations

import pytest
from pydantic import ValidationError

from video_api.pipeline.llm import fake_blueprint
from video_api.schemas import VideoBlueprint


def test_fake_blueprint_validates() -> None:
    blueprint = fake_blueprint("Explain derivatives", "math")
    assert isinstance(blueprint, VideoBlueprint)
    assert blueprint.scenes[0].key == "Scene1_HookEN"
    assert blueprint.target_duration_seconds == 240
    assert len(blueprint.scenes) == 8
    assert blueprint.subject_area == "math"
    assert blueprint.difficulty == "intro"
    assert blueprint.learning_objectives
    assert {scene.layout for scene in blueprint.scenes} >= {"concept_map", "equation_transform", "graph_plot"}


def test_scene_keys_must_be_ordered() -> None:
    data = fake_blueprint("Explain derivatives").model_dump()
    data["scenes"][1]["key"] = "Scene9_WrongEN"
    with pytest.raises(ValidationError):
        VideoBlueprint.model_validate(data)


def test_default_length_blueprints_need_enough_scenes() -> None:
    data = fake_blueprint("Explain derivatives").model_dump()
    with pytest.raises(ValidationError, match="at least 8 scenes"):
        VideoBlueprint.model_validate(data | {"scenes": data["scenes"][:3]})
