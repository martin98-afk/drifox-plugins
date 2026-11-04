# -*- coding: utf-8 -*-
"""B站工具实现层：vendor server 的工具函数在宿主进程内直接执行。

MCP 化后本模块不再注册 DriFox tools（tools/ 常用工具通道已撤）：
biliscroll_core/control_server.py 经 HTTP 把 mcp/server.py（stdio 子进程）
的调用路由到这里。宿主进程内自带 deps 注入、stdlib 与 PIL 仲裁、凭证 env，
MCP 子进程只做 stdio→HTTP 转发，不碰任何重依赖。

为什么不走 stdio MCP 直接拉起 vendor server：vendored 二进制（cp314 .pyd）
必须与解释器 ABI 匹配，.mcp.json 拉起的系统 py -3 加载不了；两段式（browser
插件同款）让子进程只依赖 mcp+httpx，bridge.json 自引导可用解释器。
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
from pathlib import Path

from loguru import logger

# 宿主 tools/UI 加载器不注插件根，先自注入再 import 本插件包
_PLUGIN_ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT_DIR)

from biliscroll_core.paths import PLUGIN_ROOT

_VENDOR_DIR = PLUGIN_ROOT / "vendor" / "bilibili-mcp"

# duty_* 窄口五件套由 DriFox 侧 tools/bili_duty_data.py 等价实现（值班轮专用
# DriFox tools，非 B站 API 工具）；转写三件 v1 未启用（章程声明跳过口径）。
# 均不在 MCP 工具表。
_EXCLUDED = ("duty_", "bili_transcribe")

_CRED_DEFAULT = PLUGIN_ROOT / "data" / "bili_credential.json"
_DUTY = PLUGIN_ROOT / "data" / "duty"


def _cred_path() -> Path:
    """凭证落 plugin_data（规范位置）；能力池不可用回退插件 data/（重装即弃）。"""
    try:
        from biliscroll_core.paths import plugin_data_root

        root = plugin_data_root()
        if root:
            return root / "bili_credential.json"
    except Exception:
        pass
    return _CRED_DEFAULT


os.environ.setdefault("BILI_CRED_FILE", str(_cred_path()))
os.environ.setdefault("BILI_DUTY_HOME", str(_DUTY))

# PIL / stdlib 仲裁（必须在 import mcp_server 前）——详见 pil_arbiter.py。
# biliscroll_core.* 是共享顶层名模块，热重载滞留旧版；本模块无跨轮状态，reload 自愈。
import biliscroll_core.pil_arbiter  # noqa: E402

importlib.reload(biliscroll_core.pil_arbiter)
from biliscroll_core.pil_arbiter import prefer_vendored_pil, prefer_vendored_stdlib  # noqa: E402

prefer_vendored_pil()
prefer_vendored_stdlib(PLUGIN_ROOT / "deps" / "_pystdlib_xml")


def _patch_web_qrcode_login():
    """vendor patch ⑨：B站 2026-08 扫码登录响应改版。

    上游 bilibili-api ≤17.4.2（已停更）的 QrCodeLogin.check_state 只从 poll
    响应 cred_url 的 query string 解析 cookie；新版 data.url 是
    crossDomain?ticket=... 票据链接，真正 cookie 改为跟随该链接时的
    Set-Cookie 响应头下发 → 三个参数全部解析为空仍报「登录成功」（假象，
    后续所有要凭证的工具报缺 sessdata）。按 bilibili-cli PR #27 思路重写
    WEB 分支：轮询判定照旧；DONE 时若 url 无 cookie 参数，带浏览器 UA 跟随
    票据链接，从 cookie jar 提取。不能事后重 poll（qrcode_key 成功即失效）。
    """
    import httpx as _httpx

    from bilibili_api import login_v2 as _lv2

    cls = _lv2.QrCodeLogin
    # 无幂等守卫：覆盖式赋值本身幂等；若加标记守卫，reload 换新补丁时会被
    # 类上的旧标记挡住（实测：update_params 修复被旧 check_state 继续遮蔽）
    poll_api = _lv2.API["qrcode"]["web"]["get_events"]
    orig_check = cls.check_state
    browser_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    async def check_state(self):
        if getattr(self, "_QrCodeLogin__platform", None) != _lv2.QrCodeLoginChannel.WEB:
            return await orig_check(self)
        events = (
            await _lv2.Api(credential=_lv2.Credential(), **poll_api)
            .update_params(qrcode_key=self._QrCodeLogin__qr_key)
            .result
        )
        code = events["code"]
        if code == 86101:
            return _lv2.QrCodeLoginEvents.SCAN
        if code == 86090:
            return _lv2.QrCodeLoginEvents.CONF
        if code == 86038:
            return _lv2.QrCodeLoginEvents.TIMEOUT

        cred_url = events["url"]
        ac_time_value = events.get("refresh_token") or ""
        sessdata = bili_jct = dedeuserid = ""
        if "SESSDATA=" in cred_url:
            # 旧格式：cookie 直接在 query string（上游原解析，修正前缀判断）
            for cookie in cred_url.split("?")[1].split("&"):
                if cookie.startswith("SESSDATA="):
                    sessdata = cookie[len("SESSDATA="):]
                elif cookie.startswith("bili_jct="):
                    bili_jct = cookie[len("bili_jct="):]
                elif cookie.upper().startswith("DEDEUSERID="):
                    dedeuserid = cookie[len("DEDEUSERID="):]
        else:
            # 新格式：票据链接，cookie 走跳转链的 Set-Cookie
            headers = {"User-Agent": browser_ua, "Referer": "https://passport.bilibili.com/"}
            async with _httpx.AsyncClient(
                follow_redirects=True, headers=headers, timeout=15
            ) as client:
                await client.get(cred_url)
                jar = client.cookies.jar
                for cookie in jar:
                    name = cookie.name or ""
                    if name == "SESSDATA":
                        sessdata = cookie.value or ""
                    elif name == "bili_jct":
                        bili_jct = cookie.value or ""
                    elif name == "DedeUserID":
                        dedeuserid = cookie.value or ""
        if not (sessdata and bili_jct and dedeuserid):
            # 诚实失败优于假成功：qrcode_key 已作废，用户需重新扫码
            raise RuntimeError(
                f"扫码凭证提取不完整（SESSDATA={bool(sessdata)}, bili_jct={bool(bili_jct)}, "
                f"DedeUserID={bool(dedeuserid)}），请重新调用 bili_login 扫码"
            )
        self._QrCodeLogin__credential = _lv2.Credential(
            sessdata=sessdata,
            bili_jct=bili_jct,
            dedeuserid=dedeuserid,
            ac_time_value=ac_time_value,
        )
        return _lv2.QrCodeLoginEvents.DONE

    cls.check_state = check_state
    cls._bili_ticket_patch = True
    logger.info("[bili-scroll] 已打 patch ⑨：WEB 扫码登录支持票据链接换 cookie")


_patch_web_qrcode_login()

if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import mcp_server as _server  # noqa: E402  vendor 模块（import 无副作用）

# vendor 热修（patch ⑨⑩）也受共享顶层名滞留影响；@tool 工具表随模块重建，
# _login_session 进程缓存会丢（扫码中热重载需重扫，可接受）
#
# ⚠️ 必须**先** reload bili_ext 再 reload _server：
#   mcp_server 尾部 `from bili_ext import register_all` 在 reload 时拿到的是
#   sys.modules 里**已存在的旧 bili_ext 模块对象**。只 reload _server 的话，
#   挂载进去的还是旧 register_all ⇒ 改 bili_ext 等于没改（实证：修了分区
#   解析结构，重载后仍返回旧的空结果）。
import importlib as _importlib

# 修过的 vendored SDK 文件（如 utils/picture.py 的临时文件冲突修复）同样会被
# sys.modules 里的旧版挡住 —— bilibili_api 是共享顶层名，reload 必须点名到
# 具体子模块，且要在 reload(_server) 之前完成（_server 在 import 期就绑定了引用）。
for _mod in ("bilibili_api.utils.picture", "bilibili_api.video_uploader"):
    try:
        _m = _importlib.import_module(_mod)
        _importlib.reload(_m)
    except Exception as _e:  # noqa: BLE001 - 单模块失败不阻断整体
        logger.warning(f"[bili-scroll] reload {_mod} 失败: {_e}")

try:
    import bili_ext as _bili_ext

    _importlib.reload(_bili_ext)
except Exception as _e:  # noqa: BLE001 - 扩展模块缺失不应阻断上游工具
    logger.warning(f"[bili-scroll] reload bili_ext 失败（扩展工具可能未更新）: {_e}")

importlib.reload(_server)

IMPLS: dict = {}    # 工具名 → 同步 impl（kwargs → content str）
SCHEMAS: dict = {}  # 工具名 → OpenAI function schema（上游原始定义）


def _make_impl(fn):
    """async 工具函数 → 同步 impl（worker/HTTP 线程无活动 loop，asyncio.run 安全）。

    异常不在此吞：control_server 统一捕获转 {"ok": false, "error": ...}。
    """

    def _impl(**kwargs):
        out = asyncio.run(fn(**kwargs))
        if isinstance(out, str):
            return out
        return json.dumps(out, ensure_ascii=False, default=str)

    return _impl


def _iter_fastmcp_tools():
    """跨 mcp SDK 小版本枚举 FastMCP 工具表（name -> Tool）。"""
    tm = getattr(_server.mcp, "_tool_manager", None)
    tools = getattr(tm, "_tools", None)
    if isinstance(tools, dict):
        return tools
    raise RuntimeError("FastMCP 工具表结构未知（mcp SDK 版本不兼容），无法枚举 B站工具")


def _build():
    for name, tool in sorted(_iter_fastmcp_tools().items()):
        if name.startswith(_EXCLUDED):
            continue
        fn = tool.fn if hasattr(tool, "fn") else tool.func
        IMPLS[name] = _make_impl(fn)
        SCHEMAS[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": (tool.description or "").strip() or name,
                "parameters": tool.parameters or {"type": "object", "properties": {}},
            },
        }


_build()
logger.info(f"[bili-scroll] B站工具实现层就绪：{len(IMPLS)} 个工具（MCP 控制端点后端）")
