"""Git 面板固定输入的渲染基准；修改前后使用同一命令比较。"""
import importlib.util
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ui = Path(__file__).resolve().parents[1] / "ui"
spec = importlib.util.spec_from_file_location("ui_plugin_git_panel", ui / "__init__.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
from PyQt5.QtCore import QCoreApplication, QEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication, QWidget  # noqa: E402
from ui_plugin_git_panel.cards import GitPanelCard  # noqa: E402

app = QApplication.instance() or QApplication([])


def payload(count, seed=0):
    return {"branch": "main", "ahead": 0, "behind": 0, "status": [
        {"path": f"src/group{(i + seed) % 20}/file{i}.py", "status": "M", "staged": i % 3 == 0}
        for i in range(count)
    ], "stashes": [], "branches": [], "log": []}


# 预热：首帧字体与样式表初始化不计入被测数据
warm = GitPanelCard()
warm._render_content(payload(30))
app.processEvents()

results = {}
for count in (100, 1000):
    panel = GitPanelCard()
    panel.resize(320, 800)
    first = time.perf_counter()
    panel._render_content(payload(count))
    app.processEvents()
    first_ms = (time.perf_counter() - first) * 1000
    times = []
    for _ in range(5):
        start = time.perf_counter()
        panel._render_content(payload(count))
        app.processEvents()
        times.append((time.perf_counter() - start) * 1000)
    changed = []
    for seed in range(1, 3):
        start = time.perf_counter()
        panel._render_content(payload(count, seed=seed))
        app.processEvents()
        changed.append((time.perf_counter() - start) * 1000)
    results[str(count)] = {
        "first_ms": round(first_ms, 2),
        "unchanged_median_ms": round(statistics.median(times), 3),
        "one_file_changed_median_ms": round(statistics.median(changed), 2),
        "widgets": len(panel.findChildren(QWidget)),
    }
    panel.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
print(json.dumps(results, ensure_ascii=False))
