"""离屏连拍收起/展开两态，用于对照效果稿；不调用模型。"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication

from ui.panel import Panel

OUT = Path(__file__).resolve().parent / "shots"
DEMO = [
    ("帮我把会议纪要浓缩成三点。", "1. 周五前确认交付范围。\n2. 设计稿先走一轮内部评审。\n3. 测试排期等接口定稿后再排。"),
]
LONG = (
    "解释一下这场雨。",
    "雨是从云里落下来的水。\n\n空气上升时冷却，水汽凝成小滴，小滴不断碰撞变大，"
    "重到上升气流托不住时就落下。落下的过程里有的又被蒸发，所以雨量看的是"
    "落到地面这一层，而不是云里生成了多少。\n\n雨的味道来自三处：雨前干旱期"
    "土壤细菌分泌的土臭素、植物在干燥时释放的油脂、以及雨滴撞碎时带起的"
    "气溶胶。你闻到的那股第一滴雨的味道，多半是土臭素。",
)


def shot(panel, name):
    panel.show()
    QApplication.processEvents()
    pix = panel.grab()
    canvas = QPixmap(pix.width() + 48, pix.height() + 48)
    canvas.fill(QColor("#dfe8ec"))
    painter = QPainter(canvas)
    painter.drawPixmap(24, 24, pix)
    painter.end()
    canvas.save(str(OUT / f"{name}.png"))
    reply = panel.reply
    print(
        name,
        "窗口", panel.width(), panel.height(),
        "卡片", panel.card.height(), "回复区", reply.height(),
        "横向溢出", reply.horizontalScrollBar().maximum(),
        "纵向范围", reply.verticalScrollBar().maximum(),
        flush=True,
    )


def main():
    OUT.mkdir(exist_ok=True)
    app = QApplication([])
    panel = Panel(lambda: None, dark=True)
    panel.transcript = list(DEMO)
    panel.hotkey_hint = "Esc 收起   ·   ⌃⌥K 呼出"

    panel.expand()
    panel.set_state("done")
    panel.render()
    shot(panel, "expanded-dark")

    panel.set_theme(False)
    shot(panel, "expanded-light")

    panel.transcript = [LONG]
    panel.current_prompt = "那第一滴雨呢"
    panel.partial = "第一滴雨的味道最明显，因为干燥期积在土壤和植物表面的气味"
    panel.set_state("streaming")
    panel.render()
    shot(panel, "expanded-long-light")

    panel.set_theme(True)
    shot(panel, "expanded-long-dark")

    panel.current_prompt = ""
    panel.partial = ""
    panel.transcript = list(DEMO)
    panel.collapse()
    panel.set_state("done")
    shot(panel, "collapsed-dark")

    panel.set_theme(False)
    shot(panel, "collapsed-light")

    panel.set_state("waiting")
    panel.set_theme(True)
    shot(panel, "collapsed-waiting-dark")

    panel.set_state("failed")
    shot(panel, "collapsed-failed-dark")
    panel.chat.shutdown()
    panel.close()


if __name__ == "__main__":
    main()
