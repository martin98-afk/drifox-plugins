# -*- coding: utf-8 -*-
"""WebDAV 客户端（纯 urllib，兼容坚果云 / Nextcloud）

仅实现备份所需子集：PROPFIND（列目录）/ MKCOL（建目录）/ PUT / GET / DELETE。
Basic Auth；坚果云需使用「应用密码」；注意坚果云免费版有请求频率限制。
"""
from __future__ import annotations

import base64
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

_DAV_NS = "{DAV:}"
_TIMEOUT = 30


class WebDAVError(Exception):
    """WebDAV 操作失败（带 HTTP 状态码）"""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class WebDAVClient:
    def __init__(self, base_url: str, username: str, password: str, timeout: int = _TIMEOUT):
        base_url = (base_url or "").strip()
        if not re.match(r"^https?://", base_url):
            raise WebDAVError(f"服务器地址必须以 http(s):// 开头，当前: {base_url!r}")
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        self._auth_header = f"Basic {token}"

    # ── 底层请求 ────────────────────────────────────────

    def _url(self, path: str) -> str:
        """base_url + 编码后的相对路径（path 以 / 开头或为空均可）"""
        rel = (path or "").lstrip("/")
        # 逐段 percent-encode，保留斜杠
        encoded = "/".join(quote(seg, safe="") for seg in rel.split("/") if seg != "")
        return self.base_url + encoded

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> tuple:
        url = self._url(path)
        req = Request(url, data=body, method=method)
        req.add_header("Authorization", self._auth_header)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read()
        except HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            raise WebDAVError(f"HTTP {e.code} {method} {urlsplit(url).path}: {detail or e.reason}", status=e.code) from e
        except URLError as e:
            raise WebDAVError(f"网络错误 {method} {urlsplit(url).path}: {e.reason}") from e
        except OSError as e:
            raise WebDAVError(f"连接失败 {method} {urlsplit(url).path}: {e}") from e

    # ── WebDAV 方法 ─────────────────────────────────────

    def test(self) -> Dict[str, Any]:
        """PROPFIND Depth 0 探活，返回服务器摘要"""
        status, _ = self._request(
            "PROPFIND", "", _PROPFIND_BODY, {"Depth": "0", "Content-Type": "application/xml"}
        )
        host = urlsplit(self.base_url).hostname or ""
        return {"ok": True, "status": status, "host": host}

    def mkdirs(self, path: str) -> None:
        """逐级 MKCOL 建目录；405（已存在）与 301 视为成功"""
        parts = [p for p in path.strip("/").split("/") if p]
        cur = ""
        for seg in parts:
            cur += "/" + seg
            try:
                self._request("MKCOL", cur)
            except WebDAVError as e:
                if e.status not in (301, 405, 409):
                    raise

    def put(self, path: str, data: bytes) -> None:
        self._request("PUT", path, data, {"Content-Type": "application/octet-stream"})

    def get(self, path: str) -> bytes:
        _, body = self._request("GET", path)
        return body

    def delete(self, path: str) -> None:
        self._request("DELETE", path)

    def list_dir(self, path: str) -> List[Dict[str, Any]]:
        """PROPFIND Depth 1，返回子项列表（不含自身）；目录不存在返回空表"""
        try:
            status, body = self._request(
                "PROPFIND", path, _PROPFIND_BODY, {"Depth": "1", "Content-Type": "application/xml"}
            )
        except WebDAVError as e:
            if e.status == 404:
                return []
            raise
        if status not in (207, 200):
            raise WebDAVError(f"PROPFIND 意外状态码 {status}", status=status)
        # href 是服务器绝对路径（含 base_url 的 path 前缀，如 /dav/...），须同源推导后比较
        from urllib.parse import unquote, urlsplit

        server_dir = unquote(urlsplit(self._url(path)).path)
        return _parse_propfind(body, parent_path=server_dir)


_PROPFIND_BODY = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:"><d:prop>'
    "<d:resourcetype/><d:getcontentlength/><d:getlastmodified/><d:displayname/>"
    "</d:prop></d:propfind>"
).encode("utf-8")


def _parse_propfind(xml_body: bytes, parent_path: str) -> List[Dict[str, Any]]:
    """解析 multistatus；parent_path 为该目录的服务器绝对路径（如 /dav/drifox-backup），
    用于排除自身；子项路径一律按服务器 href 解析"""
    from urllib.parse import unquote

    parent = PurePosixPath("/" + (parent_path or "/").strip("/"))
    items: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_body)
    except ET.ParseError as e:
        raise WebDAVError(f"PROPFIND 响应解析失败: {e}") from e
    for resp in root.iter(f"{_DAV_NS}response"):
        href_el = resp.find(f"{_DAV_NS}href")
        href = (href_el.text or "") if href_el is not None else ""
        # href 可能带 percent-encoding
        href = unquote(href)
        p = PurePosixPath(href)
        if p == parent or str(p) == str(parent):
            continue
        is_dir = resp.find(f"{_DAV_NS}propstat/{_DAV_NS}prop/{_DAV_NS}resourcetype/{_DAV_NS}collection") is not None
        prop = resp.find(f"{_DAV_NS}propstat/{_DAV_NS}prop")
        size = 0
        modified: Optional[datetime] = None
        if prop is not None:
            len_el = prop.find(f"{_DAV_NS}getcontentlength")
            if len_el is not None and len_el.text and len_el.text.isdigit():
                size = int(len_el.text)
            mod_el = prop.find(f"{_DAV_NS}getlastmodified")
            if mod_el is not None and mod_el.text:
                try:
                    modified = parsedate_to_datetime(mod_el.text)
                except (TypeError, ValueError):
                    pass
        name = p.name or href.rstrip("/").rsplit("/", 1)[-1]
        items.append(
            {
                "name": name,
                "is_dir": is_dir,
                "size": size,
                "modified": modified,
            }
        )
    return items
