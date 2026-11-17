# B站值班卡片实施计划

> **执行方式：** 当前会话按下列任务逐项实施，团队只读核查交互边界。

**目标：** 落实用户确认的精简工作台布局，不改变 B 站值班业务行为。

**架构：** 保留 `BiliScrollCard` 入口、上下文与快照接口，使用原生 Qt 面板、摘要网格和富文本阅读器组织页面；只在卡片宽度跨断点时调整布局。异步任务继续使用现有 worker，显式分发值班轮结果。

**技术栈：** PyQt5、qfluentwidgets、pytest，无新增依赖。

---

## 任务一：建立回归测试

文件：新增 `tests/test_bili_scroll_card.py`。

- [x] 动态载入 `ui/cards.py`，创建共用 QApplication，不注册插件调度器、不访问真实 B 站。
- [x] 验证诊断折叠、摘要四项、宽窄布局切换、空态和 Markdown 日报。
- [x] 验证长标题与长路径不会造成卡片最小宽度膨胀。
- [x] 用替身 worker 验证 `_on_run_round` 显式传入 `_render_round`，按钮固定短文案，加载期间不会启动第二个任务。
- [x] 运行 `python3 -m pytest tests/test_bili_scroll_card.py -q`，确认旧实现无法通过新增断言。

## 任务二：卡片实现

文件：修改 `plugins/bili-scroll/ui/cards.py`。

- [x] 构造标题工具条、四项摘要网格、日报/最近视频面板、空态、运行反馈和折叠诊断。
- [x] Markdown 使用 `QTextBrowser.setMarkdown()`，列表以转义后的富文本渲染视频元数据，不拼接不可信 HTML。
- [x] 900 像素以下切换上下主体布局，680 像素以下摘要改两列；使用 QBoxLayout/QGridLayout，不重新创建 widget。
- [x] 主题从 context 读取，更新文本、边框、面板、富文本样式和字体，提供 `refresh_style()`。
- [x] `_render_snapshot` 提取现有中文键，列表和诊断分离，完整路径仅出现在折叠诊断。
- [x] `_on_run_round` 使用 `self._start_worker(self._run_round, self._render_round)`；运行期与读取期互斥，不改值班引擎。
- [x] 再跑专项 pytest 直至通过。

## 任务三：视觉与文档验证

文件：修改 `plugins/bili-scroll/README.md`；独立预览及截图放 `.drifox/` 任务目录，不加入插件安装物。

- [x] README 说明摘要、分栏、折叠诊断，更新按钮文案。
- [x] 使用合成快照在 1100、620、460 像素宽度测试深浅主题与空态，使用 `grab().save()` 保存真实 Qt 截图。
- [x] 检查截图中的中文、长标题、路径、边框与主次层级；异常则只修任务范围文件。
- [x] 运行 `python3 -m pytest tests/test_bili_scroll_card.py -q` 与 `ruff check plugins/bili-scroll/ui/cards.py tests/test_bili_scroll_card.py`。
- [x] 先比对开发运行副本，确认仅有空行差异后同步本次卡片改动；不覆盖其他文件，不触发真实值班。

## 评审依据

对照 `docs/superpowers/specs/2026-11-17-bili-scroll-card-design.md`，确认所有视觉要求和原有操作都覆盖；截图中的演示数据必须注明，不宣称已验证真实联网值班。
