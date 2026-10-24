import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
# deps 按平台分目录：原生扩展在 deps/<platform>/（注入优先于公共 deps/）。
# 顺序即 sys.path 优先级：当前平台目录 > 公共 deps/ > 其他平台兜底。
# sys.platform: darwin(macOS) / win32(Windows) / linux
_curr = {"darwin": "darwin", "win32": "win32", "linux": "linux"}.get(sys.platform, sys.platform)
for _plat in (_curr, ""):
    _d = os.path.join(os.path.dirname(__file__), "..", "deps", _plat)
    if os.path.isdir(_d):
        sys.path.insert(0, _d)
import _store as store  # noqa: E402
import _pool as pool  # noqa: E402
import _auth as auth  # noqa: E402
import _guard as guard  # noqa: E402
# 注册别名，使测试内 `import ssh_toolkit_xxx as X` 命中已加载模块
sys.modules["ssh_toolkit_store"] = store
sys.modules["ssh_toolkit_pool"] = pool
sys.modules["ssh_toolkit_auth"] = auth
sys.modules["ssh_toolkit_guard"] = guard
