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

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from loguru import logger

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor" / "proxypool"
_PROXY_MAIN = _VENDOR_DIR / "main.py"


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
        # 工作目录：存 socks.txt / alive.txt / config.json（默认 user-custom/ip-switcher/data）
        self.data_dir = data_dir or (
            Path(".drifox") / "plugins" / "user-custom" / "ip-switcher" / "data"
        )
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()
        self._base_url = f"http://127.0.0.1:{stats_port}"

    # ── 子进程生命周期 ──

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, fetch_and_check: bool = True, wait_ready: float = 8.0) -> bool:
        """启动代理池子进程。fetch_and_check=True 时先抓取+检测代理。"""
        with self._lock:
            if self.is_running():
                return True
            self.data_dir.mkdir(parents=True, exist_ok=True)
            try:
                if fetch_and_check:
                    # run = fetch → check → serve（一键全流程）
                    cmd = [
                        sys.executable,
                        str(_PROXY_MAIN),
                        "run",
                        "--port",
                        str(self.proxy_port),
                        "--stats-port",
                        str(self.stats_port),
                    ]
                else:
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
                )
                logger.info(
                    f"[ip-switcher] 代理池已启动 (pid={self._proc.pid}, port={self.proxy_port})"
                )
            except Exception as e:
                logger.error(f"[ip-switcher] 代理池启动失败: {e}")
                self._proc = None
                return False
        # 等待控制台就绪
        deadline = time.time() + wait_ready
        while time.time() < deadline:
            if self._request("GET", "/stats") is not None:
                return True
            time.sleep(0.5)
        logger.warning("[ip-switcher] 代理池控制台未就绪（可能仍在抓取/检测）")
        return True  # 进程在跑，只是没就绪；后续调用会重试

    def stop(self) -> None:
        """停止代理池子进程"""
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
        logger.info("[ip-switcher] 代理池已停止")

    # ── HTTP 控制 API ──

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        timeout: float = 6.0,
    ):
        """请求代理池控制台 API，失败返回 None"""
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

    def get_outbound_ip(self, timeout: float = 8.0) -> Optional[str]:
        """通过代理请求 ipify 拿出口 IP（验证代理连通性）"""
        try:
            proxies = {
                "http://": f"http://127.0.0.1:{self.proxy_port}",
                "https://": f"http://127.0.0.1:{self.proxy_port}",
            }
            r = httpx.get("https://api.ipify.org", proxies=proxies, timeout=timeout)
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
