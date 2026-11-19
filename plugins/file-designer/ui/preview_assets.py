# -*- coding: utf-8 -*-
"""预览图片资产落盘：内联 data URI → 语义命名的本地文件。

Chromium（WebEngine 83）拖拽 data: URI 图片出门时忽略任何文件名提示，统一
命名 download.png（见 crbug 40556755：data scheme 只按 download.<ext> 落盘），
同页多张图片拖进输入框后全部同名、互相覆盖。换成 file:// 资源后拖出的就是
真实文件名，因此打开文档时把 HTML 里的 base64 图片写成
preview_assets/<文档名>_<序号>.<ext>，页面改用相对路径引用。
"""

import base64
import re
import shutil
from pathlib import Path

# base64 字符集不含引号，正则不会跨出属性边界
_DATA_IMG_RE = re.compile(r"data:image/([A-Za-z0-9.+-]+);base64,([A-Za-z0-9+/=]+)")

_MIME_EXT = {
    "png": "png",
    "jpeg": "jpg",
    "jpg": "jpg",
    "gif": "gif",
    "bmp": "bmp",
    "webp": "webp",
    "svg+xml": "svg",
    "x-icon": "ico",
    "vnd.microsoft.icon": "ico",
}


def _safe_stem(stem):
    """文档名 → 可用作文件名的片段（去掉 Windows 非法字符与空白）。"""
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", stem or "").strip("._")
    return s[:40] or "preview"


class PreviewAssets:
    """一次打开会话的图片资产目录。同一张图（base64 相同）复用同一文件。"""

    def __init__(self, root, stem):
        self.dir = Path(root) / "preview_assets"
        self.stem = _safe_stem(stem)
        self._cache = {}
        self._seq = 0
        self.reset()

    def reset(self):
        """清空资产目录：上一次打开的文档文件不再被 HTML 引用。"""
        shutil.rmtree(str(self.dir), ignore_errors=True)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._cache.clear()
        self._seq = 0

    def rewrite_html(self, html):
        """把 HTML 里的 data:image 内联资源改写为相对路径。

        返回 (新 HTML, 是否发生了改写)。改写后页面必须走 file:// 加载：
        setHtml 的 http baseUrl 下 file 子资源会被 Chromium 拦掉。
        """
        if not html or "data:image/" not in html:
            return html, False
        changed = False

        def _sub(m):
            nonlocal changed
            payload = m.group(2)
            url = self._cache.get(payload)
            if url is None:
                self._seq += 1
                ext = _MIME_EXT.get(m.group(1).lower(), "png")
                name = "%s_%02d.%s" % (self.stem, self._seq, ext)
                try:
                    (self.dir / name).write_bytes(base64.b64decode(payload))
                except Exception:
                    # 坏数据原样保留，退回 data URI 显示
                    return m.group(0)
                url = "preview_assets/" + name
                self._cache[payload] = url
            changed = True
            return url

        return _DATA_IMG_RE.sub(_sub, html), changed
