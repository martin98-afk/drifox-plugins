# 顶边快捷对话实施计划

> **执行要求：** 按任务逐项执行；可选 `subagent-driven-development` 或 `executing-plans`。复选框用于记录真实完成项。

**目标：** 在 macOS 上用顶边胶囊展开独立纯文本对话，支持真实流式及收起后继续处理。

**架构：** 先验证宿主 `EngineSession` 的部署契约，再实现独立会话控制器及 Qt 小窗。快捷键与窗口视图分开；旧插件只在主工作树暂存退役，不带入开发分支。

**技术：** Python、PyQt5、DriFox 能力池、macOS 原生快捷键（仅在宿主入口不具备跨应用能力时评估）。

规格：`docs/superpowers/specs/2026-11-26-notch-chat-design.md`。

## 任务一：宿主契约验收

- [ ] 在 `plugins/notch-chat/tests/host_probe.py` 写下述探针；宿主入口从 UI 主线程取 `pool_for(plugin="notch-chat", surface="ui")["engine.session"]`，在同一后台线程顺序执行两轮。探针不写会话库、不输出回复正文。

```python
from threading import Event


def probe_engine(create):
    session = create("notch-chat", hook_policy="none", permission_strategy="auto_deny")
    saw_delta = Event()

    def mark_delta(piece):
        if isinstance(piece, str) and piece.strip():
            saw_delta.set()

    try:
        first = session.turn(
            user="记住本次校验词是蓝松塔；请先用两段短文介绍雨天读书。",
            tools=[], callbacks={"content_received": mark_delta},
            timeout=60, auto_history=True,
        )
        assert first.ok and first.text.strip(), "首轮无有效回复"
        assert saw_delta.is_set(), "未收到正文增量"
        second = session.turn(
            user="刚才的校验词是什么？只回答校验词。",
            tools=[], timeout=60, auto_history=True,
        )
        assert second.ok and "蓝松塔" in second.text, "第二轮未保留上下文"
    finally:
        session.cleanup()
```

- [ ] 宿主验收入口显式触发探针。记录首个增量和 `turn()` 返回的单调时钟次序；必须前者早于后者。调用前后核对主窗会话 ID 和消息数不变。
- [ ] 在真机发起一个长回复，等待首个增量后用另一线程调用公开 `session.cancel()`；检查取消、在途回调收尾、下一轮能发送。无需输出模型名、回复全文或凭据。
- [ ] 若运行版签名或行为与公开契约不符，记下具体缺口并暂停后续 UI 接入；不使用私有引擎、密钥或伪流式兜底。真机通过才进入任务二。

## 任务二：插件骨架及会话控制

- [ ] 建立 `plugins/notch-chat/.drifox-plugin/plugin.json`、`plugins/notch-chat/ui/__init__.py`、`plugins/notch-chat/README.md`。注册 UI，声明 `api_version: 2` 与 `engine.session`，仅启用实际组件。
- [ ] `plugins/notch-chat/ui/chat.py` 实现 controller：串行驱动单个隔离 EngineSession，默认工具为空。每轮用同一轮次编号发送增量、完成、超时或异常；主线程仅消费当前轮次事件。停用时协作取消、等待退场并清理会话。跨线程不访问 UI。
- [ ] `plugins/notch-chat/tests/test_chat.py` 用可控 EngineSession 替身验证：重复发送被拒绝、失败后恢复、停止后忽略迟到增量、界面收起不取消。使用真机记录单独验收流式和上下文。

## 任务三：顶边胶囊和快捷键

- [ ] `plugins/notch-chat/ui/panel.py` 实现用户认可的紧凑胶囊与展开稿：同一窗口形态，状态文字、滚动正文、底部输入和停止；Esc 保留输入与在途回复，输入法候选提交不能误发送。
- [ ] `plugins/notch-chat/ui/hotkey.py` 接入已验证的跨应用入口；已有组合冲突时不覆盖。只有注册成功时显示已绑定，失败保留胶囊点击入口。卸载或停用释放注册。
- [ ] `plugins/notch-chat/tests/test_panel.py` 验证发送键、Esc、停止和状态同步。实测其它应用前台触发、输入焦点、普通屏与刘海屏顶边定位；完整对话入口只在确认正式保存和跳转能力时启用。

## 任务四：交付核验

- [ ] `python3 -m pytest -q plugins/notch-chat/tests` 与 `python3 tools/validate_plugins.py plugins/notch-chat --strict`；市场未收录项交 CI，同其他校验项分开报告。
- [ ] 真机截图对照浅色、深色两态；完成真实请求、流式、追问、收起、停止、错误可恢复。更新 `plugins/notch-chat/README.md` 写明实际最低宿主版本及快捷键入口。
- [ ] 对照规格做独立代码审查。开发提交只包含新插件和相关文档；旧插件退役不动历史、不手改市场生成文件、不提前推送。
