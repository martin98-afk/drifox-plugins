# -*- coding: utf-8 -*-
"""ip-switcher 代理池管理 — shadow1ng/ProxyPool 子进程 + HTTP 控制

子进程：python <vendor>/main.py serve --port 8082（控制台 8083）
控制 API（ProxyPool web/index.html 前端调用清单）：
- POST /rotate  {"mode": "sticky"}  → 换 IP
- POST /mode    {"mode": "auto|sticky|manual"}
- GET  /stats   → {current, pool_size, alive_total, ...}
- POST /fetch   → 抓取代理
- POST /check   → 检测存活
- GET  /reset   → 重置熔断
"""

import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from loguru import logger

from config import get_data_dir

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor" / "proxypool"
_PYSOCKS_DIR = Path(__file__).resolve().parent / "_vendor" / "pysocks"
_PROXY_MAIN = _VENDOR_DIR / "main.py"


def _probe_port(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    """探测端口是否已被占用（有进程监听）"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _build_subprocess_env() -> Dict[str, str]:
    """构建子进程环境：注入当前 venv site-packages + _vendor/pysocks

    ⚠️ uv shim 的 sys.executable 在 subprocess 中会解析成裸 Python
    （不带 venv 的 site-packages），导致 requests/PySocks 不可用。
    必须显式通过 PYTHONPATH 注入，否则 ProxyPool 的 fetch/check 全失败。
    """
    env = dict(os.environ)
    parts: list[str] = []
    # 1) 当前进程的 site-packages（requests 等）
    for p in sys.path:
        if "site-packages" in p and p not in parts:
            parts.append(p)
    # 2) vendor 的 PySocks（import socks 需要）
    parts.append(str(_PYSOCKS_DIR))
    old = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(parts) + (os.pathsep + old if old else "")
    return env


class ProxyPoolManager:
    """代理池子进程生命周期 + 控制 API 客户端"""

    def __init__(
        self,
        stats_port: int = 8083,
        proxy_port: int = 8082,
        data_dir: Optional[Path] = None,
    ):
        self.stats_port = stats_port
        self.proxy_port = proxy_port
        # 工作目录：存 socks.txt / alive.txt / config.json（默认插件自身数据目录
        # <root>/plugins/ip-switcher/data，与配置同目录，不走 user-custom）
        self.data_dir = data_dir or get_data_dir()
        self._proc: Optional[subprocess.Popen] = None
        # 独立运行标志：复用分支（端口被占用）时 _proc=None 但代理池确实在跑，
        # is_running() 必须返回 True，否则 UI 无法显示「停止代理」/启用换 IP。
        self._running: bool = False
        # is_running 结果短缓存（复用分支走端口探测 0.5s，高频调用防卡主线程）
        self._running_cache: Optional[tuple] = None  # (timestamp, bool)
        self._lock = threading.RLock()
        self._base_url = f"http://127.0.0.1:{stats_port}"

    # ── 子进程生命周期 ──

    def is_running(self, cache_seconds: float = 1.0) -> bool:
        # 自己启动的进程存活 → True（O(1)，无需缓存）
        if self._proc is not None and self._proc.poll() is None:
            return True
        # 复用分支（_proc=None）或进程被其他实例停止：端口实测 + 短缓存
        now = time.time()
        if self._running_cache is not None and now - self._running_cache[0] < cache_seconds:
            return self._running_cache[1]
        val = self._running and _probe_port(self.stats_port)
        self._running_cache = (now, val)
        return val

    # ── PID 文件跟踪（热重载/复用分支也能定位并杀旧进程） ──

    def _pid_file(self) -> Path:
        return self.data_dir / "proxy_pool.pid"

    def _write_pid_file(self, pid: int) -> None:
        """把代理池子进程 PID 写入数据目录（供热重载/异常残留后清理）"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self._pid_file().write_text(str(pid), encoding="utf-8")
        except OSError as e:
            logger.warning(f"[ip-switcher] PID 文件写入失败: {e}")

    def _read_pid_file(self) -> Optional[int]:
        """读取 PID 文件，返回 PID 或 None"""
        try:
            p = self._pid_file()
            if p.exists():
                return int(p.read_text(encoding="utf-8").strip())
        except Exception:
            pass
        return None

    def _delete_pid_file(self) -> None:
        try:
            p = self._pid_file()
            if p.exists():
                p.unlink()
        except OSError:
            pass

    def _kill_pid(self, pid: int) -> bool:
        """按 PID 终止进程（psutil 校验命令行防误杀）

        校验条件（任一命中即视为代理池进程）：
        1. 命令行含 "proxypool"（vendor 路径或关键词）
        2. 含 "main.py" 且带 serve/run 子命令（开发/测试直跑场景）
        """
        try:
            import psutil

            proc = psutil.Process(pid)
            cmdline = " ".join(proc.cmdline()) or ""
            is_pool = "proxypool" in cmdline or (
                "main.py" in cmdline and ("serve" in cmdline or "run" in cmdline)
            )
            if not is_pool:
                logger.warning(
                    f"[ip-switcher] PID {pid} 非 proxypool 进程，跳过（防误杀）"
                )
                return False
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
            logger.info(f"[ip-switcher] 已终止残留代理池进程 PID={pid}")
            return True
        except psutil.NoSuchProcess:
            return False  # 进程已不存在，视为清理成功
        except Exception as e:
            logger.warning(f"[ip-switcher] PID {pid} 终止失败: {e}")
            return False

    def start(self, fetch_and_check: bool = True, wait_ready: float = 8.0) -> bool:
        """启动代理池子进程。

        策略（避免 run 模式 fetch/check 阻塞控制台）：
        1. 先探测 stats_port：已占用 → 复用现有实例（防热重载重复启动）
        2. 否则直接 serve（几秒内控制台就绪）
        3. 再通过控制 API 后台触发 fetch + check（不阻塞）
        """
        # 防重复启动：端口已被占用 → 视为已有实例在跑，直接复用
        # （热重载后模块级单例失效，不能依赖内存状态判断）
        if _probe_port(self.stats_port):
            logger.info(
                f"[ip-switcher] 控制台端口 {self.stats_port} 已占用，复用现有代理池"
            )
            # 复用时不持有 _proc（不杀别人的），
            # 但保留 PID 文件以便本实例 stop() 时可定位并清理旧进程
            pid = self._read_pid_file()
            self._proc = None
            self._running = True
            self._running_cache = None  # 清缓存：状态已变，防旧 False 误报
            if pid and self._is_pid_alive(pid):
                logger.info(f"[ip-switcher] 接管现有代理池 PID={pid}")
            return True
        with self._lock:
            if self.is_running():
                return True
            self.data_dir.mkdir(parents=True, exist_ok=True)
            try:
                # 直接 serve（控制台秒级就绪），fetch/check 后续异步触发
                cmd = [
                    sys.executable,
                    str(_PROXY_MAIN),
                    "serve",
                    "--port",
                    str(self.proxy_port),
                    "--stats-port",
                    str(self.stats_port),
                ]
                self._proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.data_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    env=_build_subprocess_env(),
                )
                self._write_pid_file(self._proc.pid)
                self._running = True
                self._running_cache = None  # 清缓存
                logger.info(
                    f"[ip-switcher] 代理池已启动 (pid={self._proc.pid}, port={self.proxy_port})"
                )
            except Exception as e:
                logger.error(f"[ip-switcher] 代理池启动失败: {e}")
                self._proc = None
                self._running = False
                return False
        # 等待控制台就绪
        deadline = time.time() + wait_ready
        while time.time() < deadline:
            if self._request("GET", "/stats") is not None:
                # 后台异步触发抓取 + 检测（不阻塞，ProxyPool 支持后台任务）
                if fetch_and_check:
                    self._trigger_fetch_check_async()
                return True
            time.sleep(0.5)
        logger.warning("[ip-switcher] 代理池控制台未就绪")
        return False

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """进程是否存活"""
        try:
            import psutil

            return psutil.pid_exists(pid)
        except Exception:
            return False

    def _trigger_fetch_check_async(self) -> None:
        """后台线程触发 fetch + check（不阻塞启动流程）"""

        def _run():
            try:
                self.fetch_proxies()
                self.check_proxies()
            except Exception as e:
                logger.warning(f"[ip-switcher] 后台抓取/检测触发失败: {e}")

        threading.Thread(target=_run, daemon=True).start()

    def stop(self) -> None:
        """停止代理池子进程（双重兜底）

        1. 优先按 self._proc 终止（本实例启动的进程）
        2. 无论 _proc 是否为 None，都通过 PID 文件定位并清理残留进程
           （覆盖热重载后新实例 _proc=None 但旧进程仍存活的场景）
        """
        with self._lock:
            if self._proc is not None:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=5)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                self._proc = None
        self._running = False
        self._running_cache = None
        # PID 文件兜底清理（复用分支 _proc=None 时依然能杀旧进程；主程序退出时同样生效）
        pid = self._read_pid_file()
        if pid:
            self._kill_pid(pid)
            self._delete_pid_file()
        logger.info("[ip-switcher] 代理池已停止")

    # ── HTTP 控制 API ──

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        timeout: float = 3.0,
    ):
        """请求代理池控制台 API，失败返回 None

        超时 3s：本地控制台请求毫秒级，缩短超时避免 UI 刷新（get_stats）
        在控制台异常时卡顿过久。
        """
        try:
            if method == "GET":
                r = httpx.get(self._base_url + path, timeout=timeout)
            else:
                r = httpx.post(self._base_url + path, json=body or {}, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            logger.debug(f"[ip-switcher] 控制 API {path} 请求失败: {e}")
        return None

    def get_stats(self) -> Optional[Dict[str, Any]]:
        """获取代理池状态（当前 IP、池大小等）"""
        return self._request("GET", "/stats")

    def set_mode(self, mode: str) -> bool:
        """切换模式：auto / sticky / manual"""
        d = self._request("POST", "/mode", {"mode": mode})
        return d is not None and not d.get("error")

    def rotate(self) -> Optional[str]:
        """手动/触发换 IP：调用 /rotate，返回新代理 ip:port 或 None"""
        d = self._request("POST", "/rotate", {})
        if d is None or d.get("error"):
            return None
        return d.get("current")

    def ensure_sticky_ip(self) -> Optional[str]:
        """确保 sticky 模式已有 current IP；无则主动 rotate 一次

        代理池刚启动时 mode=auto 且 current=null（尚未选择出口代理），
        此时直接显示「未使用」会让用户误以为换绑没生效。启动流程在
        set_mode("sticky") 后调用本方法，让 current 立即有值。
        """
        stats = self.get_stats() or {}
        cur = stats.get("current")
        if cur:
            return cur
        return self.rotate()

    def fetch_proxies(self) -> bool:
        """触发抓取代理（后台任务）"""
        d = self._request("POST", "/fetch", {})
        return d is not None and not d.get("error")

    def check_proxies(self) -> bool:
        """触发检测存活（后台任务）"""
        d = self._request("POST", "/check", {})
        return d is not None and not d.get("error")

    def reset_circuits(self) -> bool:
        """重置熔断"""
        try:
            r = httpx.get(self._base_url + "/reset", timeout=6.0)
            return r.status_code == 200
        except Exception:
            return False

    # ── 出口 IP 验证 ──

    def get_outbound_ip(self, timeout: float = 3.0) -> Optional[str]:
        """通过代理请求 ipify 拿出口 IP（验证代理连通性）

        ⚠️ 免费代理转发 https 常报 CERTIFICATE_VERIFY_FAILED（代理做 MITM），
        因此用 http 端点 + verify=False，避免误判代理不可用。
        超时 3s：换 IP 在后台线程执行，但需尽快返回（验证失败时用代理 host 兜底）。
        """
        proxy_url = f"http://127.0.0.1:{self.proxy_port}"
        try:
            r = httpx.get(
                "http://api.ipify.org",
                proxy=proxy_url,
                timeout=timeout,
                verify=False,
            )
            if r.status_code == 200:
                ip = r.text.strip()
                return ip if ip else None
        except Exception as e:
            logger.debug(f"[ip-switcher] 出口 IP 验证失败: {e}")
        return None


# 模块级单例
_manager: Optional[ProxyPoolManager] = None


def get_manager() -> ProxyPoolManager:
    global _manager
    if _manager is None:
        _manager = ProxyPoolManager()
    return _manager


def reset_manager_for_test(manager: ProxyPoolManager) -> None:
    global _manager
    _manager = manager
