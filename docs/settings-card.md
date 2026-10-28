# 设置卡规范（设置页 UI）

本文件约束插件往「设置」页注册的配置卡。范式实现见 [`plugins/voice-reply/ui/config_card.py`](../plugins/voice-reply/ui/config_card.py)（表单型）与 [`plugins/ssh-toolkit/ui/connections_card.py`](../plugins/ssh-toolkit/ui/connections_card.py)（列表型）。

## 1. 用自动卡还是自绘卡

| 场景 | 选择 |
|------|------|
| 字段都是 text / password / bool / select / number / textarea / link / action | **E1 自动卡**：只写 `plugin.json` 的 `config_schema`，不写 UI 代码 |
| 需要可编辑下拉（下拉选 + 手填二合一） | 自绘卡 |
| 选项在运行时才有（服务商、模型、连接列表） | 自绘卡 |
| 字段之间要联动（切服务商换模型清单） | 自绘卡 |
| 需要行尾外链、状态置灰等布局控制 | 自绘卡 |

## 2. 注册

```python
registry.register_settings_card(
    PLUGIN_NAME,          # 插件名
    f"{PLUGIN_NAME}-config",  # card_id
    "卡片标题",            # title
    _MyConfigCard,        # widget_class，构造签名必须是 (parent=None)
    section="plugins",
    priority=1,           # >0 覆盖同 card_id 的 E1 自动卡
)
```

注册失败要降级不阻断（`try/except` + `logger.warning`），旧宿主没有该方法时插件其余功能照常可用。

> **覆盖即接管**：`priority > 0` 的自绘卡会盖掉 `config_schema` 渲染的自动卡，其中的 `link` / `action` 字段随之消失。自绘卡必须自己把这些入口补回来，否则用户会丢功能（voice-reply 1.5.0 丢过「获取 API Key」链接）。

## 3. 布局口径（表单型）

- 卡片内边距 `setContentsMargins(48, 8, 48, 8)`，行间距 `setSpacing(4)`
- 每个字段一行，行结构固定：

```python
label = BodyLabel(text, row)
label.setMinimumWidth(120)                     # 标签列定宽，全卡对齐
layout.addWidget(label, 0, Qt.AlignLeft | Qt.AlignVCenter)
layout.addWidget(control, 1)                   # 控件 stretch=1，撑满剩余宽度
```

- **禁止** `control.setMinimumWidth(220)` + `Qt.AlignRight`：控件会被挤成固定窄条，右侧留白，长值（模型名、URL）被裁
- 行尾动作（获取 Key、打开文档）用内联行：主控件 `stretch=1`，尾部控件固定宽 `AlignRight`
- 重置 / 危险按钮：右对齐，固定宽约 140，**不撑满整行**
- 字段不适用时整行 `setEnabled(False)` 置灰，不要 `setVisible(False)`：隐藏会改变卡片高度、引发布局跳动

### 控件选择

| 内容 | 控件 | 要点 |
|------|------|------|
| 单值枚举 | `ComboBox` | `addItem(label, userData=value)`，userData 必须关键字传 |
| 可手填的枚举 | `EditableComboBox` | 继承 `QLineEdit`；选中后文本是 item label，真值取 `currentData()` |
| URL / 路径 / 短文本 | `LineEdit` | 开启 clearButton |
| 密钥 | `PasswordLineEdit` | 明文不落日志 |
| 多行文本 | `TextEdit` | 最小高度 ≥140，`editingFinished` 语义需自行补 |
| 外链 | `HyperlinkButton` | `setUrl()` 后点击自动用系统浏览器打开 |
| 开关 | `SwitchButton` | 挂 header 右侧或单独行 |

## 4. 回显

- 逐控件 `blockSignals(True)` → 写值 → `blockSignals(False)`，避免回显触发保存
- 存值不在选项清单里时（服务商被删、模型下线）用 `insertItem` 插回首项保住用户配置，不静默重置
- 空值 = 清除 → 回默认，与 `PluginConfigStore` 语义一致
- 长文本回显后 `setCursorPosition(0)`：默认光标在末尾，会把 `FunAudioLLM/CosyVoice2-0.5B` 显示成 `…2-0.5B`
- 回显结束调一次状态刷新（置灰 / 联动），保证首屏就是正确状态

## 5. 折叠高度与动画

qfluentwidgets 的 `ExpandSettingCard` 展开会把 `spaceWidget` 撑成内容等高，导致展开高度 = 内容 + 等高空白、卡片关不上。同时基类的折叠动画依赖这个占位，占位归零后就没了动画。

插件不能 import 主程序的 `expand_height_mixin`（`app.widgets.*` 不是稳定契约），所以每个卡内联一份高度动画：

```python
class _CardHeightDriver(QObject):
    """把动画值写成卡片 fixedHeight（QPropertyAnimation 不能直接驱动 setFixedHeight）。"""

    def __init__(self, card):
        super().__init__(card)
        self._card = card
        self._value = 0

    def _get_value(self):
        return self._value

    def _set_value(self, value):
        self._value = int(value)
        try:
            self._card.setFixedHeight(self._value)
        except RuntimeError:  # 卡片已销毁
            pass

    value = pyqtProperty(int, _get_value, _set_value)


def _animate_card_height(card, target: int, duration: int = 180) -> None:
    from PyQt5.QtCore import QEasingCurve, QPropertyAnimation

    ani = getattr(card, "_expand_height_ani", None)
    if ani is None:
        driver = _CardHeightDriver(card)
        ani = QPropertyAnimation(driver, b"value", card)
        ani.setDuration(duration)
        ani.setEasingCurve(QEasingCurve.OutCubic)
        card._expand_height_driver = driver
        card._expand_height_ani = ani
    ani.stop()
    ani.setStartValue(int(card.height()))
    ani.setEndValue(max(0, int(target)))
    ani.start()
```

卡片侧：`_adjustViewSize()` 只负责「直接定格」（供基类与内容变化后调用），`setExpand()` 走动画：

```python
def _target_height(self, is_expand: bool) -> int:
    try:
        self.spaceWidget.setFixedHeight(0)
    except Exception:
        pass
    return self.card.height() + (self.viewLayout.sizeHint().height() if is_expand else 0)

def _adjustViewSize(self):
    self.setFixedHeight(self._target_height(self.isExpand))

def setExpand(self, isExpand: bool):
    if self.isExpand == isExpand:
        return
    self.isExpand = isExpand
    self.setProperty("isExpand", isExpand)
    self.setStyle(QApplication.style())
    self.card.expandButton.setExpand(isExpand)
    _animate_card_height(self, self._target_height(isExpand))
```

列表型卡把 `_target_height` 换成自己的实测函数（`_measure_content_height()`）：动态重建的行还没 show，`viewLayout.sizeHint()` 会漏算。

验证方法：连续采样 `card.height()`，展开/折叠都应是渐变序列（如 `70 → 175 → 381 → 397`），而不是一步跳到终点。

列表型卡在增删行后，若处于展开态要补一次 `_adjustViewSize()`，否则留白。

## 6. 列表型卡

连接列表、条目管理这类不是「字段表单」的卡：

- 行结构：状态点 / 图标 → 主键（加粗）→ 次要信息（灰色、可省略号）→ 行尾动作按钮
- 行内边距 `12, 6`，行间距 4，外层沿用 `48, 8, 48, 8`
- 空态与错误态用一行提示文字（灰 / 红），不用弹窗
- 行尾动作按钮 `background: transparent` + 细边框，hover 才上色
- 删除等破坏性操作要二次确认，并在确认文案里写清连带影响

## 7. 审查清单

提交设置卡改动前逐条过：

1. 每个字段都有**可见** label，不靠 tooltip 说明字段含义
2. 长值完整可见：控件撑满、长文本光标归零、无固定窄宽
3. `config_schema` 里的 `link` / `action` 在自绘卡里都有对应入口
4. 不适用的字段已置灰（整行），布局不跳动
5. 重置按钮右对齐不撑满
6. 展开无空白、折叠能收回去，展开/折叠有高度动画（帧序列渐变，见第 5 节），增删行后高度同步
7. 深浅主题都正常：优先用 qfluentwidgets 控件自带配色，必须自定义时用 `rgba()`
8. 文案中文、标点统一，不出现「请点击下方按钮进行…」式冗余

## 8. 常见坑

| 现象 | 原因与修法 |
|------|-----------|
| 下拉里选中的文本被裁掉前半截 | `EditableComboBox` 回显后光标在末尾，`setCursorPosition(0)` |
| 选中音色/模型后配置被写坏 | 取的是 `text()`（item label）而非 `currentData()`（真值） |
| `currentData()` 恒为 None | `addItem` 位置传参把值当成了 icon，`userData=` 必须关键字传 |
| 枚举属性不存在导致整卡构建失败 | qfluentwidgets 枚举名不可凭记忆（`GLOBE` 不是 `GLOB`），用 `getattr(F, "X", None) or F.SETTING` |
| 卡片展开后关不上 | 未归零 `spaceWidget`，见第 5 节 |
| 未 show 时高度算少 | `sizeHint()` 在未显示时不完整，需要时手工累加 |
| 设置卡与 tools 抢同一份状态 | UI 侧必须 import 同一顶层模块名复用实例，按路径重载会得到两个实例 |
