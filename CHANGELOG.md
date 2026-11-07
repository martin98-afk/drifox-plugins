# Changelog

## Unreleased
### 🔧 kling-ai-plugin v1.0.1：端点要求 OAuth，补授权声明修复连接失败
- **症状**：启用后热连接失败，日志 ConnectError 与 401 Unauthorized 交替出现，设置卡红灯
- **根因**：`kling.ai/mcp/plugin` 按 MCP 规范回 401 + `WWW-Authenticate: Bearer resource_metadata=...oauth-protected-resource/mcp/plugin`，要求 OAuth 授权码流程；插件 `.mcp.json` 缺 `auth` 声明，宿主不触发授权（README「无需密钥直连」沿用 WorkBuddy 市场宣传语，实测不成立）；ConnectError 另有系统代理瞬时抖动成分（httpx trust_env 读 WinINET 注册表代理，curl 不读）
- **修复**：`.mcp.json` 补 `auth: {type: oauth, client_name: DriFox, scope: ""}`，宿主走 DCR+PKCE 浏览器授权，token 持久化自动刷新；README 认证段更正
- **依赖**：宿主 OAuth 支持 v0.6.7 引入，`min_host_version` 0.5.0 → 0.6.7
- **验证**：端点 401 头带 resource_metadata；授权服务器元数据齐全（registration_endpoint/token_endpoint/S256/refresh_token/public client）；端到端授权待宿主内点启用实测
### 🔧 cyberpunk-2077-somi v1.0.1：前景人物与背景构图对齐
- **症状**：角色剪影与场景背景对不上，位置随窗口尺寸漂移，调 offset 也补不回来
- **根因**：`decorations` 的 reference 是 `chat_scroll_area.viewport()` 且等比 fit，而 `scene` 是 `_chat_frame` 矩形 + `setScaledContents` 拉伸；同一张壁纸拆出的两层变换不同，错位量随窗口尺寸非线性变化
- **修复**：改用宿主的 `scene.foreground`（与背景同矩形、同拉伸，Z 序在 dim 之上不被压暗）；`opacity` 0.55 → 1.0 还原原壁纸观感
- **依赖**：宿主 >= 0.6.15 即可安装；`scene.foreground` 为 0.6.16 新增，旧宿主忽略该字段、只显示背景（优雅降级）
- **验证**：宿主 `tests/widgets` 28 条通过，离屏渲染与壁纸原图构图一致
### ✨ file-designer v0.6.0：拾取/标注支持框选多元素
- **变更**：拾取/标注态左键拖拽框选（位移 >4px 出选框，矩形相交收集命中，六格式共用一套 JS，单击选单个行为不变）；拾取多元素一张选框合并截图 + 逐元素连号回填（新桥槽 `pick_many`，截图仅首条携带）；标注组合化——框选多元素一条注释挂整组（数据条目 `anchor` → `anchors[]`，note-box 按 seq 定位编辑/更新/删除，存量单 anchor JSON 读取时归一化兼容，重开恢复不受影响）
- **验证**：插件单测 104 passed（新增归一化/组合标注/批量拾取/marquee 注入 12 例）+ ruff 清零

### 🔧 file-designer v0.5.2：移除 open_docx 旧名工具
- **变更**：删 `_LEGACY_SCHEMA` 与 `open_docx` 注册，工具清单只留 `open_file`（v0.4.0 起的兼容别名退役）；测试补「注册清单只含 open_file」断言锁定接口面
- **验证**：插件单测 94 passed

### 🔧 file-designer v0.5.1：tools 相对导入致工具从未注册，改动态加载 formats
- **症状**：热重载日志反复报 `[PluginToolLoader] 插件 file-designer 新模块加载失败，保留旧注册: attempted relative import with no known parent package`
- **根因**：`tools/file_tools.py` 模块级 `from ..ui.formats import ...`。宿主 PluginToolLoader 以顶层模块名 exec tools/*.py（无父包，`__package__` 空），相对导入必炸；试加载失败走 last-known-good 保留旧注册。该 import 自 v0.4.0 引入，冷启动同样失败——open_file/open_docx 实际从未注册成功，仅表现为热重载警告
- **修复**：删模块级相对导入，新增 `_load_formats()` 运行时加载：优先 `importlib.import_module("ui_plugin_file_designer.formats")` 复用 UI 侧已注册模块（单一状态源，UI 重载自动跟随），UI 未加载时按路径 spec_from_file_location 兜底独立副本（formats 为模块级静态注册表，副本内容恒等）
- **验证**：宿主 `_load_module` 真函数全链路（AST guard→register→impl 后缀校验→状态源复用）4 项通过；插件单测 93 passed（含新增 `tests/test_file_tools.py` 4 例回归）

### 🔧 tarball 冒烟门禁：识别编译扩展子模块，修 file-designer 三平台包误杀
- **症状**：push `44e327b3` 后 CI Release Plugin Tarballs 失败，三平台包都已产出（14.76/13.73/12.54 MB）却被 strict-deps 全部拒绝发布
- **根因**：`smoke_check_tarball._module_exists` 只按 `.py` / 包目录 / `__init__.py` 重导出判定子模块存在性。`lxml.etree` 落盘形态是 `etree.cpython-314-*.so` / `etree.cp314-win_amd64.pyd`，三种候选全不命中，于是报「lxml 已 vendored 但缺 etree」，对三平台各报 6 处，全部包被剔除
- **修复**：新增 `_ext_module_names()`，用既有 `_EXT_RE` 剥掉 ABI/平台标签取模块名，作为第 5 条存在性候选。同名前缀、嵌套目录、其它包的扩展均不算命中
- **顺带**：`TestSmokeGateFailClosed` 既有失败修好 —— `setattr(sys,'modules',{**sys.modules})` 换整个 dict 后 CPython import 仍读旧 dict，模拟的 `None` 不生效；改 `monkeypatch.setitem` 直接改原 dict
- **CI 触发面**：`release-plugins.yml` 的 `push.paths` 补 `tools/smoke_check_tarball.py`，此前改门禁脚本不会重跑发布
- **验证**：本地构造三平台 file-designer 形态包 `smoke_check` 全通过；`tests/test_tarball_pipeline.py` 15 passed、插件单测 88 passed、223 插件清单校验通过

### ✨ docx-designer → file-designer v0.4.0：多格式文件设计
- **改名与迁移**：插件目录 `plugins/docx-designer` → `plugins/file-designer`，浮卡 `plugin_name`/`card_id` 同步改名、title「文件设计」；注册时若 `plugin_data/file-designer/` 不存在而旧目录存在则整目录复制，历史 picks 截图与标注 JSON 沿用；`tools/docx_tools.py` → `tools/file_tools.py`，`open_file` 为主工具、`open_docx` 保留兼容别名；不保留 `/docx-designer` 命令别名
- **新增 4 类格式**（统一 HTML 管线 + `ui/formats.py` 格式注册表）：xmind（content.json / content.xml 双形态 → 自绘 SVG 导图）、xlsx/xlsm（openpyxl 数据优先，合并单元格/列宽/多 sheet）、csv（utf-8-sig→utf-8→gb18030→latin-1 编码链 + Sniffer 探分隔符）、mermaid（`.mmd`/`.mermaid`，内联 `assets/mermaid.min.js` v10.9.1 渲染 SVG + 源码行列表）；四者共用 `_BOOT_JS/_PICK_JS/_ANNOTATE_JS` 与 note-box，元素挂 `data-anchor` 即自动具备拾取/标注/截图/回填
- **锚点契约**：xmind `s{sheet}/n/{节点路径}`、xlsx `s{sheet}!B3`、csv `r{行}c{列}` / `table`、mermaid `L{行号}`；`pick_format.py` 按 mode 扩展描述头与锚点规则说明，lookup 回填层级路径/表头/整行/上下文
- **注入语义不变**：只回填对话输入框（锚点+文本+上下文+截图），不写回源文件
- **防护上限**：xlsx 2000 行 × 200 列、csv 5000 行 × 200 列、xmind 800 节点，超出截断并在状态栏提示
- **依赖与资源**：manifest 加 `openpyxl>=3.1.0`；`assets/mermaid.min.js` 3.3MB 随插件打包，库缺失/初始化失败降级为源码视图
- **验证**：插件单测 88 条全绿（`python -m pytest plugins/file-designer/tests/ -q --noconftest`）；按注册表真实分派 4 类通用格式验 parse→render→lookup→回填契约；Edge headless `--dump-dom --virtual-time-budget` 离屏确认 mermaid.min.js 渲染出 SVG 且节点挂 `L{行号}` 锚点（Qt5 WebEngine / Chromium 87 兼容性仍待宿主内实测）
- **市场**：`marketplace.json` 条目改名、version 0.4.0、`downloads_cache.json` 的 `docx-designer: 12` 迁为 `file-designer: 12`；CI 按新名首次发布三平台 tarball。注意计数服务 key 按插件名生成（`drifox-plugins-<name>`），远端新 key 从 0 开始，本地缓存的 12 在下次 `fetch_downloads.py` 成功拉取后会被远端值覆盖

### 🚀 发布流程：新插件自动发布 + tarball 冒烟门禁
- **新插件首次推送即自动发布**：`tools/detect_plugin_changes.py` 的真源从 `marketplace.json` 改为 `plugins/*/.drifox-plugin/plugin.json`。此前新插件因清单里还没有 tarball 字段而被跳过，必须人工跑 build + publish；现在按「版本未发布过 / 版本不一致」判定，新插件与改版插件走同一条自动链路
- **新增 `tools/smoke_check_tarball.py`**：发布前逐包体检，`build_plugin_tarballs.py` 已接入（未通过的包从索引剔除、不发布）。检查项：
  - **依赖子模块存在性**：业务代码 `from X.Y import Z` 时，若 X 属于包内 vendored 依赖，则 Z 必须真实存在于 X.Y 下（含 `__init__.py` 重导出，做 AST 内容级校验而非仅看文件存在）
  - **平台归属**：包内 `.so`/`.pyd` 的平台标签必须与包名一致，交叉污染（darwin 包装了 win_amd64）直接拦下
  - **ABI 匹配**：二进制扩展的 `cpython-3XX` 标签必须等于目标运行时（cp314）；CI 在 py3.12 上拉错 wheel 会被拦下
  - **包完整性**：tarball 可解压、`.drifox-plugin/plugin.json` 存在且可解析
  - **依赖缺失提示**：声明了 pip 依赖却无 `deps/` 目录时告警
- **为什么需要**：2026-11 bili-scroll v0.2.2 事故——manifest 的 pip 包名写成停更的 `bilibili_api`，业务代码要的是 `bilibili-api-python` 17.x。CI 一路绿灯发了三平台包，用户装完才发现 `from bilibili_api import login_v2` 直接 ImportError，插件 UI 与 MCP 控制端点双双失效。静态检查在旧包上精确复现该错误、在新包上放行
- **取舍**：只用单 runner（ubuntu）做静态校验，不引入三平台 runner。原因：macOS runner 按 10 倍额度计费，而 217/223 个插件是纯 Python；真实 import 在 CI 上对含原生扩展的包必然是假阳性（cp314 的 `.so` 无法在 py3.12 加载），插件业务代码还依赖 DriFox 宿主模块。明确验不了的一项：`.so` 文件名不含 CPU 架构（mac arm64 与 x86_64 同名），架构错配无法静态判定
### 🔧 bili-scroll v0.2.4：MCP 壳 bridge.json 验活，修 app 重启后首连崩溃
- **症状**：app 重启后 `bili` MCP 首连必失败，日志报 `连接服务器 'bili' 失败: Expecting value: line 1 column 1 (char 0)`；手动重连一次即恢复。spawn 到失败仅约 2 秒，且无任何子进程 stderr 输出
- **根因**：MCP 壳 `server.py` 的 `_main` 对 `bridge.json` 只查**存在性**。app 重启后磁盘上残留的是上次实例写的过期文件（端口/token 已失效），壳据此跳过等待直接开始 stdio 握手——握手本身不需要控制端点所以成功；随后 `list_tools` 按 bridge.json 里的旧端口发请求，连接失败使壳进程崩溃退出，客户端读到 EOF，SDK 把空流报成 JSON 解析错误。等插件 UI 加载、控制端点重启并重写 `bridge.json` 后重连即成功，形成「首连必败、重连就好」的模式
- **修复**：`_main` 先经 `_endpoint_alive()` 对 bridge.json 里的端口做 `/healthz` 验活；文件不存在或端点不通一律走 `_wait_bridge()` 轮询（每轮重读端口），等端点就绪后才握手。含原生扩展解释器（`py -3` 指向系统 Python 3.12）时控制端点未就绪的场景同样被覆盖
- **验证**：`_endpoint_alive` 有效/过期判定单测通过；真实 spawn 壳进程 + initialize 握手成功（serverInfo `bili-scroll 1.28.1`）；app 内实连 62 工具稳定
### 🔧 bili-scroll v0.2.3：依赖包名修正 + MCP 入口跨平台
- **症状**：macOS / Linux 上开启 `bili` MCP 报 `[Errno 2] No such file or directory: 'py'`；即便能起壳，插件 UI 装载也报 `ImportError: cannot import name 'login_v2' from 'bilibili_api'`，控制端点起不来导致 MCP 拿不到工具表
- **根因（依赖）**：`dependencies.pip` 写的是 PyPI 包名 `bilibili_api`（MoyuScript 的老包，停更在 9.1.0/2021），而 vendor 代码 `mcp_server.py` / `bili_impl.py` 用的是 `bilibili-api-python`（Nemo2011 fork，17.x）的 API，`login_v2` / `opus` / `homepage` 老包一概没有。CI 按 manifest 拉依赖，于是每个平台打包进去的都是老 SDK
- **根因（入口）**：`.mcp.json` 写死 `command: py` + `args: [-3, …]`，这是 Windows Python launcher 专属写法，macOS/Linux 无此命令
- **修复**：依赖改为 `bilibili-api-python>=17.4.1,<18`（与 `vendor/bilibili-mcp/requirements.txt` 对齐）；`.mcp.json` 入口改为 `python3`，去掉 `-3`（壳内 `_bootstrap` 仍会按 bridge.json 自举到带 mcp/httpx 的解释器）
- **验证**：本地 deps 换装 17.4.2 后 `bili_impl` 导入成功、patch ⑨ 正常打上、62 个工具注册；控制端点 `/healthz` 与 `/api/tools` 正常；stdio MCP 壳端到端握手成功并拉到 62 个工具
### 🔧 browser v1.6.2：MCP 入口跨平台
- `.mcp.json` 的 `command: py` + `args: [-3, …]` 为 Windows Python launcher 专属写法，macOS/Linux 上 MCP 直接报 `[Errno 2] No such file or directory: 'py'`；改 `python3` 并去掉 `-3`（壳内 `_bootstrap` 自举机制不变）
### 🔧 live-data v0.1.1：修复四工具全部返回「未知工具：」的致命分发 bug
- **症状**：finance_live / dev_live / weather_live / misc_live 任一调用都返回「未知工具：」（名为空），插件自上架以来从未真正执行过；schema 注入与注册均正常，仅执行层失败
- **根因**：四工具共用单一 `_impl`，靠 `getattr(tool_ctx, "tool_name")` 区分；但宿主注入的 tool_ctx 是 dict 且不含工具名（kwargs 也无 `__tool__` 键），getattr 对 dict 恒返回默认值空串，全部落入「未知工具：{tool}」兜底分支
- **修复**：每工具注册独立包装函数硬编码名字（`_finance_live_impl` 等），共享 `_run_tool` 做分发与异常归一；删除不可达的 getattr/`__tool__` 取名逻辑
- **验证**：新增 7 条分发回归测试（含 ToolExecutor 端到端 seam）全绿；运行时 10 个真实分支逐一联网实测全通（汇率/股票/指数/金价/npm/PyPI/GitHub/天气/B站/IP）

### 🔧 docx-designer v0.3.1：大表格分页丢内容 + 拖拽失效修复
- **pptx 大文件预览空白**：`setHtml` 超 ~2MB 静默不渲染（光大售前 PPT 渲染出 39MB HTML，表现为状态栏「已打开」但内容不刷新）；>1.5MB 自动改走本地文件加载（`plugin_data/docx-designer/preview_a/b.html` 轮换防缓存），qwebchannel.js 用 QFile 读 qrc 资源内联进页面，file:// 加载下拾取/标注桥照常可用；另图片按 blob 哈希去重（同一 logo 多页/多层复用只嵌一份）
- **pptx 版式/母版背景丢失**：此前只渲染 slide 自身形状（模板背景图/装饰件在版式的非占位符形状里，MindSpore 封面山景图整张丢失）；现在版式与母版非占位符形状垫底渲染（`showMasterSp="0"` 时跳过母版层），背景填充链 slide→layout→master 逐级取（支持图片填充）；版式/母版锚点 `:L`/`:M` 前缀区分
- **多段单元格整段丢失**：单元格解析此前只回传首段 runs，渲染层随之丢掉其余段落（简历类文档正文几乎全在大表格单元格里）；改为逐段落收集：块级 `<p class=cp>` 渲染 + 平铺 runs（`\n` 分隔）兜底页眉页脚；页眉页脚表格同链路受益
- **超页大表格被裁剪**：JS 装箱分页的溢出处理只在页内已有多个元素时才把元素挪到新页，单元素超页高时直接留下被 `overflow:hidden` 裁剪（29 行简历大表第 20 行后全部不可见）；新增 `_splitTable`：表格溢出时**在当前页就地按行装箱拆页**（以页面 body 实测高度为界，页 1 剩余空间被表格首行填满，同 Word 行为），断点回退到整行网格起点（colspan 和 ≥ 总列数才断，避免切碎 rowspan），单行超页时按段落拆行续排（单元格逐段落渲染为块级 `<p class=cp>`，续行重复原单元格结构、尾段搬入下页），无法再拆才硬断兜底；无头 Chrome 实测各页 body scrollHeight=clientHeight 零溢出
- **拖拽打开失效**：预览区被 QWebEngineView 铺满，拖拽事件第一接收者是 WebEngine 内部 delegate（focusProxy），落在窗口的 dragEnterEvent/dropEvent 永远收不到；按宿主 card_viewers 同款模式在 delegate 上幂等装 eventFilter（loadFinished/showEvent 补装，防 delegate 重建），拦截 URL 拖拽转 `dropEvent`（同时阻止 Chromium 用拖入文件导航覆盖预览），非 .docx/.pptx 拖入给状态栏提示
- **验证**：真实 3 页简历经无头 Chrome 跑分页 → 29 行拆进 5 页、全量文本探针命中；测试 39→42 条（多段单元格 runs/`<br>` 渲染/分页 JS 拆表分支）

### ✨ docx-designer v0.3.0：pptx 预览与拾取标注
- **pptx 预览**：python-pptx 解析 → 固定画布绝对定位渲染（每页一张 slide）；文本框/占位符（字号/颜色/加粗/对齐/行距，版式占位符回退）、图片、表格、形状填充；图表/媒体降级占位
- **拾取/标注**：pptx 锚点 \`幻灯片:元素\`（0 起），复用同一套拾取回填、截图、标注持久化与发送流程；\`format_pick\`/\`format_annotations\` 按 pptx 语义描述
- **接入**：打开对话框与拖拽支持 \`.pptx\`；≡ 菜单缩放对幻灯片生效（deck zoom）
- **依赖**：deps 预置 python-pptx 1.0.2 + Pillow 13（cp314 win32）+ XlsxWriter；测试新增 4 条（解析/字体回退/表格/渲染）

### ✨ docx-designer v0.2.5：docx 文档设计模式（预览 + 拾取 + 标注）
- **预览**：python-docx XML 流解析 → 自生成 HTML（QWebEngineView 分页视图，sectPr 页面尺寸/边距 + JS 装箱分页 + 页眉页脚随页重复）；样式链继承（basedOn）、多级编号（numbering.xml 状态机，中文数字/字母/罗马）、段落属性（对齐/缩进/段距/行距）、run 字号颜色字体、表格 vMerge/gridSpan 与 tblGrid 列宽、内嵌图片、OMML 公式 HTML/CSS 模拟
- **拾取**：「拾取」态点击元素 → 锚点（body 块索引）+ 类型/样式 + 全文文本 + 区域截图回填输入框（QWebChannel），连续拾取连续追加
- **标注**：「标注」态点击元素写注释（角标编号 + 悬浮 tooltip），标注按文档路径持久化（重开恢复），悬浮可改；「≡ → 发送标注」把全部注释一次性回填供模型逐条修改
- **拦截**：系统打开 .docx 默认进预览窗口（os.startfile / QDesktopServices 链式代理，独立标记不干扰 browser 接管）；≡ → 「用系统程序打开」走 ShellExecuteW/open/xdg-open 系统级绕代理
- **样式还原修复**：页眉页脚此前只解析不渲染（`window.__hdrftr` 未被分页 JS 读取）→ 页眉改结构化表格还原（列宽/rowspan/边框），PAGE/NUMPAGES 域填真实页码，页脚 logo 按原尺寸左对齐，多节文档段落级 sectPr 兜底；样式链 basedOn 合并方向修正（基类先、子类覆盖），Title/Subtitle 字号与居中不再被正文样式覆盖；空 `<w:ind/>` 不再误清继承缩进，无 pStyle 段落补默认样式（1.5 行距/首行缩进 2 字符）；run 支持 szCs/bCs/iCs；段落边框 pBdr 转 CSS；显式分页（pageBreakBefore / br type=page / 分节符）生效且不产生空白页
- **标注管理**：注释浮框新增「删除」按钮（单条），≡ 菜单新增「清空标注」（确认后清空）；删除后序号自动重排并落盘
- **菜单字体**：≡ 下拉显式 setFont + QSS，跟随主题/系统字体
- **分页/域修复**：`pageBreakBefore w:val="0"` 不再误判分页（目录不再每项一页、正文不再错位）；域类型按指令首词精确匹配（PAGEREF 目录页码不再被替换成当前页）；页脚文本框内 PAGE 域正确转 `{{page}}`
- **页眉页脚拾取/标注**：页眉页脚容器挂 `data-anchor="header"/"footer"`，同锚点多页同步角标；回填与发送文本标 [页眉]/[页脚]
- **重新加载**：≡ 菜单新增「重新加载文档」，外部编辑后刷新预览并保留拾取计数与标注
- **确认弹窗**：清空标注改用宿主统一 `ConfirmDialog`（MaskDialogBase 遮罩风格），不再用 QMessageBox
- **依赖**：python-docx + lxml（deps/ 预置 cp314 win32）；测试 35 条（解析/渲染/标注格式/页眉页脚/拦截判定）
### ✨ browser v1.6.0：拦截本地 PDF 打开进内置浏览器
- **拦截**：本地 .pdf（磁盘路径 / file://）默认进内置浏览器（WebEngine PdfViewerEnabled 内嵌渲染），配置键 \`intercept_pdf\`（默认开，拦截设置面板可关）
- **实现**：redirect_config 新增 \`_is_local_pdf\` 判定（\`_is_local_html\` 重构为通用 \`_is_local_doc\`）；\`_page_factory\` 开启 \`PdfViewerEnabled\`（Qt 5.13+，缺失时防御性跳过）
- **测试**：新增 \`tests/test_redirect_pdf.py\` 5 条（判定/开关/总闸/html 回归）
### 🔧 browser v1.5.3：用户数据迁到 `plugin_data/browser/`，插件更新不再丢
- **问题**：书签/历史/下载记录（`browser.db`）、拦截配置（`browser-redirect.json`）、登录态 `profile/`、拾取截图 `picks/`、MCP 截图 `screenshots/` 全落在插件安装目录 `~/.drifox/plugins/browser/data/`，而插件升级是整目录替换，更新即丢
- **修复**：新增 `ui/paths.py` 统一解析落点，走能力池 `storage.data_dir`（返回 app_data 根）自拼 `plugin_data/browser/`；能力池不可用（MCP 子进程 / 纯逻辑单测）回退 `~/.drifox`。`data.py`、`profile_manager.py`、`redirect_config.py`、`design_mode.py`、`control_server.py` 五处路径全部改走它，`cache/` 可再生不迁
- **迁移**：首次访问自动把旧目录的 `browser.db` / `browser-redirect.json` / `picks` / `screenshots` / `profile` 复制到新位置，**复制不删**，旧目录留作回滚；全部成功才写 `.migrated-from-plugin-dir` 标记，被文件锁打断则下次重试
- **注意**：登录态 profile 要重启 DriFox 才切到新路径（运行中的 WebEngine 仍持有旧 profile 实例）
- **测试**：新增 `tests/test_browser_paths.py` 6 条（落点、helper 同源、文件+目录迁移、只迁一次、目标已有内容不覆盖、无旧目录空跑），`6 passed`

### 🔧 browser v1.5.2：外部打开彻底绕开代理链（v1.5.1 未修净）
- **v1.5.1 为何不够**：剥链只认 `_drifox_redirect` 标记，而实机上收到的 `resolved` 是一个**丢了标记的旧版代理**（`<function _redirect_os_startfile at ...>`），被当成原生入口直接调用，于是又走拦截进内置浏览器；日志实锤 `resolved=<function _redirect_os_startfile>`、`stash=None`
- **根因**：`install_redirect` 接管时用 `elif _orig_os_startfile is None: = prev_sf` 兜底，把「无标记的旧代理」存成了原始入口；安装日志里那次也没打印「接管热重载遗留的 os.startfile 代理」
- **修复**：代理判定改为「`_drifox_redirect` 标记 **或** `__name__` 命中 `_redirect_os_startfile` / `_redirect_webbrowser_open` / `_redirect_execute_bash` 或类身份」，`_strip_proxy_chain(fn, attr)` 逐层剥到原生（8 层上限防自环），webbrowser / QDesktopServices / os.startfile 三处接管统一走它
- **外部打开**：`open_url_external()` 不再依赖 `os.startfile` 的代理链，直接 `ShellExecuteW`（Win）/ `open`（macOS）/ `xdg-open`（Linux），从根上断掉回环
- **兜底**：`_orig_os_startfile` 为 None 时 `_redirect_os_startfile` 内部改走 `_shell_open`，不再 `TypeError`
- **验证**：探针复现实机现场（新代理 → 无标记旧代理 → 原生），三层接管后解析出 `<built-in function startfile>`，自环返回 None，原生原样返回；`py_compile` 通过

### 🔧 browser v1.5.1：修复「在外部浏览器打开」回环到内置浏览器
- **问题**：工具栏外链按钮走 `open_url_external()`，原实现只取一层 `_drifox_orig_startfile`。热重载接管若把旧代理当成「原始入口」存下，取回的 orig 本身仍是拦截代理，调用后重新走 `_try_intercept` → 内置浏览器新标签，而函数末尾照旧 `return True`，状态栏还报「已在系统默认浏览器打开」
- **修复**：新增 `_unwrap_startfile()` 沿 `_drifox_orig_startfile` 逐层剥代理（最多 8 层，兼容自环），剥不干净退回模块 stash `_orig_os_startfile`；仍不可用则 Windows 走 `ctypes.windll.shell32.ShellExecuteW`（不经过 Python 层任何 patch，必然落到系统默认浏览器）
- **诊断**：新增 `[browser-external]` 日志，每次外部打开打印 `os.startfile` / resolved / stash 三个对象，代理链异常可直接定位
- **验证**：剥链逻辑用四种代理形态（双层代理 / 断链 / 原生 / 自环）探针验证全通过；`py_compile` 通过

### ✨ browser v1.5.0：Design Mode（点页面元素直接进对话输入框）
- **交互**：工具栏 `⌖` 按钮、`Ctrl+Shift+C`、右键菜单「选取此元素」三条入口；鼠标移动高亮元素，点击后把 HTML、过滤后的计算样式、元素截图（外扩 40px）追加到输入框，可连续点多个，`Esc` 退出
- **实现**：事件挂在 `view.focusProxy()` 上（Qt WebEngine 实际渲染控件），页面内只跑无状态 `runJavaScript` 查询，高亮框是 Python 侧透明 QWidget，不污染页面 DOM
- **回填**：走能力池 `caps_for("input.write")`，首次覆盖后续追加，`focus=False` 保证不抢焦点（否则无法连续拾取）
- **限制**：closed shadow DOM 只能选到宿主，跨域 iframe 只能选到容器，拿不到 matchedCSSRules（那需要 CDP）
- **附带**：刷新/停止按钮移到地址栏右侧
- **验证**：`tests/test_browser_design_mode.py` 11 条纯函数单测通过；`validate_plugins.py` OK

### 🔧 ssh-toolkit v0.4.4：本地路径黑名单豁免 `~/.drifox/workspaces`（项目工作区误伤）
- **问题**：`~/.drifox` 整棵在硬黑名单，DriFox 项目工作区 `~/.drifox/workspaces/<proj>` 恰在其下，ssh_upload/ssh_download 对工作区文件一律拒绝，`allow_paths` 显式放行也救不回（硬黑名单优先于边界判定）
- **修复**：`tools/_guard.py` 新增 `_EXEMPT_SUBTREES` 豁免子树，仅放行 `~/.drifox/workspaces`；`_dir_blocked` 命中豁免子树即跳过目录黑名单。`.drifox` 根下其余位置（connections.json 等凭据落盘）仍拒绝；凭据文件名黑名单（.env / *.pem / sessions.db…）与 workdir/allow_paths 边界在豁免子树内仍生效
- **测试**：`tests/test_guard.py` 新增 `test_drifox_workspaces_exempt_from_block_dirs`（豁免子树内放行 / 子树外 connections.json 仍拒 / 子树内 .env 仍拒）；ssh-toolkit 全量 70 passed, 1 skipped

### 🔧 ssh-toolkit v0.4.3：`ssh_exec` 的 schema 说明写入 tmux 长期会话指引
- **问题**：插件执行链路固定 `client.exec_command()` + 同步轮询到进程退出，超时即关通道，长任务（编译、训练、服务）随通道一起死。此前 README 里没有任何 tmux 说明，AI 读不到 `registry.register` 之外的文档，实际会直接 `ssh_exec("make")` 然后超时失败
- **修复**：`tools/exec_tool.py` 的 `ssh_exec` schema description 直接写入判据与四条命令——`has-session || new-session -d`、`send-keys ... Enter`、`capture-pane -pt S -S -300`、`list-panes -F '#{pane_dead}'`，并附 `cmd; echo __RC=$?` 取退出码写法；同时写明两条硬约束（禁 `tmux attach`，它永不返回；`exec_command` 走非 login shell，PATH 不全时用 `bash -lc` 包一层）
- **为何放 schema**：工具说明是 AI 唯一能读到的位置；README 面向人类，对模型不可见
- **文档**：README 新增「tmux 长期会话」一节，含同一套命令、退出码取法与本插件场景下四个限制（禁 attach / PATH 不全 / 无 cwd env 参数 / 会话名靠约定），供人查阅
- **无行为变更**：仅说明文本与文档，不改执行链路；`python -m py_compile` 通过

### ✨ 新增 chrome-classics v1.0.0：Chrome 热门主题移植（四套主题，两套带壁纸）
- **来源**：Chrome Web Store 主题分类榜单（`chromewebstore.google.com/category/themes`）+ 主题详情页安装量。经 CRX 下载（`clients2.google.com/service/update2/crx`）剥离头部解 zip，读 `manifest.json` 的 `theme.colors` 原色值与 NTP 壁纸
- **四套主题**：`slinky-grey` 斯林基·中性灰（上游 Slinky Elegant，900K/★4.5，零彩色只靠灰阶）、`amoled-black` 真黑·AMOLED（Into The Black Hole，600K/★4.6，`#000` 底靠 4~9% 白叠加建层次）、`shaded-purple` 紫雾（Shaded Purple，100K/★4.7，含原壁纸）、`forest-sunset` 森林日落（Forest environment，100K/★4.4，1920×1080 插画）
- **背景图**：`shaded-purple` / `forest-sunset` 从上游 NTP 壁纸生成 `scene.jpg`（长边 1600，JPEG Q88）与 `sidebar.jpg`（居中竖裁 1:4 → 480×1920，森林加高斯模糊 0.6）。两套纯色上游无壁纸，只用纯色层
- **关键坑（已规避）**：`design_tokens._COLOR_ALIASES` 把 `accent`/`text_primary`/`selected_bg`/`hover_bg` 当作别名**来源**，故 yaml 里写 `text_accent`/`text_secondary_hover`/`tab_active_bg`/`tab_hover_bg` 全部静默失效（白名单里有名但不会被读）；`input_glow_preset` 在 `refresh()` 第 4 步会覆盖同名单个发光 token，写 preset + 自定义值等于自定义值无效。本插件因此不写 preset，直接写六个 `input_glow_*` 强度值
- **验证**：`validate_plugins.py` OK；yaml 解析 + 颜色格式 + 图片存在性 + int token 未加引号全过（105 token/套，零死 token）；PySide6 离屏渲染四张预览图确认卡片/描边/输入框层次可分辨；`generate_marketplace.py` 已收录（218 插件）

### ✨ 新增 showcase v1.0.0：成果展示工具（模型主动把文件/图片推成果栏）
- **形态**：纯 `tools` 插件，零 UI 组件。宿主侧 `ToolResult.artifacts` 即自动挂消息卡片成果栏（`app/widgets/inline_artifact_panel.py` 五类 kind 分控件渲染），无需声明 `ui.artifacts.show`
- **工具**：`showcase(paths, caption?)` — `paths` 支持混合文件与目录（目录递归只收图片/视频/网页/文本这些可预览扩展名，避免把代码仓库推上成果栏）；单文件时 `caption` 落到条目上；单次上限 50 项（对齐 `normalize_artifact_items` 落库上限），超出提示剩余数量
- **与 workbuddy `present_files` 的差异**：后者只把清单渲染进正文并写自有 `_state` 面板，不走宿主成果栏；本插件直接产出 `artifacts` 条目，图片有缩略图、条目可单击预览/双击打开/拖拽导出
- **降级**：老宿主无 `artifacts` 字段时 `TypeError` 兜底，退化为正文列出路径，不失败
- **验证**：`plugins/showcase/tests/test_showcase_tool.py` 10 组用例（单图带说明/目录递归去二进制/绝对路径/缺失/空参/上限截断/预览摘要闭包/schema/register 契约）全过；`test_showcase_load.py` 经宿主 `PluginToolLoader.load_plugin_tools` 真实加载，注册为 `plugin:showcase`、danger=safe、schema 进入工具列表；`validate_plugins.py` OK；`generate_marketplace.py` 已收录

### ✨ jimeng v1.2.0：成品与登录暂存改落 `plugin_data`，不再写插件安装目录
- **改动**：`tools/jimeng.py` 的路径根由 `<app_data>/plugins/jimeng` 改为 `<app_data>/plugin_data/jimeng`（函数 `_plugin_dir` 更名 `_data_dir`），成品默认落 `plugin_data/jimeng/generated/`，登录暂存落 `plugin_data/jimeng/pending_login.json`
- **原因**：插件安装目录随升级/重装被覆盖，可能只读；成品属于用户数据，按项目约定应放 `plugin_data/<name>/`
- **同步**：`_workdir()` 回退目录、`download_dir` 参数 schema 描述、README 两处路径说明
- **验证**：pytest 48 例全过；`validate_plugins.py` OK；`generate_marketplace.py --check` 一致（jimeng 1.2.0）
### ✨ jimeng v1.1.0：登录全程自动化（傻瓜式）
- **login 一条龙**：调 `action=login` 即自动调起系统默认浏览器进入授权页（`webbrowser.open`，跨平台），并原地阻塞等待授权完成（CLI `--poll=120`），成功直接返回登录结果；验证码已随链接自动带上，用户只需登录+点同意
- **超时续接**：120s 未完成返回 pending，再调 `login` / `checklogin` 继续阻塞等待（`checklogin` 默认 poll 30→120）；仅无桌面会话导致浏览器调不起时才降级为手动打开链接
- **工具 schema 写明触发场景**：画图/海报/插画/视频/动画/放大图片及即梦、Dreamina、文生图、图生视频、seedance 等关键词
- **SKILL.md 瘦身**：删除登录操作说明（工具层全自动），仅保留一行兜底；「常见错误」表同步
- **验证**：pytest 48 例全过（3.13）；实测真实授权链路（浏览器拉起 → 登录 → 点同意 → 阻塞返回成功）
### ✨ code-animation-styles：新增插件图标
- **来源**：即梦 text2image，5.0Pro（2k，1:1），提示词为「深蓝→紫罗兰磨砂渐变圆角方形 + 白色代码括号与贝塞尔动画轨迹三球」，4 张备选选构图最规整者
- **处理**：System.Drawing 裁中央方形（避开左上角「AI生成」水印）→ 256×256 高质量缩放 → 圆角透明（半径 22.6%），light/dark 同图
- **manifest**：补 `icon` 字段（light/dark）；v0.1.1 换用 5.0Pro 重生成图标（初版 5.0 默认模型质感不足且水印入画）
### ✨ 新增 code-animation-styles v0.1.0：341 种代码动画风格提示词库（纯技能形态）
- **内容**：十大系列 341 种风格提示词（AG 代码样片 26 / M 动态风格 40 / K 卡通画风 38 / Z 中国风 15 / H 现成版式 12 / L Lemo-Opuscar 59 / V mg-styles-15 15 / X code-video 31 / R 照参考学来的 7 / O 奥斯卡 98 部 98），193 种带静帧 jpg；附离线挑选页 `风格挑选.html`（自包含，双击即用）
- **形态**：纯技能插件（仅 `skills` 组件）。`SKILL.md` 只留路由面（触发/第一动作/渐进加载/边界硬停止），工作流契约（每步输入/输出/转移条件/失败路线）下沉 `references/workflow.md`，提示词详略分寸与公共函数内联规则在 `references/prompt-craft.md`，触发评测（正反例 + 2 真实任务 + 1 UI 动效边界任务）在 `evals/trigger-eval.json`
- **数据资产自包含于技能目录**：`skills/code-animation/styles/`，AI 检索入口为 `styles/INDEX.md` 全量索引（341 条：编号/名称/适合/关键词/静帧标记）；M 系列 8 个风格上游文件名即无名称（如 `M14_.md`），INDEX 按编号收录
- **来源与许可**：内容源自社区开源整理（含 Lemo-Opuscar / mg-styles-15 / code-video 三个 MIT 项目），来源说明与第三方 LICENSE 原样保留在 `styles/许可与来源.md`、`styles/第三方许可/`；原作者约定「免费使用、禁止包装成课程/付费 skills 出售」已在 README 完整保留，本插件免费分发
- **数据处理**：从夸克网盘分享包（74.6 MB）提取，剔除 `示例/` 下三个演示 mp4（约 60 MB，AI 用不到），插件体积 14 MB
- **验证**：`validate_plugins.py`（Python 3.10）216 插件通过，本插件 OK；`generate_marketplace.py` 重新生成 marketplace.json（216 条）

### 🗑️ 移除 designkit 插件（服务端封锁第三方 MCP 客户端，实测不可用）
- **症状**：插件启用后连接报 `401 Unauthorized`，端点 `https://designkitmcp.designkit.com/mcp/workbuddy` 返回 `WWW-Authenticate: Bearer resource_metadata=...`
- **实测结论**：`/.well-known/oauth-authorization-server` 声明了 `registration_endpoint`，但 `POST /oauth/register` 对任意 client metadata 一律 `400 invalid_client_metadata`（试穿 12 种 body 组合 + 6 种 UA 伪装）。对照 `POST https://mcp.canva.com/register` 同参数返回 `201` 签发 client_id，排除客户端实现问题。`token_endpoint_auth_methods_supported` 仅 `["none"]`、无 `client_credentials`，token 只能由服务端白名单里的 client 走浏览器授权码流程签发
- **另一条链路**：WorkBuddy 自己的 designkit 连接器不走该 MCP 端点，走 `npm install -g meitu-designkit-cli` + designkit 自有 gateway（`~/.workbuddy/connectors-marketplace/connectors/designkit-buddy-cli/cli.json`），两条独立的授权链
- **移除内容**：删除 `plugins/designkit/`（manifest / `.mcp.json` / README / icon / 内置 3 个 skill 文件）；`downloads_cache.json` 剔同名条目；`marketplace.json` 重新生成（212 → 211）
- **验证**：`validate_plugins.py` 211 插件全过；`generate_marketplace.py --check` 一致
### 🔧 voice-input v0.6.2：修 macOS 结束录音必闪退——autorelease pool 跨事件持有触发 badPop

- **症状**：macOS 上点麦克风能正常开始录音（浮窗计时正常），点结束的瞬间整个 Drifox 闪退，Python 日志无任何异常栈
- **根因**：`ui/recorder_mac.py` 把 `NSAutoreleasePool` 作为实例字段跨事件持有（`start()` 建池存 `self._pool`，`stop_and_save()` 才 drain）。objc 的池是栈式的，Qt 每个事件派发结束都会 pop 自己的池，位于其上层的本池被连带销毁；下一次事件再 `drain` 就走到 `AutoreleasePoolPage::badPop` → `_objc_fatal` → SIGABRT。崩溃报告栈指纹：`_CFAutoreleasePoolPop → -[NSAutoreleasePool drain] → badPop → _objc_fatal → abort_with_reason`，faulting thread 为 `com.apple.main-thread`（主线程，故整个 App 挂掉）
- **修复**：新增 `_autorelease_pool()` 上下文管理器，池与 objc 调用同同步块进出；`start()` / `close()` 各自开池，删除 `_pool` 字段；`stop_and_save()` 改为先 `close()`（内含 stop + release）再打日志，不再有裸 objc 调用在池外
- **回归测试**：新增 `tests/smoke_recorder_mac.py`，在子进程内用 objc 手工 push/pop 池模拟 Qt 每事件语义，跑 3 轮「开始 → 200 次事件 → 停止 → 200 次事件」，同时断言 WAV 头为 16000Hz/1ch/16bit 且数据区非空（防「不崩但录空」的假通过）；非 macOS 或未授权麦克风自动 skip
- **验证**：修复前 `exit=-6`（SIGABRT，stderr 打印 `Invalid or prematurely-freed autorelease pool`），修复后 3 轮全绿；另做 5 轮压力测试（每轮穿插 600 次事件）零崩溃；录音数据有效性实测 3.24 秒录得 104778 字节、时长 3.15s、头 16000Hz/1ch/16bit，与预期 103635 字节吻合；`validate_plugins.py --strict` 中 voice-input 为 OK，`generate_marketplace.py --check` 一致
### ✨ git-panel v2.3.0：AI 生成按钮生成中变停止按钮，可点击取消（原禁用无反馈）
- **改动**：`ui/cards.py` AI 生成启动后按钮切 `FluentIcon.PAUSE` 停止图标（原 `setEnabled(False)` 静默禁用，视觉上卡住不动），tooltip 提示「点击停止」；再次点击触发 `_on_ai_cancel`
- **取消链路**：`_AIGenerateTask` 新增 `cancel()`：置位取消事件 + 对活跃 `EngineSession` 调 `cancel()`（宿主契约：turn 随后以 cancelled=True 返回，非阻塞）
- **run 循环改造**：整段 `done.wait(150s)` 改 0.2s 分段轮询，等待期间发现停止立即 `session.cancel()` 打断；重试退避 `time.sleep` 改 `Event.wait`（停止立即生效，不再白等退避秒数）；取消后一律静默 return，迟到结果不回填输入框、不弹错误条
- **验证**：插件 30 例测试全绿；pyright 零新增报错
### ✨ magpie v0.6.0：入口从标题栏常驻 tab 收拢到侧边栏「自定义插件」分组
- **改动**：`ui/__init__.py` 删 `register_titlebar_tab`，改 `register_sidebar_item(group="custom", card_id="magpie:web")`；full 卡与命令 `/magpie:web` 不变；已注册独立 sidebar 项，宿主跳过该卡侧栏兼容派生（`sidebar_plugin_names` 优先），不重复列条目
- **假死自愈保留**：webview 原生化「状态可见、容器不可见」死锁与入口无关，手写 on_click 的自愈探测（先 hide_card 清假状态再 toggle）原样搬到侧栏回调（签名 `(_context)`，对齐 sidebar 回调约定）
- **命令去重**：floating card 与 sidebar item 同 id "magpie:web" 各登记一次命令，账本保首个（card 语义，带 per-window context），无漂移
- **验证**：桩测试 smoke_ui_full_card.py 改断言侧栏注册（item_id/group/card_id/on_click 触发 toggle）通过
### ✨ 新增 13 个专家智能体插件（243 个 @智能体，源自 WorkBuddy 专家市场）
- **专家插件**：experts-tencent / product / engineering / data / finance / marketing / content / sales / ops / quality / legal / consulting / game（按 WorkBuddy 15 分类拆包，campus 与 global 两分类上游 prompt 全缺故未建）
- **数据源**：expert_center.json（429 个专家清单）公开可下；prompt 文件 243 个成功（`baseUrl+/plugins/<plugin>/agents/<name>.md`），185 个上游 COS 404（清单先行、内容未上线，含腾讯专区 9 个），各插件 README 已附缺失名单，待上游补全后重跑 `.test/build_experts.py` 同步
- **形态**：每个专家 = `agents/<name>.md`（frontmatter name/description 原样保留，@ 名按文件名全局去重）；精选场景 27/30 个专家已随分类入库
- **验证**：validate_plugins 全量 205 插件通过
### ✨ 新增 10 个远程 MCP 连接器插件（源自 WorkBuddy 连接器市场）
- **插件**：canva / designkit / fosunwealth / futu-mcp / kdocs / kling-ai-plugin / moomoo-mcp / slack-mcp / tiktok / tripo-3d
- **来源**：WorkBuddy 连接器市场整包（download.codebuddy.ai/connector-agent-plugins/connector-plugins.zip），逐个提取 mcp.json 端点、plugin.json 描述/示例与 ai.workbuddy/assets 图标
- **形态**：统一远程 streamable HTTP MCP（`type: http`），`enabled: false`，用户在设置 → MCP 连接器手动启用
- **认证**：canva / kdocs / slack-mcp / tripo-3d 走 `auth.oauth`；designkit / fosunwealth / futu-mcp / kling-ai-plugin / moomoo-mcp / tiktok 直连（首次使用按工具返回指引授权）
- **技能**：8 个插件随包内置 11 个服务方 AI 技能（canva / designkit / fosunwealth / futu-mcp / kdocs×1 / kling-ai×3 / moomoo-mcp / tripo-3d×2，含 kdocs 569 文件 references 全量 API 指引），manifest 补 `components.skills: true`；frontmatter 扫描确认无 WorkBuddy 专有工具引用
- **验证**：validate_plugins 191 插件全过；marketplace.json 重新生成（顺带修正 jimeng 版本漂移 1.0.0 → 1.0.1）
- **wecom-unified 不收录**：CLI 为 WorkBuddy 定制（a2a 构建依赖宿主网关，vendor 构建直连官方 API 但无 auth 子命令，token 由 WorkBuddy 云端凭其账号态签发，DriFox 下无授权链路）；待企业微信侧有可用凭证来源再评估
- **调研备注**：WorkBuddy 内置 sheetagent MCP 实测为假本地（依赖宿主 editorsdk 127.0.0.1:39099），未移植；市场内 dingtalk/feishu/wecom/tmeet 为 CLI 形态、github/notion/linear/edgeone-pages 库内已有对应，均不重复接入
### 🔧 token-usage v0.1.5：统计口径由「会话内增量」改为「全量求和」——原口径比真实账单小 93.5 倍
- **症状**：用量页签显示的数字远低于实际花费（用户反馈「少得太多，是不是没叠加」）
- **根因**：v0.1.4 采用「净占用/增量」口径，每轮 input 减去同会话上一轮 input。设计动机是 DriFox 每轮请求都会重发整个上下文，直接求和会把同一份上下文重复计几十次。但**服务商就是按全量计费的**，扣掉重发量后得到的「净新增输入」与账单不是同一个量级。实测开发库（590 会话 / 43145 次请求）：prompt 中位数 93K、p90 227K、单会话中位 43 轮，增量口径只保留全量的 1.07%
- **修复**：`ui/data.py` 的 `collect()` 改为每轮 `usage.input` 原样累加，删除 `prev_prompt` 增量基线与 `max(0, prompt - prev_prompt)` 计算。30 天窗口 input 由 18,909,091 升至 2,128,068,413（93.5 倍）；output 与请求次数不变
- **已知失真**（用户确认保留）：API 不返回 usage 时宿主回退本地估算并打 `estimated: True`（实测约 5000 条），这些记录同样计入统计，不做剔除
### 🔧 win-powershell v1.0.8：修超时只杀主进程致孙进程变孤儿，且收尸阶段白等 15s
- **症状**：设置 `timeout` 后超时的命令（如 `npm run dev`、`python -m http.server`）被判定超时，但其拉起的孙进程继续存活占端口与 CPU；且超时最坏要 20s 才返回，远超用户设定的上限
- **根因**：`subprocess.run(timeout=)` 超时时只杀 `pwsh` 主进程，Windows 无 POSIX 进程组语义，孙进程不在 kill 范围；收尸 `communicate(timeout=15)` 在孙进程杀不掉时等满 15s（5 + 15 = 20.1s），护栏退化成 `timeout + 15`
- **修复**：改 `Popen` + `communicate(timeout=)` 拿到 pid，超时时 `taskkill /PID <pid> /T /F` 连带杀树；收尸窗口从 15s 收到 2s（`taskkill` 是同步强杀，返回时杀树已完成，长等无意义），仍杀不掉的 detached 孙进程不再拖累返回；`FileNotFoundError` 捕获挪到独立 try；schema 的 `timeout` 补全默认 120、范围 1-3600 与连带杀树语义
- **实测**（宿主真实工具调用）：杀树生效 5.3s 返回且孙进程 `alive=0`；detached 孙进程杀不掉时 7.1s 返回（修复前 20.1s）、`alive=1`；正常路径 7 例回归全绿（正常输出 / 无输出 / 非零退出码 / stderr 混合 / 空命令 / timeout 夹紧 / 显式 timeout）；marker 文件确认孙进程确已启动，排除「压根没跑起来」的假阴性
- **排障中发现并修掉的引入缺陷**：`communicate()` 返回 `(None, None)` 时，原 `proc.stdout or b""` 兜底会把 `BufferedReader` 对象当字节下传，触发 `AttributeError`（`subprocess.run` 改 `Popen` 的连带效应，原模式永远拿到 bytes）
### 🔧 ssh-toolkit v0.3.0：修 paramiko 加密四件套全为 Windows 产物致 macOS 完全不可用
- **症状**：macOS 上插件无法做任何 SSH 操作。四个加密依赖浅层 `import` 假成功（顶层包 `__init__.py` 不触发原生扩展加载），深层使用时才炸：`nacl.bindings` 报 `No module named 'nacl._sodium'`、cryptography 报 `cannot import name 'exceptions' from '_rust'`、cffi 报 `Version mismatch`、bcrypt 目录整个缺失 → paramiko 完全不可用
- **根因（与前三个 gateway 插件同源，且更彻底）**：deps/ 公共路径混放 Windows 产物 —— `nacl/_sodium.pyd`、`cryptography/.../_rust.pyd` 均为 Windows PE；`_cffi_backend.cp314-win_amd64.pyd` 只在 `deps/win32/`（顶层 cffi 纯 Python 配不到正确 backend）；bcrypt 包目录**完全缺失**（manifest 声明了 darwin/linux 依赖但未 vendor，内容只在 `deps/win32/`）→ paramiko 的加密四件套一个都不可用
- **修复**：新增 `deps/darwin/`（bcrypt 5.0.0 universal2 / cffi 2.1.1 arm64 含 `_cffi_backend.cpython-314-darwin.so` / cryptography 50.0.0 arm64 Rust 扩展 / PyNaCl 1.6.2 universal2 含 `_sodium.so`）；顶层移走 Windows 版 `nacl/` `cryptography/` 及对应 dist-info；保留纯 Python 的 `cffi/`（配 darwin/win32 的 backend）、`invoke/` `paramiko/` `pycparser/`
- **附带修复**：`tests/conftest.py` 原硬编码只注入 `win32`，改为按 `sys.platform` 选当前平台目录优先（darwin/win32/linux），与宿主 `deps_loader` 同语义
- **实机验证**（模拟宿主注入顺序 `deps/darwin` 优先）：四件套深层加载全通；paramiko 5.0.0 加载成功；RSA 2048 密钥生成（过 cryptography/openssl 全链路）；Ed25519 签名验证（过 nacl/_sodium）；bcrypt 哈希（过 _bcrypt）。插件自带测试 47 例全绿（修复前因 conftest 硬编码 + bcrypt 缺失而大面积失败/INTERNALERROR）
### 🔧 gateway-dingtalk / gateway-discord：deps 按平台分目录 — 修顶层 Windows 产物 + 依赖残缺
- **症状**：非 Windows 平台装这两个网关插件后，平台注册不进 `GatewayPlatformRegistry`（表现为「配置 enabled=true 但日志只有『无启用平台』」）
- **根因（与 gateway-feishu `f1696ea8` 同源）**：`deps/` 是公共路径（所有平台都从这里加载），而仓库里提交的是在 Windows 上打包的产物 —— 顶层混放 `.pyd`，非 Windows 平台 import 时抛 `OSError: Cannot load native module`，插件模块加载失败
- **本次排查额外发现两类更严重的缺陷**（两个插件都有）：
  - **依赖残缺**：gateway-dingtalk 顶层 4 个包的**包目录完全缺失**，只剩 dist-info（`frozenlist` / `multidict` / `propcache` / `yarl`），其内容仅在 `deps/win32/` 里存在 → 任何平台（含 Windows）实际都跑不起来；gateway-discord 顶层的 `discord/` 是残缺纯 Python 部分（149 文件 vs `win32/discord/` 的 243 文件）→ 缺失的 94 个文件各平台都加载不了
  - **孤立 dist-info**：包目录不存在却留着 dist-info，会让宿主 `missing_pip_deps` 误判「依赖已就绪」（该函数按顶层同名目录存在与否判定）→ 自动安装被跳过，插件永久缺依赖
- **修复**（统一方案：顶层只留纯 Python，原生扩展按平台分目录）
  - gateway-dingtalk：新增 `deps/darwin/`（7 包 11 个 `.so`：aiohttp 3.14.3 / charset-normalizer 3.5.1 / frozenlist 1.8.0 / multidict 6.7.1 / propcache 0.5.2 / websockets 17.0.1 / yarl 1.24.5）；顶层移走 3 个含 Windows 原生扩展的包 + 4 个孤立 dist-info
  - gateway-discord：新增 `deps/darwin/`（7 包 9 个 `.so`：aiohttp 3.13.5 / audioop-lts 0.2.2 / discord.py 2.7.1 / frozenlist 1.8.0 / multidict 6.7.1 / propcache 0.5.2 / yarl 1.24.5）；顶层移走残缺 `discord/` 与 aiohttp + 5 个孤立 dist-info
  - 两者 `deps/win32/` 均原样保留
- **实机验证**（模拟宿主 `deps_loader` 注入顺序：`deps/darwin` 优先于 `deps/`）：两插件的全部依赖均解析到 `deps/darwin/`；C 扩展实测可用（`multidict._multidict` / `yarl._quoting` / `audioop.getsample`）；`dingtalk_stream` 与 `discord.py 2.7.1` 均正常 import
- **注**：`darwin/discord/bin/libopus-0.x{64,86}.dll` 是上游 `discord.py` wheel 自带的跨平台辅助文件（其 `opus.py` 在 win32 走 `bin/*.dll`、其他平台走系统 libopus），保留以与上游一致
- **Linux 支持说明**：两插件 manifest 均已声明 `dependencies.pip.linux`，由宿主 DepsInstaller 安装时自动补 `deps/linux/`（其 wheel tag 平台串台缺陷已由 DriFox 主仓库 `bbba3a30` 修复）。本次不改 Linux 因 deps 目录命名不含 CPU 架构（`deps/linux/` 装不下 x86_64 与 aarch64 两份 `.so`），需先扩展宿主约定
### 🔧 gateway-feishu v1.2.3：修宿主打包环境 TLS 校验失败致长连接从未建立 + 日志盲区 + 断线补偿
- **症状**：飞书机器人「发了没反应」。宿主日志显示 `[Base Platform] Started` / `[Feishu] Connected successfully (WebSocket)`，看起来一切正常，但进程 `lsof` 只有 localhost 两条连接、**零外部 TCP**；消息发出后 `[Gateway] Processing message` 一条不出现
- **根因（CA 验证失败，真因）**：DriFox 打包环境（PyInstaller）下 OpenSSL 默认 CA 路径解析失效，`wss://msg-frontier.feishu.cn` 在 TLS 握手阶段即挂，报 `[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate in certificate chain`。长连接从未建立 → 消息全丢。同源错误也命中宿主 `urllib`（Installer 上报下载量失败）
- **假信号（误导排查的关键）**：`connect()` 的 `self._connected = True` 在起 WS 线程后**无条件置位**，不校验真实连接结果；`[Base Platform] Started` 也只在 `connect()` 返回 True 后打，而 True 来自上述硬编码。故「连接成功」日志与「实际零连接」并存，误导排查方向（期间误判两轮：先归因依赖装错平台、再归因连接被测试实例挤掉）
- **修复一（CA 分层兜底）**：模块顶层 `_ensure_ca_bundle()` + `_ssl_context()` + `_patch_lark_ws_connect()`
  - 探测顺序：`SSL_CERT_FILE` 已设 → 尊重；默认 context 能加载证书 → 不介入；有 truststore → 用系统信任库（可解企业代理自签 CA）；否则回退 certifi `cacert.pem` 写 `SSL_CERT_FILE`（实测 121 张根证书，宿主打包环境自带 `Contents/Frameworks/certifi/cacert.pem` 可用）
  - lark SDK 的 `_ws_connect_kwargs()` 硬编码只返回 `{"proxy": None}`、不暴露 ssl 入口，故包装该模块级函数补 `ssl` 键（websockets 15 从 `**kwargs` 取 `kwargs["ssl"]`，见 `asyncio/client.py` 的 `setdefault("ssl", True)` 分支）
- **修复二（日志桥接，可观测性）**：插件原用 `logging.getLogger(__name__)`，而宿主日志系统只给 loguru 配 sink（无 InterceptHandler）→ `[Feishu]` / lark SDK 的 `[Lark] connect failed, err: ...` **一条都不落盘**，排查全程盲猜。新增 `_bridge_lark_logging()`：给 root logger 挂转发器，把 `Lark` 一族记录按级转入 loguru（DEBUG 保留，因 sink 级别为 DEBUG；降 TRACE 会被过滤）
- **修复三（被动断线补偿）**：lark SDK 的 auto_reconnect 只覆盖自身驱动协程内的重连窗口；驱动协程退出后 `start()` 返回、ws 线程结束、loop 关闭，而 `_connected` 仍为 True 无人复位 → 宿主停在「假连接」直到重启。新增 `_schedule_ws_reconnect()`（线性退避 2/4/6/8/10s，上限 `_max_reconnect_attempts`，可被 `_stop_event` 打断）+ 抽出 `_spawn_ws_thread()` 供首次连接与重连共用；`connect()` 重置退避计数
- **附带**：`_on_feishu_message` 三处链路打点（收到原始消息 / 消息待分发含 `handler_set`/`loop_running` / 已投递至宿主 handler），用于区分「WS 没收到」与「收到后 handler 丢失」
- **测试**：新增 `tests/test_feishu_host_selfheal.py` 12 例 —— CA 三分支（显式环境变量尊重 / 默认可用不介入 / 失效回退 certifi）+ truststore 优先分支；日志桥接（转发 / 级别保留 / 只转发 Lark 族不吸噪音 / 幂等）；重连（拉起新线程 / 尊重 stop_event / 达上限复位 `_connected` / connect 重置计数，末者走 AST 断言重置早于起线程）
- **实机验证**：修复后宿主日志出现 `[Lark] connected to wss://msg-frontier.feishu.cn/ws/v2?...` + `ping success` + `receive pong`（此前从未落盘），`lsof` 确认 `198.18.0.1:55730->198.18.0.148:443 (ESTABLISHED)`；发消息后完整链路贯通：`收到原始消息` → `消息待分发 handler_set=True` → `已投递至宿主 handler` → `[Gateway] Processing message` → `AI completed, response_len=59`
- **已知存量问题（未处理，非本次引入）**：`tests/test_gateway_feishu_lifecycle.py` 3 例失败（`test_disconnect_stops_ws_thread_and_loops` / `test_disconnect_is_idempotent` / `test_connect_defensive_cleanup_when_thread_alive`，报 `No module named 'lark_oapi'`）—— 把本次改动 stash 后基线同样失败
- **验证**：新增 12 例全绿；`tools/validate_plugins.py --strict` 中 gateway-feishu 为 OK；`tools/generate_marketplace.py` 一致性通过
### 🔧 project-dashboard v0.2.4：修「切到项目看板 tab 却显示会话内容」+ QThread 析构致命错误
- **症状**：欢迎卡片点「📊 项目看板」tab，body 显示的是会话列表；日志只有 `[project-dashboard] UI components registered`，`collect done` / `collect error` 从未出现
- **根因一（Python 模块名撞车，主因）**：宿主 `UIPluginRegistry.load_plugin` 把每个插件的 ui 目录逐个 `sys.path.insert(0, ...)`，后加载者排前面。本插件 `ui/__init__.py` 用顶层裸名 `from collector import build_cache_key`，而 token-usage（本机同期装）也有 `ui/collector.py` → 本插件拿到的是**对方的** collector（其 `build_cache_key()` 无参，本插件传 `project_root`）→ `TypeError` 冒到宿主 `_render_welcome_body` 的 `except Exception: pass` → 函数末尾回退 `_render_sessions_body` → 用户看到会话列表。全程零日志
- **取证**：照抄宿主加载顺序与 `str(Path/"ui")` 路径形式的最小夹具：`sys.path[0:2] = [token-usage/ui, project-dashboard/ui]`，`collector 解析到 = .../token-usage/ui/collector.py`，`build_cache_key 签名 = () -> tuple`，`render 抛 TypeError: takes 0 positional arguments but 1 was given`
- **根因二（QThread 析构 UB，潜伏）**：`start()` 把 `w.finished` 同时接到 `_on_done`（首行 `self._thread = None` → QThread 失去最后引用即刻析构）与 `t.quit`（异步生效，此刻 `exec()` 仍在跑）→ Qt `qFatal: QThread: Destroyed while thread is still running`，缓存写入等后续代码到不了。这是 token-usage 在 v0.1.3（`a9cd0d34`）修过的同一类坑，project-dashboard 未跟上
- **修复一**：`ui/__init__.py` 与 `ui/collector.py` 的本插件子模块引用全部改相对导入（`from .dashboard import` / `from .collector import`），并删除 `register_ui` 里的 `sys.path.insert(0, ui_dir)` —— 宿主 spec 按文件路径加载 `ui/__init__.py`，`submodule_search_locations` 自动带上 ui 目录，相对导入可用
- **修复二**：对齐 token-usage 的线程模型 —— ①采集线程退出改由 `worker.run()` 内 `QThread.currentThread().quit()`（先 quit 再 emit，`quit` 由本线程 exec 消费，线程安全）；②缓存写入/日志前移到 worker 线程的 `_finalize_collect()`（就地生效，不经跨线程信号）；③`_on_done` 降级为幂等兜底；④采集完成通知优先走 `UIEventBus(EV_WELCOME_TAB_REFRESHED)`（任意线程发布安全），回退分支加主线程守卫
- **回归测试**：新增 `tests/test_project_dashboard.py` 12 例 —— AST 断言禁止顶层裸名导入/禁止 `register_ui` 动 `sys.path`、`run()` 内 `quit` 必须早于 `emit`；模块解析断言（`collector`/`dashboard` 必须指向本插件）；撞车场景端到端（project-dashboard + token-usage 同载，render_func 不得抛异常）；`_finalize_collect` 无信号收尾；`worker.run()` 直调（等价信号投进死线程）后缓存仍就绪；`_scan_files` 跳过噪音目录；`build_options` 四宫格结构可 JSON 序列化
- **测试有效性**：注入 3 处变异（`from .dashboard` 还原为 `from dashboard`、`register_ui` 恢复 `sys.path.insert`、`quit` 挪到 `emit` 之后）全部精确打红，还原后 12 例全绿
- **实机/夹具验证**：修复前夹具 `TypeError` + 回退会话列表；修复后 `collector 解析到本插件`、`build_cache_key 签名 (project_root: str, ...)`、`render` 正常返回占位并在采集后出图（`CHART-OK`）；`_finalize_collect` → `_release` → `_on_done` → `run` EXIT 顺序无 Qt FATAL
- **已知存量问题（未处理，非本次引入）**：`dashboard.py` 的 `names`/`files` 两个未使用变量（ruff F841，基线即有）；`tests/test_context_stats.py` 6 例失败（干净基线同样失败）
- **验证**：`ruff check` 本插件无新增告警；`tools/validate_plugins.py --strict` 中 project-dashboard 为 OK；`tests/test_project_dashboard.py` 12 例 + `tests/test_token_usage.py` 68 例全绿

## 2.11.9 (2026-10-15)
### 🔧 token-usage v0.1.4：修热力图悬停提示超出可视区被裁剪
- **症状**：欢迎卡片「🔢 用量」tab 里悬停热力图格子，tooltip 被容器裁掉 —— 截图显示右侧近边缘列的提示右半截消失
- **根因（纯 CSS 伪元素无法测量自身几何）**：tooltip 走 `.tu-cell:hover::after` + `content:attr(data-tip)` 居中展开，伪元素测不到自身宽度，只能靠 `.tu-week:nth-last-child(-n+3)` 硬编码「右侧 3 列翻到左边」。但卡片宽度是动态的（主程序按 `parent_width - 20` 算，下限 320px），列宽随宽度变化，近边缘列（如截图中的第 51 列）仍在兜底范围之外 → 提示右半截溢出，被骨架的 `html{overflow:hidden}` 裁掉。左侧边缘列同样无兜底
- **取证**：离线探针逐列 hover 53 列并读几何 —— 旧实现全部走伪元素（`getComputedStyle(cell,'::after').width` ≈ 140-145px），右边缘仅 3 列翻转；用户截图被裁的列落在翻转范围之外，闭合证据链
- **修复（JS 自绘 + 视口双向钳制）**：`data-tip` 只存文案；`.tu-grid` 上加内联委托事件（`onmouseover` / `onmouseout`），驱动 JS 自绘的 `#tu-tip`（`position: fixed` 挂 `body`）。展示时 `getBoundingClientRect()` 实测格子与 tooltip 尺寸，左右用 `Math.max(4, Math.min(centered, innerWidth - w - 4))` 钳制、上方放不下则翻到下方、下方也超界则贴底 —— 侧边列、底行、窄窗口都不会溢出。删除旧的伪元素规则与 `nth-last-child` 硬编码
- **为什么用内联事件属性而非 `<script>`**：宿主经 `innerHTML` 注入插件片段，HTML 规范下 `<script>` 不执行（同 calendar 插件用 `onclick` 切月视图），故事件挂在 `.tu-grid` 属性上（一个属性覆盖全部格子，省 HTML 体积）。已验证内联属性含 `<`/`>`/`&&`/引号时穿过宿主 markdown→HTML 管线不被转义破坏
- **为什么用 `fixed` + `body`**：宿主骨架的 `html`/`body` 无 `transform`/`perspective`/`filter`（已核实），`fixed` 相对视口可靠；挂在 `body` 下则不被 `#content-placeholder` 的局部 overflow 裁切
- **回归测试**：68 例（原 66 + tooltip 新断言组）——新增 `test_tooltip_is_js_drawn_not_pseudo_element`（必须用 `#tu-tip`，禁止回退 `:hover::after` / `attr(data-tip)` / `nth-last-child`）、`test_heatmap_binds_delegated_mouse_events`（委托事件就位、片段内不得出现 `<script>`）、`test_tooltip_js_clamps_to_viewport`（必须实测 `getBoundingClientRect`/`offsetWidth`/`innerWidth` 且含 min/max 钳制）、`test_tooltip_js_hides_on_leave_and_on_non_tip`（mouseout 判据限定 `.tu-cell[data-tip]`，悬停非 tip 元素主动隐藏）；原 `test_tooltip_css_present` / `test_tooltip_edge_columns_flip_anchor` 换代为对应新断言
- **测试有效性**：注入 8 处变异（退回伪元素、去掉视口钳制、写死尺寸不实测、摘掉事件委托、mouseout 判据放宽、去掉 `pointer-events:none`、非 tip 元素不隐藏、配色占位符未填），8 处全部精确打红
- **实机验证**：①宿主同版本 QtWebEngine 5.15.2（Chromium 83.0.4103.122）离屏冒烟 —— 7 个采样列（含左右边缘）tooltip 全部落在视口内（左列钳到 x=4、右列钳到 `vw-4`），`fixed` 生效，mouseout 正确隐藏，无 JS 错误；②边界场景（模拟宿主 `updateContent` 整体替换 DOM）—— 重渲染后 tooltip 跟随新节点重新定位、离格隐藏、清空内容不残留；③playwright 53 列全量 hover，几何断言全部在视口内（`bad=0`）
- **验证**：`ruff check` 通过；`tools/validate_plugins.py --strict` 中 token-usage 为 OK；`tools/generate_marketplace.py --check` 一致

## 2.11.8 (2026-10-14)
### 🔧 token-usage v0.1.3：修打包版市场安装后用量页签永远卡「正在统计」
- **症状**：打包版 DriFox 里从市场安装 token-usage 后，「🔢 用量」tab 永远停在「正在统计 API 用量…」；日志只有 `[token-usage] 采集已启动`，永远等不到「采集完成」。开发版（插件随仓库加载/热重载）不触发
- **根因（QObject 线程亲和 + 死线程信号投递）**：`register_ui()` 尾部的预热 `start()` 在**市场安装 worker 线程**执行 —— 安装器用 `QTimer.singleShot(0, reload)` 触发重载，而 `QTimer` 归**调用线程**所有（安装 worker 线程有 `exec()` 事件循环，回调会执行但不在主线程）。于是 `_collector` 单例诞生在安装 worker 线程；采集 QThread 0.6s 跑完后 `finished.emit()` 是 queued 信号，投给 `_collector` 所在线程 —— 该线程任务完成后已 `quit()` 退出事件循环，**排队给死线程的事件永不消费**：`_on_done` 不执行 → 缓存永不写入、`_running` 永不清零 → 后续每次 `start()` 被 `is_running()` 拦截 → 页签永久加载占位
- **取证路径**：打包宿主日志「采集已启动」有、「采集完成/异常/错误」全无 → worker 线程 CPU 时间 0.625s ≈ dev 实测 0.79s，说明 `collect()` 正常跑完 → 断点在 emit 之后的信号投递环节 → 逆向安装器线程模型（`_MarketplaceWorker` moveToThread + `QTimer.singleShot` 归属）闭合证据链
- **修复**：数据就绪与信号投递解耦 —— ①缓存写入/日志/状态清理前移到 worker 线程的 `_finalize_collect()`（锁保护，就地生效，不经任何跨线程信号）；②采集线程退出改为 `run()` 内 `QThread.currentThread().quit()`（quit 线程安全，退出事件由本线程 exec 消费），不再依赖 `finished -> thread.quit` 的 queued 连接；③`notify_refresh()` 回退分支（直接摸 UIPluginRegistry）加主线程守卫，worker 线程触发时跳过（缓存已写好，下次打开页签 `get_cached()` 命中）；④`_on_done` 保留为幂等兜底（receiver 线程存活场景的重复通知，无害）
- **回归测试**：新增 2 例（66 例总数）——`test_finalize_collect_writes_cache_without_signal`（收尾函数就地生效，无 Qt 信号参与）、`test_worker_run_finalizes_even_when_signal_never_delivered`（同步直调 `worker.run()` 等价「信号投进死线程」极端场景，断言缓存命中 + `_thread` 清零 + `is_running()` False）。注入变异（删除 `_finalize_collect` 调用）精确打红
- **验证**：`ruff check` 通过；`tools/validate_plugins.py --strict` 中 token-usage 为 OK；`tools/generate_marketplace.py --check` 一致

## 2.11.7 (2026-10-14)
### 🔢 token-usage v0.1.0：欢迎卡片新增「🔢 用量」tab — 30 天四指标 + GitHub 风格年度热力图
- **版本**：v0.1.1
- **版式**：照 GitHub 个人主页贡献图设计 —— 顶部标题 + 右上「刷新用量」，面板内先「过去 30 天」四指标（总/输入/输出 Token、请求次数），分隔线下「每日活动」365 天热力图（按周分列、7 行 = 周一至周日）+ 色阶图例。**纯 HTML 网格，不依赖 echarts**（无图表 vendor 加载开销）
- **口径（增量，用户确认）**：输入 Token = 每轮 `prompt_tokens` **减去同会话上一轮**（首轮全额）；输出 Token = 每轮 `output` 之和；请求次数 = 带 `token_usage` 的消息条数。DriFox 每轮请求重发整个上下文，直接求和等于把同一份上下文重复计几十次（实测输入占比 99.4%，总 262M）；扣增量后输入占比降到 60.5%（总 3.8M / 输入 2.3M / 输出 1.5M），输入输出回到同量级。prompt 回退（上下文压缩后变小）按 0 计，不产生负数
- **数据源**：`sessions.messages` 里的**真实 API usage**（`token_usage.input/output`），而非 `sessions.context_usage`（本地估算，算不出输入输出拆分）。该字段是 zstd 压缩 blob（4 字节 magic `ZSTD` + 版本 + frame，见主程序 `app/core/store/serde.py`），本插件两种格式都兼容
- **异步采集**：全库解压扫描 476 会话 / 85MB 实测 0.6s，走 QThread（`collector.py`），主线程同步会卡 UI。首次打开显示「加载中」占位，完成后经 `UIEventBus.publish(EV_WELCOME_TAB_REFRESHED)` 触发卡片重渲染。error 结果带 60s TTL
- **db 路径探测**：优先问宿主 `app.utils.utils.get_app_data_dir()`（覆盖 `DRIFOX_DATA_DIR` / 开发态 / 打包态 / macOS 四条分支），再退回 `.drifox/sessions.db`、`~/.drifox/sessions.db`；候选库需含 `sessions` 表才算有效，避开同名空壳库抢占真实库
- **Chromium 83 兼容**（Qt 5.15.2 的 WebEngine）：不用 flex `gap`（间距走 margin）、不用 `aspect-ratio`（格子用 `width:100% + padding-bottom:100%` 撑正方形）、不用写死 px 列宽（列宽 `flex:1 1 0` 均分容器，卡片宽度是动态的 `parent_width - 20`，下限 320px）。月标签按「本月起始周 → 下月起始周」flex 跨度分配空间，窄容器（`@media (max-width:560px)`）隐藏「月」后缀只留数字，避免「10月11月」粘连
- **色阶**：按当日总 Token 的**分位数**分 5 档（抗单日尖峰，样本 <8 时退化为等距切分）。**明暗两版统一为「越深 = 越多」**（档1 最亮 → 档5 最深），暗色档5 与背景保持 2.3 倍亮度差避免沉进背景
- **刷新**：「刷新用量」挂 `.context-tag[data-type="tu-refresh"]`，经主程序 `dispatch_welcome_action` 派发回插件，丢弃缓存强制重采。旧主程序缺该扩展点时页签仍可用，只是刷新按钮无响应（有 warning）
- **回归测试**：`tests/test_token_usage.py` 64 例，覆盖 zstd/裸 JSON/损坏数据三种格式、增量口径（含基线按会话独立、压缩回退按 0、跨会话隔离）、缓存 TTL 与 staleness 判据、窗口补零、数字缩写、色阶分位与**方向单调性**（明暗两版均须越深越多，且档间亮度差 ≥15）、热力图周列对齐（周一起始、恰好 365 格）、CSS 有效性、tooltip 规则与配色。**已验证测试有效性**：注入 22 处回归（CSS 双花括号、口径退回全量、基线跨会话共享、prompt 回退负数、列宽/格子写死 px、暗色色阶退回半透明、色阶方向反转、档位沉底/挤叠、窄屏 media query 失效、zstd 解压失效、缓存读时重算 key、TTL 失效、invalidate 空转、tooltip 退回原生 title / CSS 丢失 / 配色未注入 / 拦截鼠标等），21 处精确打红，1 处为无效变异
- **踩坑记录 1（CSS 双花括号）**：CSS 模板最初写成 `.tu-wrap {{ ... }}`（f-string 残留写法）却配 `.replace()` 填充，双花括号从未折叠 → 整份样式表失效、页面全部退回浏览器默认样式，而字符串断言型测试完全查不出来。已补 `test_css_has_single_brace_rules` 锁死，并改用无头 Chrome 截图逐版核对
- **修复 1（永远卡在「加载中」）**：缓存 key 自相矛盾 —— `get_cached()` 读取时重算 `(db mtime_ns, 日期)`，而采集完成写入的 key 是那一刻的 mtime；对话持续写库使 mtime 不断变化，两次 key 永远不等 → 每次都判未命中 → 每次重起线程 → 采集完 mtime 又变，永远追不上。读路径改为只按 TTL（60s）判，db 变化交给新增的 `_is_stale()` 单独判断，写/读不再共用易变 key。诊断依据：日志里「采集已启动」有而「采集完成」无
- **修复 2（tooltip 在浅色下不可控）**：原先用原生 `title` 属性，由操作系统绘制，浅色主题下是黑底 + 系统默认大字号，且明暗跟随 OS 而非 Qt 主题。改为纯 CSS `::after` + `attr(data-tip)`，配色直接取自 context-stats 的 echarts `tooltip_bg` / `tooltip_border`，两插件观感一致；右边缘 3 列的 tooltip 翻到左侧展开避免被容器裁掉；`pointer-events: none` 保证不拦截点击
- **修复 3（暗色色阶方向反了）**：暗色版最初做成「越亮 = 越多」，与浅色的「越深 = 越多」语义相反（用户反馈「颜色反了，应该越深代表越多」）。改为明暗同语义：档1 最亮 → 档5 最深，两版亮度均单调递减（暗 174.8 → 69.2，浅 212.7 → 74.5）。深色底上有固有约束——越深越接近背景（#1e1e1e 亮度 30），一味求深会让用量最高的日子最不显眼，故档5 停在 #1f4a86（与背景差 39，约 2.3 倍背景亮度），档间亮度差保持约 25 以维持 5 档可分辨
- **踩坑记录 3（核对脚本自己出错两次）**：验证 tooltip 时，给全部 371 个格子加 force 类导致提示叠成一团；改选第 820 格则永远选不中（共 371 格）。最终改用页内 JS 输出 `getComputedStyle` 诊断到 DOM 再截图，确认 `content` / `position` / `backgroundColor` 全部生效才收工
- **验证**：`ruff check` 通过；`tools/validate_plugins.py --strict` 中 token-usage 为 OK；`tools/generate_marketplace.py --check` 一致（marketplace.json 已随 manifest 收录）

## 2.11.6 (2026-10-14)
### 🔊 voice-reply v1.4.0：朗读只读正文，剔除思考过程/工具结果/代码/机器串，上限 500 → 2000 字
- **动机**：原实现取 `card.get_plain_text()`，对助手卡片等价于 `content_to_text(..., include_tool_results=True)` —— 工具调用结果（`[tool:read_file] ...`）与代码片段被一起朗读；思考过程虽不在块列表里，历史消息/扁平文本路径仍可能混入。用户原话：「朗读的内容需要过滤，只朗读正文，并且需要进行内容过滤」
- **正文口径**：新增 `ui/tts_text.py`（纯函数、无 Qt 依赖），优先读卡片 `_content_data` 块列表，**只保留 `type == "text"` 块** —— `reasoning`（思考过程）、`tool_result`（工具调用与结果）、`custom`（echarts 等自定义渲染块）、图片块一律不进朗读。块列表不可用时退回 `get_plain_text()`，此时文本已混入工具结果，靠正则补刀（内联 `<think>…</think>` 整段删、`[tool:xxx]` 开头的行整行删）
- **清洗口径**（朗读器会把符号读成人话、把机器串读成乱码）：代码块整体替换为「代码略」提示音；行内代码去反引号、图片留 alt、链接留文字；粗体/斜体/删除线/标题/有序与无序列表/引用/分隔线/表格竖线去标记（新增删除线、有序列表序号、引用尖括号、分隔线、脚注引用）；裸 URL 与 data URI 删除（尾部排除中文标点，避免吞掉句末「。」）；超长 base64/哈希/路径串、HTML 标签、emoji 与装饰符号、控制字符删除；连续标点折叠为单个停顿
- **上限调整**：`_MAX_TEXT_LEN` 500 → `MAX_TEXT_LEN` 2000（`ui/tts_text.py`），原上限常把长回复切断在句中。`tts_engine.py` 超时注释同步（50 秒兜底对 2000 字仍宽裕）
- **空正文提示**：文案从「本条消息没有可朗读的文本」改为「…没有可朗读的正文」（只含思考/工具结果的消息现在会命中这条）
- **回归测试**：新增 `tests/test_voice_reply_tts_text.py` 19 例，覆盖块类型过滤（reasoning/tool_result/custom/image 不进场）、纯思考与纯工具消息为空、兜底路径的 think 段与 `[tool:]` 行补刀、URL/data URI/base64/HTML/emoji/控制字符清洗、markdown 结构标记清除、2000 字截断。已验证测试有效性：分别破坏「块类型过滤」「URL 清洗」「base64 清洗」「emoji 清洗」「think 段清洗」「工具行清洗」「引用标记清洗」共 7 个点，各自精确打红 1 例，恢复后 19/19 通过
- **验证**：`ruff check` 通过；`tools/validate_plugins.py --strict` 中 voice-reply 为 OK；`tools/generate_marketplace.py --check` 一致（marketplace.json 版本号已随 manifest 同步到 1.4.0）

## 2.11.5 (2026-10-11)
### ✨ voice-input v0.5.0：新增 macOS 录音后端，修 WAV 解析漏读填充块致时长统计失败
- **症状**：macOS 上点麦克风按钮无任何反应，日志报 `module 'ctypes' has no attribute 'windll'`
- **根因**：`ui/recorder.py` 全文件基于 Windows winmm（`ctypes.windll.winmm.mciSendStringW`）。`ctypes.windll` 是 Windows 专属属性，macOS 的 ctypes 无此符号，模块顶层绑定即抛 `AttributeError`，`ui/__init__.py` 的 try/except 接住后静默 return，按钮点了永远没反应
- **修复**：新增 `ui/recorder_mac.py` —— ctypes 直调 libobjc + AVFoundation 构造 `AVAudioRecorder`（16kHz/16bit/单声道，与 winmm 参数一致），零第三方依赖。不走 pyobjc 的原因：宿主 PyInstaller 只收集了 objc/Foundation/AppKit/CoreFoundation/Quartz，**AVFoundation 未打包**，`import AVFoundation` 必失败；ctypes 直调系统框架不依赖打包结果。`ui/__init__.py` 新增 `_make_recorder()` 按 `sys.platform` 分派（winmm 模块顶层绑 win 专属符号，非 Windows 必须绕开其 import）
- **附带修复**：`AVAudioRecorder` 会在 `fmt` 块前插 `JUNK` + `FLLR` 填充块，实测 data 块偏移到 4096 字节，而原 `wav_utils` 只读前 64 字节头 → 时长统计恒为「读取失败」。头部读取改 8192 字节，解析循环补「body 越界收尾」防死循环
- **重构**：WAV 头解析与电平统计抽到 `ui/wav_utils.py`（两端共用），`recorder.py` 从 206 行瘦到 99 行
- **macOS 权限前置**：TCC 麦克风授权由宿主 app 决定，缺 `NSMicrophoneUsageDescription` 时系统不弹窗直接拒绝、录音全程数字静音（peak=0）。插件侧新增授权状态探测与首次使用提示，被拒时抛带指引的 `RuntimeError`（宿主侧配套见主仓 build.py）
- **平台声明**：manifest 新增 `platforms: ["windows", "darwin"]`（Linux 未实现），市场卡片对不兼容平台置灰
- **回归测试**：新增 `tests/test_voice_input_wav_utils.py` 10 用例（标准 winmm 布局 / AVAudioRecorder 填充块布局 / 截断头不挂死 / 时长按实际文件大小 / 静音与信号电平 / 非 16bit 降级）。已验证测试有效性：把头部读取退回 64 字节后 2 例精确失败，恢复后 10/10 通过
- **验证**：`ruff check plugins/voice-input/` 通过；`validate_plugins.py --strict` 中 voice-input 为 OK；macOS 真机跑通 start → 1.2 秒 → stop_and_save 全链路（WAV 42996 字节、时长 1.2s、格式 16000Hz/1ch/16bit）

## 2.11.4 (2026-10-11)
### 🐛 webdav-backup v0.8.2：403 配额/限流被误报为「认证失败」，误导排查方向
- **症状**：坚果云上传返回 403，界面提示「认证失败(401/403)：请确认使用「应用密码」而非登录密码」，而凭证完全正常
- **根因**：`engine.py` 把 401 与 403 合并处理（`if e.status in (401, 403)`）并统一套用认证文案。坚果云在配额/限流类拒绝时返回 403 + `<s:exception>TrafficRateExhausted</s:exception>`（本周期上传流量超额），被错误归因到密码
- **诊断证据**：用磁盘真实凭证直连，PROPFIND/MKCOL/PUT/GET/DELETE 全链路通过；用真实备份大小（124MB）PUT 复现 403，响应体明确为 `TrafficRateExhausted`；云端 10 份备份合计约 900MB（免费版额度 1GB），且 `drifox-backup-20261011-093108.zip` 经 Range 读尾部校验确认是**上传中断的残包**
- **修复**：`WebDAVError` 新增 `detail`（响应体片段，保留 1000 字符）与 `dav_exception`（从 `<s:exception>` 抽取的 DAV 专有异常名）；`webdav.py` 抛错时填充两字段；`engine.py` 新增 `_describe_webdav_error()` 统一映射——401 才归因认证，403 按 `TrafficRateExhausted` / `OverQuota` 区分流量与空间，未知 403 带出服务器原文，507 归因空间不足。`run_test` / `run_backup` / `run_restore` / `run_list` 四条路径统一走该映射
- **回归测试**：新增 `tests/test_webdav_backup_error_map.py` 9 用例（异常名抽取、401/403/507/无状态码映射、旧构造签名兼容）。已验证测试有效性：在修复前代码上 9/9 失败，修复后 9/9 通过
- **验证**：`ruff check --select F,E9` 通过；`validate_plugins.py --strict` 中 webdav-backup 为 OK

## 2.11.3 (2026-10-11)
### 🔗 webdav-backup v0.8.1：设置卡新增「应用密码怎么拿」外链
- **动机**：坚果云必须用「应用密码」而非登录密码，原说明只是纯文字路径（账户信息 → 安全选项 → 添加应用密码），用户要自己摸索
- **改动**：`config_schema` 在「密码」字段后新增 `type: "link"` 字段，指向坚果云帮助中心官方图文教程 `https://help.jianguoyun.com/?p=2064`（第三方应用授权 WebDAV 开启方法）；密码字段 description 同步改为引导至该链接
- **范围**：`server_url` 输入框保留（Nextcloud / 群晖 / 自建 WebDAV 地址各不相同，删字段会把插件退化为坚果云专用）
- **验证**：经主程序 `parse_config_schema` 实测解析通过（9 字段，link 字段 url 合法）；`tools/validate_plugins.py --strict` 中 webdav-backup 为 OK

## 2.11.2 (2026-10-11)
### 🎛 webdav-backup v0.8.0：卡片重排为左右分栏，恢复现场迁入 `.drifox/restore`，收尾指引可视化
- **范围收窄**：移除「团队 / 项目 / 截图 / 本地备份」4 类备份选项（`config.py` 白名单同步删除，仅剩 8 类）；旧配置中的 `inc_teams` 等残留键不再被读取
- **布局重排**：英雄头下方独立工具条承载「立即备份 / 测试连接 / 刷新列表」（测试结果靠右、恢复后追加「重启 DriFox」）；主区改为左右分栏——左侧云端备份列表（区域内滚动，卡片高度不再随份数增长），右侧备份范围勾选改单列 + 额外包含 + 说明尾注
- **恢复现场迁出 temp**：统一落 `<数据目录>/restore/`——完成脚本 `restore-<ts>.bat`（原 `finish_restore-*.bat`）、待应用文件 `pending-<ts>/`、旧文件副本 `rollback-<ts>/`；`restore/` 目录显式排除出备份范围
- **收尾指引**：恢复存在被占用文件时自动用资源管理器定位脚本，并弹 `MessageBoxBase` 对话框给出三步编号指引、脚本绝对路径与回滚副本说明，按钮「打开所在文件夹 / 稍后再说」；弹窗失败时回退为状态行文字提示。新增 `engine.reveal_path()`（Win `explorer /select`、macOS `open -R`、Linux `xdg-open`）与 `engine.get_restore_root()`
- **验证**：`ruff check --select F,E9` 通过；离屏构造自检 20 项全通过（白名单 8 项、恢复现场常量、去 tempfile 化、卡片左右栏构造、对话框文本与按钮文案）；`tools/validate_plugins.py --strict` 中 webdav-backup 为 OK

## 2.11.1 (2026-09-15)
### 🐛 prompt-enhancer v0.3.0 / git-panel v2.0.1：修复密钥加密后插件拿到密文 API Key 导致 401
- **根因**：两插件直读 `~/.drifox/app.config` 的 `LLM.SavedProviders[*].API_KEY`。主程序引入 `SecretMode` 后，`password` 模式该字段是 `enc:v2:…` 密文、`keyring` 模式是空串（密钥已入系统凭证库），插件把密文当 Bearer token 发出 → `401 log in fail: Please carry the API secret key (1004)`。只有主程序内存态持有解密后的明文
- **修复**：改走宿主公开服务 `ctx["services"]["get_provider_config"](provider, model)`（主程序读内存态已解锁明文并叠加模型默认参数）；旧版主程序无此服务时回退遍历 `main_widget._valid_configs`（同为内存态）。删除磁盘取 key 路径 `_get_provider_config_by_name`
- **语义收紧**：显式指名的服务商不存在时返回空配置（不再静默串到当前会话模型）；判定改为「配置非空」而非「key 非空」，免鉴权服务商（如 OpenCode 免费模型，key 本就为空、由 `build_openai_client` 剥掉 Authorization 头）不再被误拒
- **配套（主仓）**：`app/main_widget.py` 新增 `_resolve_provider_config` 并注入 `services["get_provider_config"]`；`EngineHost` 契约同步该键；输入按钮 context 补 `services`（此前仅浮动卡有），`main_widget._on_plugin_input_button_clicked` / `UIPluginRegistry.invoke_input_button` 两条派发路径均已覆盖
- **验证**：新增 `tests/test_provider_key_channel.py` 8 用例（磁盘放密文 + 内存放明文，断言取到明文、显式服务商失效不串号、空 key 免鉴权服务商可受理）；在修复前代码上 8/8 失败（精确打出 `enc:v2:` 被当 key 的证据），修复后 8/8 通过；主仓 `tests/plugins/test_engine_host_contract.py` 契约守卫 12 用例通过，全量真实服务商探针 9/9 明文

## 2.11.0 (2026-09-13)
### ✨ voice-input 转纯云端双链：硅基流动免费优先 + MiniMax 备用，砍本地引擎（v0.4.0）
- **硅基流动接入（免费）**：实测 `Qwen/Qwen3-ASR-1.7B` 免费且中文识别带标点（官方定价页确认 Qwen3-ASR / XingChenASR 系列 / TeleSpeechASR / SenseVoiceSmall 全部免费）；`FunAudioLLM/SenseVoiceSmall` 免费通道当前限流严重（请求挂起不响应），模型名做成配置项默认 Qwen3-ASR 可随时换
- **worker 通用化**：`ui/minimax_recognizer.py` 重构为 `ui/cloud_recognizer.py` —— 硅基流动（OpenAI 兼容）与 MiniMax 专有接口协议同构（multipart 上传 + Bearer + `{"text"}`），差异仅 URL/模型名/Key，统一 `CloudRecognizeWorker` + `transcribe_wav` 纯函数；仍纯标准库 urllib 零第三方依赖，超时错误细分为「响应超时（可能限流）」
- **识别链架构**：`auto`（默认）按配置生成引擎链，头部失败自动转备用、本次录音不丢；`siliconflow`/`minimax` 单引擎失败即报错；配置 key 全缺时录音入口直接拦截提示
- **删除本地识别**：SAPI5（recognizer.py）与 Whisper（whisper_recognizer.py + tools/install_whisper.py）整体移除，zh 引擎强检逻辑随之删除，插件不再依赖任何本地组件
- **配置卡**：识别引擎三选项（自动/仅硅基流动/仅 MiniMax）+ 双 Key（`SILICONFLOW_API_KEY`/`MINIMAX_API_KEY` 环境变量可覆盖）+ 硅基流动模型名可配 + 两个获取 Key 外链
- **验证**：真实 key 走 `transcribe_wav` 全链路（硅基流动 Qwen3-ASR 返回带标点文本一字不差）；MiniMax 链路协议未变沿用 0.3.0 实测结论；plugin.json 合法、py_compile / ruff 过

## 2.10.0 (2026-09-12)
### ✨ voice-input 接入 MiniMax 云端识别，引擎设置可选（v0.3.0）
- **MiniMax 云端识别后端**：新增 `ui/minimax_recognizer.py`，上传 16kHz WAV 至 `POST https://api.minimaxi.com/v1/speech_to_text`（`asr-1.0`），带标点中文秒级返回；纯标准库 urllib 手写 multipart（宿主 PyInstaller 未收集 requests，插件零第三方依赖）；30s 超时兜底，网络/HTTP/JSON 错误全链路人话化
- **声明式配置卡**：plugin.json 声明 `config_schema`，设置页自动生成「语音听写配置」卡 —— 识别引擎 select（自动/MiniMax 云端/SAPI5）、API Key password（支持 `MINIMAX_API_KEY` 环境变量覆盖）、获取 Key 外链；配置走主程序 PluginConfigStore（`plugin_data/voice-input/config.json`），主程序零改动
- **引擎链重排**：`auto`（默认）配了 Key 即云端优先，失败（网络/401/额度不足）自动回退本地链（Whisper → SAPI5），本次录音不丢；`minimax` 强制云端（Key 缺失提示后回退）；`sapi5` 强制本地；纯云端模式不再强检本地 zh 识别引擎，无 SAPI5 中文引擎的机器也可用
- **验证**：真实代码路径 `transcribe_wav` 识别 TTS 中文音频 39 字全对带标点；无效 key → HTTP 401 → `RuntimeError` → 回退分支确认；plugin.json 合法、py_compile / ruff 全过

## 2.9.1 (2026-09-11)
### 🔧 网关消息分片自包含化 + loguru 日志占位符修正（qq v1.1.2 / wecom v1.0.1 / feishu v1.2.2 / slack v1.0.1 / dingtalk v1.0.1）
- **QQ/WeCom 发送崩于已下线的宿主基类方法**：主程序 `b6136c7a` 死代码剪枝移除了 `BasePlatformAdapter.truncate_message`（主仓库内无引用，调用方在插件仓库故未被识别），`QqAdapter._send_plain_chunks` 与 `WeComAdapter.send` 一调用即抛 `AttributeError`，QQ 群聊消息全量发不出去；现各网关自带 `_split_message`（优先按空行切段、单段超限硬切，与 feishu/slack 同名同风格），不再依赖宿主基类方法
- **日志占位符统一改 `{}`**：loguru 走 `str.format`，`%s` 不会被替换且参数被静默丢弃，真实异常与 HTTP 状态码全部丢失（如 `[QQ] replace flush failed: HTTP %s code=%s`）；本轮修正 qq 17 处、wecom 9 处、feishu 14 处、slack 5 处、dingtalk 2 处；dingtalk 保留的 2 处 `self.logger` 属 dingtalk_stream SDK 自带标准 logging，`%s` 是正确写法
- **验证**：桩 http client 端到端跑通 QQ 群聊长文本（10548 字 → 6 片 `[1772,1781,1774,1774,1774,1663]`，msg_seq 递增）与单聊超长兜底（`[1800,1800,1400]`）；10 组分片边界用例（空串 / 恰好上限 / 纯超长段 / markdown 代码块）满足不超限且不丢字；`ruff check` 通过

## 2.9.0 (2026-09-06)
### ✨ voice-input 识别引擎双后端：Whisper 优先，SAPI5 自动兜底（v0.2.0）
- **准确率瓶颈根治**：旧版全程走 SAPI5 dictation（Vista 时代离线引擎，中文听写字准确率仅 ~60–75%、无标点），属引擎天花板；新增 `ui/whisper_recognizer.py` faster-whisper 后端（CPU int8、固定 zh、VAD 裁剪、`initial_prompt` 引导简体中文与标点、关前文条件依赖防长音频幻觉），中文准确率提升至 ~90%+
- **双引擎自动切换不破会话**：`ui/__init__.py` 停止录音后按可用性探测（轻量 `find_spec`，不卡 UI）选择后端；Whisper 依赖缺失 / 模型下载失败 / 识别异常任一环节自动回退 SAPI5 并 InfoBar 提示，插件永不失效；浮窗新增 `set_status` 实时反馈「下载模型… / 识别中…」阶段
- **自包含依赖安装**：`tools/install_whisper.py` 一键把 faster-whisper 装进插件自带 `deps/`（desktop-automation 同款 `sys.path` 注入），pip 按宿主解释器自动挑选编译轮子 —— ctranslate2 4.8.2（cp314）/ av（abi3）/ tokenizers（abi3）/ numpy 2.5.2 实测解析通过；装完隔离子进程验证 import，卸载删 `deps/` 即可
- **模型首次自动下载 + 档位可配**：默认 small（≈460MB，CPU 实时率良好），缓存 `~/.cache/drifox-voice-input/`；`DRIFOX_VOICE_MODEL` 可切 tiny/base/medium，`DRIFOX_VOICE_WHISPER_DIR` 可改缓存目录；国内网络可设 `HF_ENDPOINT=https://hf-mirror.com`
- README / plugin.json 同步更新（v0.1.0 → v0.2.0）

## 2.8.6 (2026-09-05)
### ✨ quick-screenshot 右键隐藏主窗截图（v0.2.0）
- **右键按钮隐藏截图**：右键点工具栏截图按钮 → DriFox 主窗 `hide()` → 等 280ms DWM 合成刷新后 `grabWindow` 冻结底图 → 选区复制剪贴板 → 主窗自动恢复并抢回前台（`show`+`raise_`+`activateWindow`）→ InfoBar 提示；Esc/右键取消同样恢复，任何失败路径强制恢复主窗不留黑屏
- **主程序接口扩展**：`register_input_button` 新增 `on_right_click` 参数（同款 context），按钮右键走 `CustomContextMenu`+`customContextMenuRequested` 派发，不再弹系统菜单；插件侧 `inspect.signature` 检测降级，旧主程序自动回纯左键模式（tooltip 同步切换）
- **左键行为不变**：快速截图仍含 DriFox 窗口，遮罩内右键仍是取消选区

## 2.8.5 (2026-08-28)
### ✨ 新增 command-code 服务商插件（v0.1.0）
- **Command Code 聚合网关接入**：`providers/command_code.py` 注册 `Command Code` 服务商，走 OpenAI 兼容协议（`https://api.commandcode.ai/provider/v1`），Bearer 鉴权，把 Claude / GPT / Gemini / DeepSeek / Kimi / GLM / MiniMax 等主流与开源模型统一接入 DriFox 模型选择器
- **family 走系统 openai-family**：同 OpenRouter 聚合网关模式，无需自定义 model_adapter；`family="commandcode"`、`auth_type="bearer"`
- **内置精选模型列表**：默认 `deepseek/deepseek-v4-flash`，含 Claude / GPT / Kimi / Gemini / MiniMax / MiMo 等代表性 ID；完整模型以官方 `cmd --list-models` 或 `GET /provider/v1/models` 为准（大小写不敏感，支持 `company/name` 与短名）
- **图标**：命令提示符风格 `icon.svg` / `icon_dark.svg`；`marketplace.json` 经 `generate_marketplace.py` 重新生成收录（零 error/warning）

## 2.8.4 (2026-08-23)
### 🔧 修复 chinese-chess 棋子视觉与 LLM 调用四连击（v0.2.1）
- **棋子周围方框**：PyQt5 QSS 的 `border-radius` 只裁剪 `background`、不裁剪 `border`，`WA_StyledBackground=True` + `setStyleSheet(border: ...)` 让方形外框叠在自绘圆形之上 → 改 paintEvent 全自绘（公共函数 `_draw_piece_circle`，`PieceLabel` 与 `_GhostPieceLabel` 共用），关闭 `WA_StyledBackground`，弃用 QSS
- **棋子上文字过小**：`_refresh_style` 计算了 `font_px=int(cell*0.46)` 但漏 `setFont`，painter 拿到 QPainter 系统默认字号（13-15px），比预期 24-28px 小一半；补 `setFont(bold + pixelSize=font_px)`
- **LLM 始终空响应（reasoning 模型截断）**：`max_tokens=500` 对 reasoning 模型 MiniMax-M3 太小，`reasoning_tokens=499` 占满预算、答案被截为 `finish_reason=length`；提到 `max_tokens=2000` 留余量
- **SYSTEM_PROMPT 未禁止 <think>（对比 prompt-enhancer）**：prompt-enhancer `DEFAULT_ENHANCE_PROMPT` 明确写"不要输出 <think> 等思考过程内容"，chinese-chess 之前没提；新增第 3 条要求（模型未必遵守，靠 `parse_move` 的 `<think>` 剥离逻辑兜底）
- **验证**：`tests/` 133 个全过；用 DriFox `.drifox/app.config` 真实 MiniMax-M3 跑全链路（`start_ai_move` → `_AIMoveTask.run` → 真实 chat.completions.create），两次都返回合法走法（`马2进3 (1,0)→(2,2)`、`炮2平5 (1,2)→(4,2)`）

## 2.8.3 (2026-08-23)
### 🔧 修复 autoloop 配置卡项目路径预填（v1.0.1）
- **打开时默认项目路径未用当前上下文**：`AutoLoopConfigCard.showEvent` 仅在路径为空且 `ctx` 含 `project_root` 时预填，来源单一（缺 `get_workdir`/`cwd` 兜底）且预填值会残留、不随当前上下文刷新；现改为按 `project_root → services.get_workdir → os.getcwd` 三级取当前上下文路径预填，并引入 `_path_user_edited` 标志：未手动编辑时每次打开刷新为当前上下文路径，手动改过则尊重用户选择不再覆盖

## 2.8.2 (2026-08-19)
### 🔧 修复 workbuddy 插件 plan 模式与 UI 产物面板（v1.0.1）
- **plan 阻断失效（大小写根因）**：`ToolExecutor` 注入 hook context 的 `tool_name` 是 Claude Code 风格（PascalCase `Edit`/`Write`/`MultiEdit`/`BgStart`），而 hook 用小写匹配 → 永匹配不上，进入 plan 后仍可编辑；改为归一化（去下划线+小写）后比较阻断清单，单测通过（MultiEdit/BgStart→block，Read/无标记→放行）
- **`wb_plan` 报 `setdefault` 不存在**：`_state.py` 补 `plan_set/plan_get/plan_clear`（模块属性持久化），替换误用 setdefault
- **UI 产物面板未加载（导入崩溃被吞）**：`artifact_panel.py` 顶层 `_TYPE_ICON` 用到 `FluentIcon.PRESENTATION`/`SHEET`（qfluentwidgets 无此枚举）→ 导入抛 AttributeError 被 `register_ui` 吞掉 → 静默未注册；改用 `PROJECTOR`/`ZIP_FOLDER`，注册验证通过

## 2.8.1 (2026-08-18)
### 🔧 修复 browser 插件弹窗与拦截五项问题（v1.4.0）
- **历史弹窗透明**：`panel_base.apply_panel_theme` 修复 —— `dialog_style` 只给 `QDialog` 设背景，卡片内嵌 QFrame 面板无背景变透明；现按 objectName 追加 `QFrame#xxx` 容器背景（surface + border + 圆角），并统一 QLineEdit 样式（历史搜索框）
- **弹窗格式统一**：收藏/下载面板由 QDialog 独立窗口改为与历史面板同款「卡片内悬浮 QFrame 弹窗」（460×320，菜单按钮下方定位，三面板互斥显示、resize 同步重定位）
- **拦截开关失效（热重载根因）**：旧代理函数顶层 import 冻结旧模块的 ConfigStore 单例（永不读盘）→ 设置弹窗改开关无效；修复为 ① 代理调用时按 sys.modules 动态解析当前 `redirect_config`，② `install_redirect` 热重载时**接管**旧模块遗留代理（webbrowser.open / QDesktopServices / os.startfile / TerminalTools.execute_bash 四入口，从旧代理 stash 属性/`__globals__`/闭包取回原始函数后重绑），开关保存即生效
- **拦截配置收敛**：`intercept_system` + `intercept_shell` 合并为 `intercept_web`（拦截打开网页，全入口统一），与 `intercept_html`（拦截打开本地 HTML）构成两类语义开关，旧配置文件自动迁移；设置弹窗同步改为 3 开关
- **拦截设置卡片配色**：原硬编码深色背景/浅字（浅色主题下全黑），改为 `theme_colors` 深浅主题自适应
- **「在外部浏览器打开」回环修复**：该按钮原来走 `os.startfile`（已被拦截 patch）→ 又被拦回内置浏览器；新增 `external_open.open_url_external` 通过代理 stash 取回原始入口绕过拦截
- **验证**：拦截决策/配置迁移逻辑自测 + 热重载接管仿真测试（四入口接管、关掉拦截直达原始函数、幂等安装、防回环）全部通过；ruff 零告警

## 2.8.0 (2026-08-16)
### ✨ 新增 dsh-router + dsh-super-injector 插件（dsh-routing-suite 迁移）
- **`dsh-router`** — 任务感知思维模式路由（源自 dsh-router-standard，MIT）：build/fix 行为带划分（spec/react/mixed/weak + 关键词正则分类）、persona 选择、引导注入；components = commands + agents + skills
- **`dsh-super-injector`** — 运行时注入观测（源自 dsh-super-injector，MIT）：会话审计记录 + 插件状态/自检工具；components = hooks + tools
- **机制**：`marketplace.json` 重新生成（收录 dsh-router 与 dsh-super-injector），两插件均通过 `validate_plugins.py` 校验（零 error/warning）

## 2.7.0 (2026-08-15)
### ✨ 新增 codegraph-tools 工具插件 + tools 组件支持
- **`codegraph-tools`** — CodeGraph 语义级代码智能工具（`codegraph_explore`）：搜索 / 调用链 / 影响分析 / 索引管理，从 DriFox 主程序迁出（工具插件化），依赖 `codegraph-py` 库
- **组件体系扩展**：官方插件组件由 8 类增至 9 类，新增 **`tools`** 组件（`tools/*.py` 暴露 `register(registry)` 注册内置工具，由 `PluginToolLoader` 加载）
- **配套更新**：`schemas/plugin.schema.json` 支持 `tools` 组件；`tools/validate_plugins.py` 新增 `check_tools_dir` 校验（register 入口 + 语法）；`tools/generate_marketplace.py` 推断 `tool` 分类；`example-plugin` 补齐 tools/ui 组件成为 9 类完整参考；README / docs 组件清单同步更新
- **机制**：`marketplace.json` 重新生成（64→65 个插件），`codegraph-tools` 通过 `validate_plugins.py` 校验（零 error/warning）

## 2.6.0 (2026-08-13)

### ✨ 新增 laputa-fog 主题插件（DriFox 原生）

- **`laputa-fog`** — 浮岛·雾青主题：宫崎骏《天空之城》灵感浅色主题，灰蓝主调（`#5B7E8E`）+ 琥珀暖金点缀（`#C49A5C`），呼吸感光晕（`input_glow_preset: breath`），96 个颜色 token，显式声明 `mode: light`
- **专属背景**：聊天列表背景图 `laputa-fog_bg.jpg`（13% 透明度），随插件分发
- **机制**：`marketplace.json` 重新生成（63→64 个插件），`laputa-fog` 通过 `validate_plugins.py` 校验（零 error/warning），`/theme laputa-fog` 切换

## 2.5.1 (2026-08-13)

### 🔧 改进 context-stats 用量图表

- **`context-stats`** — 用量趋势图由「上下双面板」改为**单坐标系双 Y 轴**合并图：token 面积图（左轴）+ 消息柱状图（右轴）共享一条时间轴，一眼对比两组数据
- **数字缩写**：y 轴刻度与 tooltip 支持 `8M` / `1.2k` 形式（8000000 → 8M，去尾 `.0`）；因 echarts JSON 无法携带 JS 函数，采用 Python 侧按数据量级缩放 + 字符串模板 formatter 实现
- **测试**：`tests/test_context_stats.py` 增加缩写（`_fmt_k` / `_scale_unit`）与双轴结构断言，10 项全过

## 2.5.0 (2026-08-12)

### ✨ 新增 calendar 插件（DriFox 原生）

- **`calendar`** — 欢迎卡片日历 tab：Python 预渲染当月网格（周一起始 + 前后月补位 + 今天高亮），上/下月切换走 onclick 内联 JS（`innerHTML` 注入不执行 `<script>` 的约束），明暗配色 `prefers-color-scheme` 自适应
- **机制**：`marketplace.json` 重新生成（59→60 个插件），`calendar` 通过 `validate_plugins.py` 校验（零 error/warning）

## 2.4.0 (2026-08-12)

### ✨ 新增 ui-motion-skills 插件（社区生态）

- **`ui-motion-skills`** — UI 动效设计技能集，打包 [emilkowalski/skills](https://github.com/emilkowalski/skills)（MIT，28k★）全部 10 个技能，内容与上游保持一致：
  - 自动触发：`emil-design-eng`（核心哲学）、`animate`（从零构建动画）、`animation-vocabulary`（动效术语反查）、`apple-design`（Apple 设计原则）、`ask-sonner`（Sonner toast 指南）
  - 显式调用：`review-animations`（严格评审）、`improve-animations`（全库审计）、`find-animation-opportunities`（寻找动效机会）、`pick-ui-library`（UI 库选型）、`prototype`（多版本原型对比）
  - 含辅助文档：RECIPES.md / API.md / AUDIT.md / STANDARDS.md / PLAN-TEMPLATE.md / PICKER.md
- **机制**：`marketplace.json` 重新生成（56→57 个插件），`ui-motion-skills` 通过 `validate_plugins.py` 校验（零 error/warning）

## 2.3.0 (2026-08-11)

### ✨ 新增 minimax-h3 插件（DriFox 原生）

- **`minimax-h3`** — MiniMax H3 全模态音视频生成：文本/图片/视频/音频 → 带原生立体声音频的视频（768P/2K，4-15s）
  - `/minimax-h3` 命令引导完整流程（技能写提示词 → 提交任务 → 轮询 → 下载）
  - `scripts/h3_video.py` 三个子命令：create / query / download，支持 t2va / i2va / fl2va / ref2va 全部输入模式
  - `skills/h3-prompt-writing/` 搬运自 MiniMax-AI/MiniMax-H3（SKILL.md + base-en.txt + ref-en.txt），原样保留
  - API Key 从环境变量 `MINIMAX_API_KEY` 或 `~/.minimax/api_key` 读取（与 voice-clone 约定一致）
  - 合规声明：H3 技能内容遵循 MiniMax H3 Community License，生成内容受平台审核约束

## 2.2.0 (2026-08-08)

### ✨ 新增 voice-clone 插件（DriFox 原生）

- **`voice-clone`** — MiniMax 语音克隆：上传 10s+ 音频样本 → 克隆为永久 voice_id → 用克隆音色合成 TTS
  - `/voice-clone` 命令引导完整流程（采集样本 → 克隆 → 合成）
  - `scripts/voice_clone.py` 三个子命令：clone / tts / upload
  - API Key 从环境变量 `MINIMAX_API_KEY` 或 `~/.minimax/api_key` 读取（与 guizang-ppt-skill 约定一致）
  - 实测验证：上传 ✓、TTS 合成 ✓（克隆接口受账号权限限制，需开通 voice clone 权限的 key）
  - 授权提醒：仅克隆用户有权使用的声音，不得用于冒充或欺诈

## 2.1.0 (2026-08-08)

### ✨ 新增创意趣味插件（7 个，Claude 生态）

- **`algorithmic-art`**（Anthropic 官方）— p5.js 程序化艺术生成（流动场/粒子系统/种子随机）
- **`canvas-design`**（Anthropic 官方）— 设计哲学产出 PNG/PDF 海报视觉作品，内置设计字体库
- **`slack-gif-creator`**（Anthropic 官方）— 动画 GIF 生成（Slack 尺寸约束 + 校验工具，依赖 pillow/imageio）
- **`theme-factory`**（Anthropic 官方）— 10 套预设主题 + 即时生成新主题，给 HTML artifact 换肤
- **`web-artifacts-builder`**（Anthropic 官方）— 复杂交互式 HTML 构建（React + Tailwind + shadcn/ui）
- **`playground`**（Anthropic 官方插件）— 交互式 HTML 练习场（控件 + 实时预览 + 提示词复制）
- **`excalidraw-diagram`**（github/awesome-copilot）— 手绘风格图表生成（流程图/时序图/ER 图/思维导图 + 模板库 + Python 工具）

- **机制**：`marketplace.json` 重新生成（34→41 个插件），全部通过 `validate_plugins.py`（新增插件零 error/warning）

## 2.0.0 (2026-08-08)

### ✨ 新增 Claude Code 市场适配插件（6 个）

从 Claude Code 官方/社区市场适配高星插件，新增 DriFox manifest（保留上游 `.claude-plugin/plugin.json` 溯源）：

- **`superpowers`**（obra/superpowers，123k★）— 14 个工程工作流技能（TDD/调试/头脑风暴/写计划/代码审查/子智能体驱动开发），SessionStart 注入技能指引（DriFox 原生 Python hook）
- **`ecc`**（affaan-m/everything-claude-code，25k★）— 67 智能体 + 284 技能 + 94 命令的工程工作流全集
  - 所有命令补齐 DriFox 必需的 `type: prompt` frontmatter
  - 5 个 skill 目录名与 `name` 字段对齐；16 个多行 `>-` description 折叠为单行
  - hooks 未移植（上游为 node 内联脚本，强依赖 Claude 特有运行时）
- **`skill-creator`**（Anthropic 官方）— 技能创作/优化/评测完整流程（含评测脚本与基准测试）
- **`code-simplifier`**（Anthropic 官方）— 代码简化重构智能体（@code-simplifier）
- **`security-guidance`**（Anthropic 官方）— AI 生成代码安全审查；移植静态模式检查层（25 条规则），改写为 DriFox 原生 Python hook（PostToolUse 触发）；LLM diff 审查层未移植
- **`feature-dev`**（Anthropic 官方）— 功能开发工作流（/feature-dev + code-explorer/code-architect/code-reviewer 三智能体）

- **机制**：`marketplace.json` 由 `generate_marketplace.py` 重新生成（34 个插件），`validate_plugins.py` 全部通过（新增插件零 error/warning）

## 0.1.0 (2026-08-04)
### Added
- ip-switcher 插件：免费模型限流自动换 IP（429 检测 + 代理池轮换 + 仪表盘）
  - monkey patch openai SDK：白名单模型请求走本地代理池
  - 429 自动换 IP + 自动重试（默认 3 次，2s 退避）
  - 仪表盘浮动卡片：当前出口 IP、换绑历史、统计、手动换 IP
  - 代理池内置管理（shadow1ng/ProxyPool vendor 打包，sticky 模式）
  - 配置存 user-custom 插件（随云端备份恢复）

## 1.3.0 (2026-08-03)

### 🗑️ 移除 DriFox 运行时内置插件

- **背景**：`plugin-manager`、`plugin-marketplace`、`context-usage-stats`、`file-tree` 等插件已随 DriFox 运行时内置分发（`D:/work/DriFox/plugins/`），继续出现在插件市场中会让用户困惑（误以为需要额外安装 / 重复安装）。
- **移除内容**：
  - 删除 `plugins/plugin-marketplace/`、`plugins/plugin-manager/`、`plugins/context-usage-stats/`、`plugins/file-tree/` 四个插件目录
  - `marketplace.json` 同步重新生成，市场不再收录 DriFox 内置插件
- **机制保护**：
  - `tools/generate_marketplace.py` 新增 `DRIFOX_BUILTIN_PLUGINS` 名单，生成时跳过 DriFox 运行时内置插件
  - `tools/validate_plugins.py` 的 marketplace 一致性检查同步跳过内置插件
- **文档同步**：`README.md`、`plugins/README.md`、`docs/architecture.md`、`docs/plugin-development.md`、`plugins/git-dashboard/README.md` 更新插件索引与 ui 参考实现指引

## 1.2.0 (2026-07-01)

### ✨ 新增 ui 组件类型（第 8 类）

- **3 个 ui 插件**（官方 UI 三件套）：
  - **`plugin-marketplace`** — 官方插件市场浮动卡片 + 2 个内容块渲染器（`plugin_marketplace_grid` / `plugin_marketplace_card`），覆盖浏览 / 搜索 / 安装
  - **`plugin-manager`** — 插件管理浮动卡片，列出已安装插件并支持启用 / 禁用 / 卸载
  - **`context-usage-stats`** — 对话上下文用量统计浮动卡片，token / 消息量趋势 + 会话活跃度图表
- **Schema**：`schemas/plugin.schema.json` 新增 `components.ui` 字段
- **校验**：`tools/validate_plugins.py` 新增 `check_ui_dir()` — 校验 `ui/__init__.py` 存在 + `register_ui(registry)` 顶层函数
- **marketplace 生成**：`tools/generate_marketplace.py` 新增 `ui` 分类识别 + 统计类关键词（`stats` / `analytics` / `token` / `context` / `dashboard`）
- **文档同步**：
  - 根 `README.md` 与 `plugins/README.md` 7→8 类能力，组件覆盖矩阵新增 `ui` 列
  - `docs/architecture.md` 目录约定新增 `ui/` 段，加入「ui 组件」章节介绍 3 个扩展点 + 3 个官方 UI 插件参考实现
  - `docs/plugin-manifest.md` / `docs/plugin-development.md` / `CONTRIBUTING.md` 同步 7→8
- **CI**：
  - `.github/workflows/validate.yml` 新增 `auto-fix-marketplace` job：当 `generate_marketplace.py --check` 失败时自动修复
  - 触发场景：PR 推送 → push 回 PR head 分支；push main → push 回 main，保证 main 始终 green
  - commit 携带 `[skip ci]` 防止无限循环
  - 非 marketplace 漂移的失败：PR 留 comment，main push 让 job 失败（不污染 main 历史）
  - 加 `concurrency` 防止并发 PR 互相干扰

## 1.1.0 (2026-06-26)

### 🏗️ 基础设施完善

- **marketplace.json 迁移**：从 `.claude-plugin/marketplace.json` 移至仓库根目录 `marketplace.json`
- **自动生成**：新增 `tools/generate_marketplace.py`，从 `plugin.json` 自动汇总生成 `marketplace.json`，支持 `--check` 一致性检查
- **校验增强**：`tools/validate_plugins.py` 新增 `dependencies` 依赖校验 + `marketplace.json` 一致性校验
- **CI**：新增 `.github/workflows/validate.yml`，PR 自动校验（manifest + marketplace 一致性 + ruff lint + 文档链接检查）
- **社区文件**：新增 PR 模板 + Issue 模板（bug 报告 / 插件请求）
- **兼容性声明**：`evolver` 和 `example-plugin` 补充 `drifox.min_version` 声明
- **文档**：新增 `docs/marketplace-improvement-plan.md` 完善方案

## 1.0.0 (2026-06-26)

### ✨ 新增插件

- **git-workflow**：Git 工作流增强插件 — `/commit` 生成 Conventional Commits 消息、`/branch` 分支命名检查、`/pr` PR 模板生成、PreToolUse Hook 提交前自动校验

### ✨ 初始版本

- **插件**：收录 `evolver`（自进化引擎）和 `example-plugin`（最小参考实现）两个官方插件
- **marketplace.json**：插件市场清单，支持 `/plugin --install` 流程
- **JSON Schema**：`schemas/plugin.schema.json` 覆盖全部 7 类组件（commands/agents/skills/themes/hooks/mcp/lsp）
- **校验脚本**：`tools/validate_plugins.py` 自动校验 manifest + 组件完整性
- **文档**：`docs/` 目录包含 11 份组件规范文档
