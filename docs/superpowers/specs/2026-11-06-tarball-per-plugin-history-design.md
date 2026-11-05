# 设计：dist 按插件分组存档 + GitHub Releases 历史同步

日期：2026-11-06
状态：设计已确认（对话中用户选定方案 A 并批准设计）

## 任务目标

1. 本地构建产物从平铺改为按插件分组：`dist/<name>/<file>.tar.gz`
2. 新增同步脚本，把 GitHub Releases 上已发布的全部历史版本拉回 `dist/<name>/` 本地归档

## 背景与动机

- 现状：`dist/` 平铺 200+ 个 tarball，只含本地最后一次构建的产物。
- 历史版本的权威存储是 GitHub Releases（每插件 × 每版本一个独立 release，tag 形如
  `plugin-<name>-v<version>`，发布后不删、产物不可变），但本地 dist 不回流 CI 产物，
  想拿旧版本只能按 URL 手动下载。
- 需求动机：嫌平铺乱 + 希望本地能直接拿到任意历史版本。用户在四个选项中选定
  「两者都要」，并在 A/B/C 三方案中选定方案 A。

## 不变量（设计约束）

- `dist/tarball_index.json` 位置与结构均不变：generate_marketplace.py 的旧索引回退
  保护逻辑（版本不低于已发布 / 同版本指纹不同 KEEP）依赖它，零风险保留。
- `marketplace.json` 生成结果一字不变（url/sha256/size 均为远端语义）。
- CI（release-plugins.yml）、validate.yml、detect_plugin_changes.py、
  generate_marketplace.py 零改动。
- 宿主 plugin-marketplace 插件零感知：其唯一数据源是 raw.githubusercontent.com 上的
  marketplace.json 与 Releases asset URL，dist/ 不进 git，物理不可见（已核实源码
  ui/marketplace_manager.py:93 等，无任何 dist/ 引用）。
- .gitignore 不变：dist/ 继续整体忽略。
- publish 的发布语义不变：索引驱动、产物不可变（同 asset 同内容跳过 / 异内容报错）、
  同版本重打包必须升版本号。

## 改动清单

### 1. tools/build_plugin_tarballs.py（4 处路径拼接）

- `_pack_single`（约 354 行）：`tar_path = out_dir / fname` → `out_dir / name / fname`
- 三处平台产物调用点（约 491 / 518 / 529 行）：
  `build_tarball(plugin_dir, deps_dir, out_dir / fname, ...)` → `out_dir / name / fname`
- `_run_smoke_checks`（约 502 / 546 行调用）内部按 out_dir 定位包文件处同步加一层
  `<name>`（smoke 需要打开 tarball 做冒烟）。
- `build_tarball` 内部已有 `out_path.parent.mkdir(parents=True, exist_ok=True)`，
  子目录免改；`pip_root = out_dir / ".deps"` 等临时目录不改。
- 文件头注释的产物路径示例同步更新。

### 2. tools/publish_plugin_tarballs.py（1 处）

- 文件定位：`fpath = DIST_DIR / fname` → `DIST_DIR / name / fname`（约 177 行）。
- 本地堆积的历史版本不在本次构建索引里，publish 严格按索引取文件，
  天然不会误传历史包。

### 3. 新脚本 tools/sync_release_history.py

- 鉴权与远端：同目录 `import publish_plugin_tarballs`，复用 `parse_remote` 与 `api`。
- 流程：
  1. 分页 `GET /repos/{owner}/{repo}/releases?per_page=100`
  2. 解析 tag `plugin-<name>-v<version>`（不匹配的 release 跳过）
  3. 对每个 release 的 assets：目标 `dist/<name>/<asset.name>`，同名已存在即跳过
     （产物不可变 ⇒ 同名必同内容，幂等）
  4. asset API 若带 `digest`（sha256）字段则下载后比对，缺失则仅记录 size
- 参数：`--only`（逗号分隔插件名）、`--dry-run`（只列清单不下载）
- 输出：每 release 一行状态 + 汇总（新增 N / 跳过 M / 失败 K，失败不中断整体）

## 验证方案

1. 本地构建单插件（`build_plugin_tarballs.py --only <name>`）：
   产物落 `dist/<name>/` 子目录、smoke 通过、tarball_index.json 内容与改前语义一致
2. `publish_plugin_tarballs.py --dry-run`：能按新路径找到文件，清单正确
3. `sync_release_history.py --dry-run`：列出的 release 清单与 GitHub 页面一致；
   实跑后重跑一遍，第二次应为全 skip（幂等验证）
4. push 后观察 release-plugins.yml 全链路：检测 → 构建 → 发布 → 清单提交正常
5. 确认 marketplace.json diff 为空（或仅时间戳类字段）

## 已知边界与遗留

- 改造前遗留的旧平铺 tarball 不会被自动清理：新逻辑只按索引 + 子目录定位，
  旧文件不会被读到，仅手动清理即可。
- sync 依赖 GitHub API 可达性；无 token 时与 publish 同策略（只读公开 release
  可匿名，受 60 次/小时限流约束）。
- dist 本地归档仅本机有效；CI runner 每次 checkout 全新，不受影响。
