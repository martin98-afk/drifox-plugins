# 可选视觉工作台合同

## 定位

视觉工作台是供应商无关的页面承载与返修协作层，不是图片生成供应商，也不是图片路线的新增层级。它只能在“机会研究 -> 营销决策 -> 逐页视觉导演 -> Image2 Brief”完成后启用。

启用前先探测当前宿主是否存在匹配的适配清单。没有适配器或必需工具不可调用时，继续宿主原生图片预览与原生选择流程；不得阻塞，不得改变完整发布包触发边界。

工作台写入必须绑定当前用户工作区：记录规范化后的 `project_dir` 与 `canvas_dir`，默认 `canvas_dir = <project_dir>/canvas`。自定义 `canvas_dir` 默认禁止；只有用户明确授权且规范化路径、真实路径与符号链接检查均证明它仍在已授权 `project_dir` 内时才能使用。不得接受 `..`、盘符切换、UNC/链接逃逸或未记录的路径。

## 价值触发与低打扰询问

工作台不能在 Skill 启动、机会研究刚完成、营销方向刚选定、页面导演表尚未出图或封面仍只是文字 Brief 时询问。默认且最早的价值节点必须同时满足：机会研究完成、营销决策完成、逐页视觉导演和 Image2 Brief 完成、首张本轮 3:4 封面候选已真实生成且可见。此时用户能马上在手机画幅里比较标题、主体、留白和排版，工作台才有明确价值。

面向普通用户不显示供应商名。Codex 使用 `request_user_input`，Claude Code 使用 `AskUserQuestion`，宿主等价原生选择面也可。用户实际看到：

```text
问题：封面首稿已经出来，3:4 页面方向也已确定。要不要打开可视化工作台？你可以在手机画幅里放大查看标题、主体和留白，直接批注需要调整的位置；无论是否打开，封面确认和后续生成都照常继续。

打开工作台（推荐）
马上看到 3:4 封面首稿，可放大检查排版并圈出要调整的位置。

暂不打开，继续生成
不打开画布，直接继续封面确认和后续图片生成，结果不会少。
```

工作台询问状态只使用 `not_offered`、`offered_pending`、`accepted`、`declined`、`unavailable`、`launch_failed`、`opened_verified`。原生选择返回才证明原生确认；`explicit_auto_permission` 只证明自动授权，不得写成 `human_confirmed`。插入返回只证明 attempted，只有适配器声明的画布状态能力回读匹配 shape、asset URL/路径与 snapshot SHA-256 才能写 `opened_verified`。

同一 `offer_stage + value_fingerprint` 最多询问一次。跳过后不因重新显示同一封面、进入封面 MVP 弹框或批量翻页而再问。只允许在两类新高价值阶段再次询问，且必须有新的 artifact hash、`new_value_reason` 和 `new_value_evidence_sha256`：

1. `cover_revision_comparison`：用户已指出具体封面问题，修订候选已经形成，可做 before/after 比较。
2. `failed_page_revision_comparison`：批量后已有明确失败页与修订候选，只比较和返修失败页，不重做整组。

用户明确“按推荐自动决定/你定”时可在价值节点自动打开，但记录 `explicit_auto_permission`；用户说“不要问/继续完成”时默认跳过可选工作台；用户明确“不要打开”时记录 `declined`。无原生选择面时显示 Markdown 降级卡并停止等待，不得伪称原生弹窗。工作台不可用、用户跳过或启动失败时，继续封面 MVP 原生确认和现有图片路线。

## 阶段合同

### 1. 封面承载

1. 只有完成上节一次性询问并获得授权后，才根据导演表建立 `3:4` 封面槽位；槽位必须关联 `page_direction_id` 与 `image_brief_id`。
2. 先由既有图片路线生成封面，再把本轮生成资产插入槽位。只有当前选择读回证明恰好一个槽位是已验证 `AI 图片` holder 时，才允许替换 holder；其他场景必须保留原对象。工作台不得自行成为第 2 级生成器，也不得在 Image2 失败后启动另一条隐形生成路线。
3. 在移动端信息流尺度检查主标题、主体、留白、贴边和遮挡，记录 `mobile_thumbnail_check` 的结果与证据。
4. 检查通过后，必须通过宿主原生选择工具取得“通过并批量生成”的许可。工作台中的选中、拖放、评论或 canvas id 均不算批量许可。

### 2. 批注返修

1. 每个批注截图只对应一个待返修资产，除非用户明确声明多个截图属于同一张图。
2. 批注截图是本轮返修 Brief；不扫描整张画布猜测编辑意图。
3. 修订图必须作为新位图放在原图右侧；该分支必须显式禁止 holder 替换，不得覆盖、移动、隐藏或删除原图与批注。
4. 修订后重新检查移动端缩略图、文字、主体和页面任务。只有明确记录 `accepted_asset` 后，修订图才成为该页交付资产。

### 3. 批量后逐页验收

批量出图结束后，为封面和每张内页建立逐页资产清单。只返修失败页并保留版本链；通过页不得被连带重做。

## 最小逐页清单

```json
{
  "page_key": "cover-or-page-01",
  "page_direction_id": "direction-id",
  "image_brief_id": "brief-id",
  "generation_evidence": {
    "route_tier": 1,
    "tool_or_host": "host-native-image-generation",
    "result_id_or_path": "current-run-result"
  },
  "workspace_placement": {
    "provider_id": "adapter-id",
    "status": "persisted_verified",
    "resolved_project_dir": "absolute-current-user-workspace",
    "resolved_canvas_dir": "absolute-current-user-workspace/canvas",
    "insert_attempt": {
      "page_id": "workspace-page-id",
      "slot_id": "3x4-slot-id",
      "returned_asset_id": "attempted-asset-id",
      "returned_shape_id": "attempted-shape-id",
      "returned_asset_url_or_path": "attempted-asset-url-or-path"
    },
    "state_readback": {
      "shape_id_confirmed": true,
      "asset_url_or_path_confirmed": true,
      "persisted_snapshot_sha256": "64-lowercase-hex",
      "evidence": "current-run-state-readback"
    }
  },
  "mobile_thumbnail_check": {
    "status": "pass-or-fail",
    "evidence": "screenshot-or-explicit-review-result"
  },
  "revision_lineage": [],
  "accepted_asset": {
    "asset_id_or_path": "explicit-final-asset",
    "status": "accepted",
    "acceptance_source": "human-or-recorded-review",
    "evidence": "native-choice-or-review-evidence"
  }
}
```

## 证据边界

- 插入工具返回的 `page_id`、`asset_id`、`shape_id`、资产 URL/路径、坐标和尺寸只证明工作台尝试放置，状态只能写 `attempted`。
- 完成放置必须在插入后调用适配器声明的状态读回能力，确认读回 snapshot 中存在同一 `shape_id`，该 shape 指向匹配的 asset URL/路径，并记录持久化 snapshot 的 SHA-256；三项齐全才能写 `persisted_verified`。
- `generation_evidence` 才能证明本轮生成；必须来自既有图片路线。
- `mobile_thumbnail_check` 才能证明小屏可读性检查结果。
- `accepted_asset` 只能在对应 `workspace_placement.status = persisted_verified` 后指定交付资产；缺读回或缺该字段时该页只能是 `partial`。
- 工作台截图可以证明对照和批注意图，不能单独证明图片质量或用户接受。
- 静态合同校验器或 eval 通过只能证明规则文件一致，不是当前宿主能力、实时插入或落盘成功的证据。

## 适配器边界

具体供应商映射放在 `references/provider-adapters/` 与 `assets/visual-workspace-adapters/`。适配器只能声明宿主、调用面、画幅、证据和不可用时的回退；不得改写本合同、图片路线优先级或触发合同。
