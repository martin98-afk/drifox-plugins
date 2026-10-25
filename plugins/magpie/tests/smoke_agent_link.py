# -*- coding: utf-8 -*-
"""agent_link 冒烟：注册表读写 + 幂等 + 真 magpie 生效判定。

跑法（项目 venv）：
    python plugins/magpie/tests/smoke_agent_link.py

用临时 XDG_CONFIG_HOME 隔离，不碰用户真实 magpie 配置。
"""
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agent_link", ROOT / "ui" / "agent_link.py")
mod = importlib.util.module_from_spec(spec)
SPEC_OK = True
spec.loader.exec_module(mod)

tmp = Path(tempfile.mkdtemp(prefix="magpie-link-"))
old_xdg = os.environ.get("XDG_CONFIG_HOME")
os.environ["XDG_CONFIG_HOME"] = str(tmp)
try:
    cfg = tmp / "magpie"
    reg = cfg / "plugins.json"
    assert mod.magpie_config_dir() == cfg, mod.magpie_config_dir()
    assert mod.registry_path() == reg

    # 插件包路径随插件目录推导，且真实存在
    assert mod.agent_plugin_dir().name == "agent_plugin"
    assert (mod.agent_plugin_dir() / "drifox.agent.js").is_file()

    # 无注册表 → 未登记
    assert not reg.exists()
    assert mod.is_registered() is False

    # 首次登记：创建文件
    state, info = mod.ensure_registered()
    assert state == "registered", (state, info)
    data = json.loads(reg.read_text(encoding="utf-8"))
    assert len(data["plugins"]) == 1
    assert Path(data["plugins"][0]["spec"]) == mod.agent_plugin_dir()
    assert mod.is_registered() is True

    # 幂等：再登记不追加
    state2, _ = mod.ensure_registered()
    assert state2 == "already", state2
    assert len(json.loads(reg.read_text(encoding="utf-8"))["plugins"]) == 1

    # 保留用户已有条目与额外字段
    reg.write_text(
        json.dumps(
            {
                "plugins": [
                    {"spec": "C:/some/other/plugin", "options": {"k": 1}},
                    {"spec": str(mod.agent_plugin_dir())},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert mod.is_registered() is True
    assert mod.ensure_registered()[0] == "already"
    kept = json.loads(reg.read_text(encoding="utf-8"))["plugins"]
    assert kept[0] == {"spec": "C:/some/other/plugin", "options": {"k": 1}}, kept

    # 路径比较对分隔符/大小写不敏感（Windows）
    reg.write_text(json.dumps({"plugins": [{"spec": str(mod.agent_plugin_dir()).replace("\\", "/")}]}), encoding="utf-8")
    assert mod.is_registered() is True

    # 损坏的注册表 → 明确报错，不静默覆盖
    reg.write_text("{ not json", encoding="utf-8")
    state3, info3 = mod.ensure_registered()
    assert state3 == "error" and "读取失败" in info3, (state3, info3)
    assert reg.read_text(encoding="utf-8") == "{ not json"  # 原样保留

    # 插件包缺失 → 明确报错
    reg.unlink()
    real_dir = mod.agent_plugin_dir
    mod.agent_plugin_dir = lambda: Path(tempfile.mkdtemp()) / "nope"
    state4, info4 = mod.ensure_registered()
    assert state4 == "error" and "缺失" in info4, (state4, info4)
    mod.agent_plugin_dir = real_dir

    print("agent_link ok: 登记/幂等/保留他人条目/路径归一/损坏不覆盖/缺包报错")
finally:
    if old_xdg is None:
        os.environ.pop("XDG_CONFIG_HOME", None)
    else:
        os.environ["XDG_CONFIG_HOME"] = old_xdg
    shutil.rmtree(tmp, ignore_errors=True)
