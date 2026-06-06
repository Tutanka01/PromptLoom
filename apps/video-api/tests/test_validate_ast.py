from __future__ import annotations

import pytest

from video_api.pipeline.validate import validate_scene_ast_security


_VALID_SCENE = """\
class Scene1_HookEN(EnglishGeneratedScene):
    scene_key = "Scene1_HookEN"
    fallback_duration = 30

    def construct(self):
        self.begin_sync()
        bg = make_background()
        title = title_bar("Introduction")
        node = card("concept", width=2.5, color=USER, font_size=22)
        node.move_to(ORIGIN)
        self.add(bg)
        self.play_until(0.12, FadeIn(title))
        self.play_until(0.40, FadeIn(node, shift=UP * 0.1))
        self.play_until(0.75, node.animate.set_stroke(KERNEL, width=4))
        self.play_until(0.88, FadeIn(t("done", 24, TEXT)))
        self.finish_sync()
        self.play(FadeOut(fade_group(bg, title, node)), run_time=0.7)
"""


def test_valid_scene_passes() -> None:
    validate_scene_ast_security(_VALID_SCENE, "Scene1_HookEN")


def test_eval_is_rejected() -> None:
    code = _VALID_SCENE.replace(
        "self.begin_sync()", "eval('import os; os.system(\"rm -rf /\")')\n        self.begin_sync()"
    )
    with pytest.raises(ValueError, match="eval"):
        validate_scene_ast_security(code, "Scene1_HookEN")


def test_exec_is_rejected() -> None:
    code = _VALID_SCENE.replace(
        "self.begin_sync()", "exec('x=1')\n        self.begin_sync()"
    )
    with pytest.raises(ValueError, match="exec"):
        validate_scene_ast_security(code, "Scene1_HookEN")


def test_open_is_rejected() -> None:
    code = _VALID_SCENE.replace(
        "self.begin_sync()", "open('/etc/passwd').read()\n        self.begin_sync()"
    )
    with pytest.raises(ValueError, match="open"):
        validate_scene_ast_security(code, "Scene1_HookEN")


def test_import_os_is_rejected() -> None:
    code = "import os\n" + _VALID_SCENE
    with pytest.raises(ValueError, match="os"):
        validate_scene_ast_security(code, "Scene1_HookEN")


def test_import_subprocess_is_rejected() -> None:
    code = "import subprocess\n" + _VALID_SCENE
    with pytest.raises(ValueError, match="subprocess"):
        validate_scene_ast_security(code, "Scene1_HookEN")


def test_from_import_os_is_rejected() -> None:
    code = "from os import path\n" + _VALID_SCENE
    with pytest.raises(ValueError, match="os"):
        validate_scene_ast_security(code, "Scene1_HookEN")


def test_unexpected_import_is_rejected() -> None:
    """Even safe-looking imports not in the allowlist should be rejected."""
    code = "import random\n" + _VALID_SCENE
    with pytest.raises(ValueError, match="random"):
        validate_scene_ast_security(code, "Scene1_HookEN")


def test_os_system_via_attribute_is_rejected() -> None:
    code = _VALID_SCENE.replace(
        "self.begin_sync()", "os.system('id')\n        self.begin_sync()"
    )
    with pytest.raises(ValueError, match=r"\.system"):
        validate_scene_ast_security(code, "Scene1_HookEN")


def test_syntax_error_raises_value_error() -> None:
    code = "class Broken:\n    def construct(:\n"
    with pytest.raises(ValueError, match="Syntax error"):
        validate_scene_ast_security(code, "BrokenScene")


def test_numpy_import_is_allowed() -> None:
    code = "import numpy as np\n" + _VALID_SCENE
    validate_scene_ast_security(code, "Scene1_HookEN")


def test_math_import_is_allowed() -> None:
    code = "import math\n" + _VALID_SCENE
    validate_scene_ast_security(code, "Scene1_HookEN")
