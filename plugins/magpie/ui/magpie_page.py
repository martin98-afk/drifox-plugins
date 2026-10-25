# -*- coding: utf-8 -*-
"""magpie 网页界面内容页（内嵌 magpie web）。

数据源：magpie 的网页服务（默认 127.0.0.1:3430），不是网关 3425——那两个是
不同进程入口，网页服务只在 ``magpie web`` / ``magpie serve --web`` /
``magpie daemon install --web`` 时存在。

页面三态：
- 探测中：显示「正在连接…」
- 不可达：一键启动（经宿主 process.start 能力拉起 magpie web，自动固定 key）
  或命令指引
- 已连上：QWebEngineView 加载，顶部状态条保留「重新加载 / 在浏览器打开」

识别 DriFox（同目录 ``agent_link.py``）：把本插件的 ``agent_plugin/`` 包登记进
magpie 的插件注册表，magpie 的 Agents / Usage / Sessions 页就有 DriFox 一行与
按会话分组的用量。三条路径都调同一个幂等登记函数：拉起 magpie web 前、写「让
AI 帮我装」提示词前、指引面板的「让 magpie 认得 DriFox」按钮。登记只写配置
文件，不依赖 magpie 是否已装，也不依赖 Bun。

key：magpie web 每次启动会换一个随机 key，URL 必须带 ``?k=<key>``。插件自动
管理：配置里没 key 时生成一个稳定随机值存进插件配置，启动进程时以环境变量
``MAGPIE_WEB_KEY`` 注入——之后每次（含插件拉起的每次重启）都是同一个 key，
用户无感。用户在设置卡手填过的 key 优先（``PluginConfigStore.get`` 的语义：
系统环境变量 > 存储值，插件只在两者都空时才生成）。
"""

import os
import secrets
import shutil
import threading
import time

from loguru import logger

from PyQt5.QtCore import QUrl, Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

_PLUGIN = "magpie"
_DEFAULT_WEB_PORT = 3430

_PROFILE_NAME = "magpie-web"


def _caps(cap_id: str):
    """取某能力（full 卡无独立 ctx，统一走 sdk 的 caps_for，host 由宿主解析）。

    抽成模块级函数而非在各处内联 import：无 ctx 场景下 host 解析只有这一条
    路径，内联会让「拿不到能力」的兜底散落多处；也便于测试替换。
    """
    from app.plugins.sdk import caps_for

    return caps_for(cap_id, plugin=_PLUGIN, surface="ui")


def _magpie_installed() -> bool:
    """magpie 可执行文件是否在 PATH 上（决定引导文案走「启动」还是「安装」）。"""
    return shutil.which("magpie") is not None


def _link_status() -> bool:
    """magpie 的插件注册表里是否已有 DriFox 的 agent 条目。

    只读注册表、不起子进程（「已登记」≠「已生效」，生效判定走
    ``agent_link.probe_agent_active``，仅在显式同步时跑）。
    """
    try:
        from . import agent_link

        return agent_link.is_registered()
    except Exception as e:  # noqa: BLE001 — 状态探测失败按未登记处理
        logger.debug(f"[magpie] agent 登记状态探测失败: {e}")
        return False


def _new_web_key() -> str:
    """生成一个 magpie 接受的稳定随机 key（16+ 位字母数字，hex 24 位）。"""
    return secrets.token_hex(12)


def _ensure_web_key(cfg: dict) -> str:
    """取当前生效 key；没有则生成并写回插件配置（下次启动复用同一个）。

    cfg 是启动前的配置快照（含 env 覆盖语义后的 key），避免这里再读一次。
    写回失败不阻断启动：本次仍用该 key（进程已定死），仅记日志。
    """
    key = str((cfg or {}).get("key") or "").strip()
    if key:
        return key
    key = _new_web_key()
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        PluginConfigStore().set_values(_PLUGIN, {"web_key": key})
    except Exception as e:  # noqa: BLE001 — 写失败仅影响下次复用，不阻断本次启动
        logger.warning(f"[magpie] 自动生成的 web key 写回配置失败: {e}")
    return key


def _web_argv(port: int) -> list:
    """组装 magpie web 启动命令（argv 数组；可执行名交给 CreateProcess 补 .exe）。"""
    exe = shutil.which("magpie") or "magpie"
    argv = [exe, "web"]
    if port != _DEFAULT_WEB_PORT:
        argv += ["--addr", f"127.0.0.1:{port}"]
    argv.append("--no-open")
    return argv


def _wait_port(port: int, timeout: float = 12.0) -> bool:
    """轮询等端口就绪（magpie 冷启动含初始化，秒级）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _probe(port, timeout=1.0):
            return True
        time.sleep(0.5)
    return _probe(port, timeout=1.0)


def _read_config() -> dict:
    """读插件设置（端口 / key）。配置系统不可用时回默认值。"""
    try:
        from app.plugins.managers.plugin_config_store import PluginConfigStore

        store = PluginConfigStore()
        port = store.get(_PLUGIN, "web_port")
        return {
            "port": int(port) if str(port or "").strip().isdigit() else _DEFAULT_WEB_PORT,
            "key": str(store.get(_PLUGIN, "web_key") or "").strip(),
        }
    except Exception as e:  # noqa: BLE001 — 配置不可用走默认值
        logger.warning(f"[magpie] 读取 web 配置失败，按默认: {e}")
        return {"port": _DEFAULT_WEB_PORT, "key": ""}


_web_profile = None


def _get_web_profile():
    """独立命名的持久 Profile（延迟创建）。

    不复用主程序共享 profile：那是消息卡片在用，Cookie/缓存混用会互相污染；
    也不用默认 profile（改它的策略会影响整个应用）。
    """
    global _web_profile
    if _web_profile is not None:
        try:
            _web_profile.storageName()
            return _web_profile
        except RuntimeError:
            _web_profile = None

    from PyQt5.QtWebEngineWidgets import QWebEngineProfile

    profile = QWebEngineProfile(_PROFILE_NAME)
    profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
    profile.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
    profile.setHttpCacheMaximumSize(64 * 1024 * 1024)
    _web_profile = profile
    return profile


def _probe(port: int, timeout: float = 2.0) -> bool:
    """探测网页服务是否在监听（任意 HTTP 响应都算活着，401/403 也是活着）。"""
    import urllib.error
    import urllib.request

    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


class MagpieWebPage(QWidget):
    """magpie 网页界面（full 容器工作页）。"""

    _probe_done = pyqtSignal(bool)
    _start_done = pyqtSignal(bool, str)
    _link_probed = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._provider = None
        self._colors: dict = {}
        self._loaded_once = False
        # 引导面板当前展示的分支：""=未连接 / "load_failed"=被拒绝
        # （主题刷新时要按同一分支重渲染，否则文案被冲回「未连接」版）
        self._guide_state = ""
        # _show_guide 存下的 cfg 快照（主题刷新按它重渲染，不重读配置）
        self._guide_cfg: dict = None

        self._build_ui()
        self._probe_done.connect(self._on_probe_done)
        self._start_done.connect(self._on_start_done)
        self._link_probed.connect(self._on_link_probed)

    # ── 三约定接口 ────────────────────────────────────────

    def set_context_provider(self, provider):
        self._provider = provider

    def show_card(self):
        """页显示/激活入口（宿主唤出浮动卡时调用）：显示 + 取色 + 探测 + 加载。

        必须自管可见性：容器 add_card 时统一 setVisible(False) 藏卡，而
        CardManager 对实现了 show_card() 的卡只调本方法、不再代为 setVisible
        ——漏了这行卡永远 isHidden，容器判定无可见卡而折叠回对话区。
        （独立弹窗时代的 show_card 只做业务激活，可见性由弹窗壳负责。）
        """
        self.setVisible(True)
        self._apply_theme()
        self._connect_and_load()

    def refresh_theme(self):
        self._apply_theme()

    # ── 骨架 ─────────────────────────────────────────────

    def _build_ui(self):
        from qfluentwidgets import PushButton

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QWidget(self)
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(14, 8, 14, 8)
        bar_lay.setSpacing(10)

        self._status = QLabel("正在连接…", bar)
        bar_lay.addWidget(self._status, 1)

        self._reload_btn = PushButton("重新加载", bar)
        self._reload_btn.clicked.connect(self._connect_and_load)
        bar_lay.addWidget(self._reload_btn)

        self._browser_btn = PushButton("在浏览器打开", bar)
        self._browser_btn.clicked.connect(self._open_in_browser)
        bar_lay.addWidget(self._browser_btn)

        root.addWidget(bar)

        # 不可达时的指引面板（与 webview 互斥显示）
        self._guide = QWidget(self)
        guide_lay = QVBoxLayout(self._guide)
        guide_lay.setContentsMargins(24, 12, 24, 12)
        guide_lay.setSpacing(12)
        guide_lay.addStretch(1)

        self._guide_text = QLabel(self._guide)
        self._guide_text.setAlignment(Qt.AlignCenter)
        self._guide_text.setTextFormat(Qt.RichText)
        self._guide_text.setWordWrap(True)
        self._guide_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._guide_text.setText(self._guide_html("", ""))
        guide_lay.addWidget(self._guide_text)

        self._guide_btns = QWidget(self._guide)
        btn_lay = QHBoxLayout(self._guide_btns)
        btn_lay.setContentsMargins(0, 0, 0, 0)
        btn_lay.setSpacing(10)
        btn_lay.addStretch(1)

        self._launch_btn = PushButton("启动 magpie web", self._guide_btns)
        self._launch_btn.clicked.connect(self._launch_magpie)
        btn_lay.addWidget(self._launch_btn)

        self._copy_btn = PushButton("复制启动命令", self._guide_btns)
        self._copy_btn.clicked.connect(self._copy_command)
        btn_lay.addWidget(self._copy_btn)

        self._ask_btn = PushButton("让 AI 帮我装", self._guide_btns)
        self._ask_btn.clicked.connect(self._ask_ai_to_install)
        btn_lay.addWidget(self._ask_btn)

        # 让 magpie 认得 DriFox（登记 agent 条目；幂等，装没装 magpie 都能点）
        self._link_btn = PushButton("让 magpie 认得 DriFox", self._guide_btns)
        self._link_btn.clicked.connect(self._sync_agent_link)
        btn_lay.addWidget(self._link_btn)

        btn_lay.addStretch(1)
        guide_lay.addWidget(self._guide_btns)
        guide_lay.addStretch(1)
        root.addWidget(self._guide, 1)

        # ★ webview 懒构造：不在构造期创建 QWebEngineView。
        # 全卡场景下 webview 嵌在主窗 overlay 里，若构造期（服务未跑、页不可见）
        # 就存在 Chromium 原生窗口，process.start 首启确认框的模态遮罩盖住它
        # 重绘时 Qt 合成器会崩（dev 线崩 Qt5Gui / pyside6 线崩
        # Qt6WebEngineCore，2026-10-25 实测）；独立弹窗时代无此叠加不崩。
        # 改为探测到服务可用后才在 _ensure_webview 里创建。
        self._view = None
        self._page = None

    def _ensure_webview(self) -> None:
        """懒构造 QWebEngineView（探测到服务可用时调用）。

        构造失败（缺 QtWebEngine）降级为指引面板：禁「在浏览器打开」不可用，
        状态条提示无法内嵌。
        """
        if self._view is not None or self.layout() is None:
            return
        try:
            from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineView

            self._view = QWebEngineView(self)
            # PyQt5 的 QWebEngineView 没有 setProfile：profile 只能经 QWebEnginePage
            # 注入。page 必须由 Python 侧持有引用，否则被回收后 webview 变空白。
            self._page = QWebEnginePage(_get_web_profile(), self._view)
            self._view.setPage(self._page)
            self._view.loadFinished.connect(self._on_load_finished)
            self._view.setVisible(False)
            self.layout().addWidget(self._view, 1)
        except Exception as e:  # noqa: BLE001 — 缺 QtWebEngine 时降级
            logger.warning(f"[magpie] QWebEngineView 不可用，降级为指引面板: {e}")
            self._view = None
            self._browser_btn.setEnabled(False)

    # ── 连接与状态 ───────────────────────────────────────

    def _target_url(self) -> str:
        cfg = _read_config()
        url = f"http://127.0.0.1:{cfg['port']}/"
        if cfg["key"]:
            url += f"?k={cfg['key']}"
        return url

    def _connect_and_load(self):
        cfg = _read_config()
        self._status.setText(f"正在连接 127.0.0.1:{cfg['port']} …")
        self._reload_btn.setEnabled(False)

        def work():
            ok = _probe(cfg["port"])
            try:
                self._probe_done.emit(ok)
            except RuntimeError:
                pass  # 页面已销毁（窗口关闭）

        threading.Thread(target=work, daemon=True, name="magpie-web-probe").start()

    def _on_probe_done(self, ok: bool):
        self._reload_btn.setEnabled(True)
        cfg = _read_config()
        if not ok:
            self._status.setText("未连接")
            self._show_guide(cfg)
            return

        self._guide.setVisible(False)
        self._ensure_webview()
        if self._view is None:
            self._status.setText("已连接（缺 QtWebEngine，无法内嵌）")
            return

        self._view.setVisible(True)
        self._status.setText(self._connected_status(cfg["port"]))
        self._view.setUrl(QUrl(self._target_url()))
        self._loaded_once = True

    @staticmethod
    def _connected_status(port: int) -> str:
        """已连接状态条文案：顺带告诉用户 magpie 认不认得 DriFox。"""
        if _link_status():
            return f"已连接 127.0.0.1:{port} · DriFox 已登记"
        return f"已连接 127.0.0.1:{port} · 未登记 DriFox"

    def _on_load_finished(self, ok: bool):
        if ok:
            return
        # 服务在监听但页面拒绝访问：几乎总是 key 不对
        self._status.setText("页面加载失败（多为 web key 不匹配）")
        self._show_guide(_read_config(), load_failed=True)

    # ── 一键启动（经宿主 process.start 能力） ─────────────

    def _launch_magpie(self):
        """拉起 magpie web：登记 DriFox 识别 → 自动定 key → 启动 → 轮询端口 → 加载。

        登记先于启动：magpie 的 agent 条目是纯配置，不需要网关在跑；先登记好，
        拉起后到 Agents / Usage 页就能看到 DriFox。
        全程后台线程，按钮期间禁用防重复点；结果经 _start_done 回主线程。
        """
        cfg = _read_config()
        self._status.setText("正在启动 magpie web …")
        self._reload_btn.setEnabled(False)
        self._launch_btn.setEnabled(False)

        def work():
            ok, err = False, ""
            try:
                self._ensure_agent_link(log_only=True)
                start = _caps("process.start")
                if start is None:
                    err = "宿主未提供 process.start 能力（需 DriFox ≥ 0.6.11）"
                else:
                    key = _ensure_web_key(cfg)
                    start(_web_argv(cfg["port"]), env={"MAGPIE_WEB_KEY": key}, name="magpie-web")
                    ok = _wait_port(cfg["port"])
                    if not ok:
                        err = "已启动但端口未就绪（超时 12s），可稍后点「重新加载」重试"
            except FileNotFoundError:
                err = "找不到 magpie 可执行文件（PATH 上没有）"
            except Exception as e:  # noqa: BLE001 — 启动失败原因回显给用户
                err = str(e)
            try:
                self._start_done.emit(ok, err)
            except RuntimeError:
                pass  # 页面已销毁（窗口关闭）

        threading.Thread(target=work, daemon=True, name="magpie-web-launch").start()

    def _on_start_done(self, ok: bool, err: str):
        self._reload_btn.setEnabled(True)
        self._launch_btn.setEnabled(True)
        if ok:
            self._notify("magpie web 已启动", "用插件固定的 key，无需再手动设环境变量")
            self._on_probe_done(True)
            return
        self._status.setText("启动失败")
        self._notify("magpie web 启动失败", err)
        self._show_guide(_read_config())

    def _show_guide(self, cfg: dict, load_failed: bool = False):
        if self._view is not None:
            self._view.setVisible(False)
        self._guide.setVisible(True)
        self._guide_state = "load_failed" if load_failed else ""
        self._guide_cfg = dict(cfg or {})
        installed = _magpie_installed()
        self._guide_text.setText(
            self._guide_html(_start_command(cfg["port"]), cfg["key"], load_failed, installed)
        )
        # 按钮按分支显隐：未装→只留安装引导；key 不匹配→只留重启对齐
        self._copy_btn.setVisible(installed and not load_failed)
        self._launch_btn.setVisible(installed)
        # 识别按钮：已登记就只留「已认得」提示（无需再点），未登记时任意分支都可点
        linked = _link_status()
        self._link_btn.setVisible(not linked)
        self._link_btn.setText("让 magpie 认得 DriFox")
        self._apply_theme()

    def _open_in_browser(self):
        from PyQt5.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(self._target_url()))

    def _copy_command(self):
        cmd = _start_command(_read_config()["port"])
        from PyQt5.QtWidgets import QApplication

        QApplication.clipboard().setText(cmd)
        self._notify("已复制", cmd)

    def _ensure_agent_link(self, log_only: bool = False):
        """把 DriFox 的 agent 条目登记进 magpie（幂等）。

        走注册表文件而非 ``magpie plugin add``：后者在无 Bun 的环境会去下载 Bun
        并长时间卡住（实测 180s 无返回）。agent 插件本身不需要 Bun。

        log_only=True 用于启动流程（不弹窗打扰，失败只记日志 + 回状态条）；
        False 用于用户主动点按钮（结果要明确告知）。
        """
        try:
            from . import agent_link

            state, info = agent_link.ensure_registered()
        except Exception as e:  # noqa: BLE001 — 登记失败不该阻断启动
            logger.warning(f"[magpie] 登记 DriFox agent 条目失败: {e}")
            if not log_only:
                self._notify("登记失败", str(e))
            return False

        if state == "error":
            logger.warning(f"[magpie] 登记 DriFox agent 条目失败: {info}")
            if not log_only:
                self._notify("登记失败", info)
            return False
        if state == "already":
            logger.debug("[magpie] DriFox agent 条目已登记，跳过")
        else:
            logger.info(f"[magpie] 已登记 DriFox agent 条目: {info}")
        return True

    def _sync_agent_link(self):
        """用户主动同步：登记 + 探测 magpie 是否真的认得（两级状态）。

        探测要起 `magpie <id>` 子进程（冷启动可能几秒），放后台线程跑，别冻 UI。
        """
        from PyQt5.QtWidgets import QApplication

        self._link_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if not self._ensure_agent_link():
                return
        finally:
            QApplication.restoreOverrideCursor()
            self._link_btn.setEnabled(True)

        self._status.setText("正在确认 magpie 是否认得 DriFox …")

        def work():
            try:
                from . import agent_link

                active, detail = agent_link.probe_agent_active()
            except Exception as e:  # noqa: BLE001 — 探测失败按未生效处理
                active, detail = False, str(e)
            try:
                self._link_probed.emit(active, detail)
            except RuntimeError:
                pass  # 页面已销毁（窗口关闭）

        threading.Thread(target=work, daemon=True, name="magpie-agent-probe").start()

    def _on_link_probed(self, active: bool, detail: str):
        self._link_btn.setEnabled(True)
        if active:
            self._status.setText(self._connected_status(_read_config()["port"]) if self._view else "DriFox 已登记")
            self._notify("magpie 已认得 DriFox", f"{detail}（Agents / Usage 页可见）")
            self._link_btn.setVisible(False)
            return
        self._status.setText("已登记，magpie 未确认")
        if not _magpie_installed():
            self._notify("已登记，magpie 未安装", "装好 magpie 后重新打开这一页即可生效")
        else:
            self._notify("已登记但 magpie 未加载", f"magpie 返回：{detail}")

    def _ask_ai_to_install(self):
        """把安装/启动指令写进输入框，交给对话里的模型去执行。

        用 input.write 而非自己 subprocess：装软件涉及下载、PATH、权限与平台
        差异，交给模型按当前环境处理比插件硬编码更稳；插件只负责把意图摆到
        用户眼前。

        写提示词前先把 DriFox 的 agent 条目登记进 magpie 注册表：登记只写
        配置文件，不依赖 magpie 是否已装，所以装好后第一次启动就认得 DriFox
        （开箱即用）。登记失败不影响提示词（模型装完照样能用，用户可再点按钮）。
        """
        write = _caps("input.write")

        if write is None:
            self._notify("无法写入输入框", "当前宿主未提供 input.write 能力，请手动安装 magpie")
            return

        linked = self._ensure_agent_link(log_only=True)
        prompt = (
            "请帮我安装 magpie（https://github.com/yetone/magpie），安装好后启动它的网页服务，"
            "让 127.0.0.1:3430 能访问，然后告诉我一声。当前平台是 "
            f"{'Windows' if os.name == 'nt' else 'macOS/Linux'}。"
        )
        if linked:
            prompt += (
                "\n\n装好后不用管 DriFox 的识别：插件已经把 DriFox 的 agent 条目登记进 magpie，"
                "你只要确认 magpie 能正常启动即可。"
            )
        try:
            write(prompt, append=False, focus=True)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[magpie] 写入输入框失败: {e}")
            self._notify("写入失败", str(e))
            return
        self._notify("已填入输入框", "发送后模型会按你的环境装 magpie（可能需要下载与权限确认）")

    def _notify(self, title: str, content: str):
        """提示优先走 ui.notify 能力，拿不到就只记日志（不依赖页内 InfoBar parent）。"""
        notify = _caps("ui.notify")
        if notify is not None:
            try:
                notify(title, content)
                return
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[magpie] notify 失败: {e}")
        logger.info(f"[magpie] {title}: {content}")

    # ── 主题 ─────────────────────────────────────────────

    def _ctx_colors(self) -> dict:
        from qfluentwidgets import isDarkTheme

        ctx = self._provider() if callable(self._provider) else {}
        colors = (ctx or {}).get("colors", {}) or {}
        dark = isDarkTheme()
        return {
            "text_primary": colors.get("text_primary")
            or ("rgba(255,255,255,0.9)" if dark else "rgba(0,0,0,0.85)"),
            "text_secondary": colors.get("text_secondary")
            or ("rgba(255,255,255,0.55)" if dark else "rgba(0,0,0,0.45)"),
            "border": colors.get("border") or ("rgba(255,255,255,0.12)" if dark else "rgba(0,0,0,0.12)"),
        }

    def _apply_theme(self):
        self._colors = self._ctx_colors()
        c = self._colors
        self._status.setStyleSheet(f"color: {c['text_primary']};")
        self._guide_text.setStyleSheet(f"color: {c['text_secondary']};")
        # 用 isHidden() 而非 isVisible()：窗口尚未显示时父级不可见会让
        # isVisible() 恒为 False，导致主题切换时引导文案不重刷
        # 引导文案按 _show_guide 存下的 cfg 重渲染（不重新读配置：读到的端口
        # 可能已变，会把刚展示的分支文案冲成另一个端口的版本）
        if not self._guide.isHidden() and self._guide_cfg is not None:
            self._guide_text.setText(
                self._guide_html(
                    _start_command(self._guide_cfg["port"]),
                    self._guide_cfg["key"],
                    self._guide_state == "load_failed",
                    _magpie_installed(),
                )
            )

    # ── 文案 ─────────────────────────────────────────────

    def _guide_html(self, command: str, key: str, load_failed: bool = False, installed: bool = True) -> str:
        c = self._colors or self._ctx_colors()
        body_lines = []
        if load_failed:
            head = "magpie 拒绝了这次访问"
            body_lines.append(
                "运行中的 magpie web 用的是另一次启动时随机生成的 key。"
                "先退出现有的 magpie 进程，再点下面的「启动 magpie web」："
                "插件会用自己固定的 key 重新拉起，之后不再变。"
            )
            body_lines.append(
                "也可以在插件设置里把 Web Key 改成当前实例的值（当前实例若是"
                "手动启动且没设 <code>MAGPIE_WEB_KEY</code>，那个 key 每次都会变）。"
            )
        elif installed:
            head = "magpie 网页服务没有在监听"
            body_lines.append(
                "magpie 已安装。点下面的「启动 magpie web」直接拉起：插件会"
                "自动固定 key 并在就绪后自动加载，无需终端。也可以复制命令"
                "自己启动："
            )
            body_lines.append(
                "<code style=\"padding:2px 6px;border-radius:4px;"
                f"border:1px solid {c['border']}\">{command}</code>"
            )
            if not key:
                body_lines.append(
                    "另外：可以设 <code>MAGPIE_WEB_KEY</code> 固定 key，并填进插件设置。"
                )
        else:
            head = "没有找到 magpie"
            body_lines.append(
                "PATH 上没有 <code>magpie</code> 可执行文件。点下面的按钮把安装指令"
                "填进输入框，让对话里的模型按你的环境装（Windows / macOS / Linux 装法不同）。"
            )
            body_lines.append(
                '也可以自己去 <a href="https://usemagpie.ai">usemagpie.ai</a> 下载。'
            )
        body = "<br><br>".join(body_lines)
        return (
            f"<div style=\"font-size:15px;color:{c['text_primary']};margin-bottom:8px\">{head}</div>"
            f"<div>{body}</div>"
        )


def _start_command(port: int) -> str:
    """按端口给出可复制的启动命令（3430 是默认端口，其他端口需显式 --addr）。"""
    if port == _DEFAULT_WEB_PORT:
        return "magpie web --no-open"
    return f"magpie web --addr 127.0.0.1:{port} --no-open"
