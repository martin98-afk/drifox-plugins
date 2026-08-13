# Manual 模式示例

场景：宿主能读取 Agent Skills，但没有本包支持的 Hook 生命周期。

1. 安装：

   ```bash
   ./install.sh --project-dir /path/to/project --platform manual
   ```

2. 会话开始时运行 loader：

   ```bash
   cd /path/to/project
   python /path/to/memory-3layer/hooks/memory_loader.py
   ```

   它会按预算返回 Layer 3、近期 Layer 2 和相关 Layer 1 上下文。

3. 用户明确说“记住”时，调用公开记录入口，不要把任意工具原始输出当作记忆。例如：

   ```bash
   python scripts/record_memory.py --project-dir /path/to/project --fact "This project uses pnpm." --topic workflow
   ```

4. 也可以直接检查：

   - `.memory-3layer/MEMORY.md`
   - 最近 `MEMORY_DAILY_DAYS` 天的日记
   - 相关 topic 最近 `MEMORY_MAX_ITEMS` 条 active facts

5. 会话结束或压缩前记录最小摘要，不复制完整对话。

6. 定期运行 `memory-status` 与 `memory-review`。

Manual 模式的预期结果是数据格式和生命周期可用；它不包含自动启动、自动提取或自动压缩前保存。
