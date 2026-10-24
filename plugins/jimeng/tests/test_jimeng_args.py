# -*- coding: utf-8 -*-
"""jimeng 工具参数组装与校验的离线测试（不调用真实 CLI）。

只测纯逻辑：``_build_gen_args`` 的参数映射、必填校验、取值校验，
以及 ``_artifact_for`` 的成果条目形状。真实 CLI 交互需装 CLI + 登录，
不在单测范围。
"""

import sys
from pathlib import Path

import pytest

# 允许从 plugins 目录导入（仓库内无 app 包，故用最小替身注入 ToolResult）
_PLUGIN_TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(_PLUGIN_TOOLS))


class _FakeToolResult:
    def __init__(self, success, content=None, error=None, artfacts=None, **kw):
        self.success = success
        self.content = content
        self.error = error
        self.data = kw.get("data")
        self.artifacts = kw.get("artifacts")


@pytest.fixture(scope="module")
def jm():
    """按文件路径加载 tools/jimeng.py，把宿主 app.tools.result 换成替身。

    不能用 ``import jimeng``：``plugins/jimeng/__init__.py`` 存在，pytest 的
    rootdir 插入会让包名 ``jimeng`` 命中包而非模块。
    """
    import importlib.util
    import types

    app_pkg = types.ModuleType("app")
    tools_pkg = types.ModuleType("app.tools")
    result_mod = types.ModuleType("app.tools.result")
    result_mod.ToolResult = _FakeToolResult
    registry_mod = types.ModuleType("app.tools.registry")
    registry_mod.make_summarize_from_preview = lambda preview: (
        lambda tool_name, tool_args, content: preview(tool_args)
    )
    sys.modules.setdefault("app", app_pkg)
    sys.modules.setdefault("app.tools", tools_pkg)
    sys.modules["app.tools.result"] = result_mod
    sys.modules["app.tools.registry"] = registry_mod

    target = _PLUGIN_TOOLS / "jimeng.py"
    spec = importlib.util.spec_from_file_location("jimeng_tool_under_test", target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── text2image ────────────────────────────────────────────────────


def test_text2image_minimal(jm):
    args, err = jm._build_gen_args("text2image", {"prompt": "a cat", "resolution": "2k"})
    assert err is None
    assert args[0] == "text2image"
    assert "--prompt" in args and "a cat" in args
    assert "--resolution_type" in args and "2k" in args


def test_text2image_requires_resolution(jm):
    _, err = jm._build_gen_args("text2image", {"prompt": "a cat"})
    assert err and "resolution" in err


def test_text2image_rejects_bad_resolution(jm):
    _, err = jm._build_gen_args("text2image", {"prompt": "x", "resolution": "8k"})
    assert err and "resolution" in err


def test_text2image_rejects_bad_ratio(jm):
    _, err = jm._build_gen_args(
        "text2image", {"prompt": "x", "resolution": "2k", "ratio": "5:5"}
    )
    assert err and "ratio" in err


def test_text2image_generate_num_range(jm):
    _, err = jm._build_gen_args(
        "text2image", {"prompt": "x", "resolution": "2k", "generate_num": 11}
    )
    assert err and "1-10" in err


def test_dimensions_must_pair(jm):
    _, err = jm._build_gen_args(
        "text2image", {"prompt": "x", "resolution": "2k", "width": 1024}
    )
    assert err and "成对" in err


def test_dimensions_ok(jm):
    args, err = jm._build_gen_args(
        "text2image", {"prompt": "x", "resolution": "2k", "width": 1024, "height": 768}
    )
    assert err is None
    assert "--width" in args and "--height" in args


# ── image2image ───────────────────────────────────────────────────


def test_image2image_requires_images(jm):
    _, err = jm._build_gen_args(
        "image2image", {"prompt": "x", "resolution": "2k"}
    )
    assert err and "images" in err


def test_image2image_too_many(jm):
    imgs = [f"a{i}.png" for i in range(11)]
    _, err = jm._build_gen_args(
        "image2image", {"images": imgs, "prompt": "x", "resolution": "2k"}
    )
    assert err and "1-10" in err


def test_image2image_ok(jm):
    args, err = jm._build_gen_args(
        "image2image", {"images": ["a.png", "b.png"], "prompt": "x", "resolution": "4k"}
    )
    assert err is None
    assert args.count("--images") == 2


# ── upscale ───────────────────────────────────────────────────────


def test_upscale_requires_image(jm):
    _, err = jm._build_gen_args("upscale", {"resolution": "4k"})
    assert err and "image" in err


def test_upscale_ok(jm):
    args, err = jm._build_gen_args("upscale", {"image": "a.png", "resolution": "8k"})
    assert err is None
    assert "--resolution_type" in args and "8k" in args
    assert "--prompt" not in args


def test_upscale_no_model_flag(jm):
    args, err = jm._build_gen_args(
        "upscale", {"image": "a.png", "resolution": "4k", "model": "5.0"}
    )
    assert err is None
    assert "--model_version" not in args


# ── 视频 ──────────────────────────────────────────────────────────


def test_text2video_ok(jm):
    args, err = jm._build_gen_args(
        "text2video", {"prompt": "run", "resolution": "720p", "duration": 5}
    )
    assert err is None
    assert "--video_resolution" in args and "720p" in args
    assert "--duration" in args and "5" in args


def test_text2video_requires_resolution(jm):
    _, err = jm._build_gen_args("text2video", {"prompt": "run"})
    assert err and "resolution" in err


def test_frames2video_requires_both_frames(jm):
    _, err = jm._build_gen_args(
        "frames2video", {"first": "a.png", "resolution": "720p"}
    )
    assert err and "first" in err and "last" in err


def test_frames2video_ok(jm):
    args, err = jm._build_gen_args(
        "frames2video", {"first": "a.png", "last": "b.png", "resolution": "1080p"}
    )
    assert err is None
    assert "--first" in args and "--last" in args


def test_multiframe_requires_transitions_for_3plus(jm):
    _, err = jm._build_gen_args(
        "multiframe2video",
        {"images": ["a.png", "b.png", "c.png"], "resolution": "720p"},
    )
    assert err and "transition_prompts" in err


def test_multiframe_transition_count_mismatch(jm):
    _, err = jm._build_gen_args(
        "multiframe2video",
        {
            "images": ["a.png", "b.png", "c.png"],
            "transition_prompts": ["one"],
            "resolution": "720p",
        },
    )
    assert err and "2" in err


def test_multiframe_ok(jm):
    args, err = jm._build_gen_args(
        "multiframe2video",
        {
            "images": ["a.png", "b.png", "c.png"],
            "transition_prompts": ["a to b", "b to c"],
            "resolution": "1080p",
        },
    )
    assert err is None
    assert args.count("--transition-prompt") == 2
    assert "--model_version" not in args


def test_multimodal_requires_input(jm):
    _, err = jm._build_gen_args("multimodal2video", {"resolution": "720p"})
    assert err and "multimodal" == "multimodal" or True  # 只断言有错
    assert err


def test_multimodal_ok(jm):
    args, err = jm._build_gen_args(
        "multimodal2video",
        {"images": ["a.png"], "audios": ["m.mp3"], "resolution": "720p"},
    )
    assert err is None
    assert "--image" in args and "--audio" in args


# ── 成果条目 ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,kind",
    [
        ("a.png", "image"),
        ("a.JPG", "image"),
        ("a.webp", "image"),
        ("a.mp4", "video"),
        ("a.mov", "video"),
        ("a.html", "html"),
        ("a.md", "text"),
        ("a.unknown", "file"),
    ],
)
def test_artifact_kind(jm, name, kind):
    art = jm._artifact_for(Path("/tmp") / name)
    assert art["kind"] == kind
    assert art["path"].endswith(name)


def test_artifact_missing_file_size_zero(jm):
    art = jm._artifact_for(Path("/nonexistent/x.png"))
    assert art["size"] == 0
    assert art["name"] == "x.png"


def test_result_with_artifacts_fallback(jm):
    """宿主未升级（ToolResult 不接受 artifacts）时不抛异常。"""

    class _OldResult:
        def __init__(self, success, content=None, error=None, data=None):
            self.success = success
            self.content = content
            self.error = error
            self.data = data

    original = jm.ToolResult
    jm.ToolResult = _OldResult
    try:
        res = jm._result_with_artifacts(
            success=True, content="ok", artifacts=[{"path": "a.png"}]
        )
        assert res.success and res.content == "ok"
        assert not hasattr(res, "artifacts")
    finally:
        jm.ToolResult = original


# ── schema 完整性 ─────────────────────────────────────────────────


def test_schema_covers_all_actions(jm):
    props = jm._SCHEMA["function"]["parameters"]["properties"]
    assert set(props["action"]["enum"]) == set(jm.ALL_ACTIONS)
    assert len(jm.ALL_ACTIONS) == 16


def test_gen_specs_cover_all_gen_actions(jm):
    assert set(jm._GEN_SPECS) == set(jm.GEN_ACTIONS)
