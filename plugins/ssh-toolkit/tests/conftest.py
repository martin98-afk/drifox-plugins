import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "deps"))
import _store as store  # noqa: E402
import _pool as pool  # noqa: E402
import _auth as auth  # noqa: E402
# 注册别名，使测试内 `import ssh_toolkit_xxx as X` 命中已加载模块
sys.modules["ssh_toolkit_store"] = store
sys.modules["ssh_toolkit_pool"] = pool
sys.modules["ssh_toolkit_auth"] = auth
