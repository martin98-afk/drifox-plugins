# B 站公开接口契约

> 全部条目均为 2026-10-27 本机实测，非文档转述。写新脚本前先照抄这里的头与解析方式。

## 通用请求头（缺一不可）

```python
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate",   # 关键：不要带 br
}
```

⚠ **`Accept-Encoding` 必须显式写成 `gzip, deflate`，不要声明 `br`。** 否则拿到 brotli 流，标准库解不了。

## 解压约定

弹幕接口返回的是 **deflate（zlib 裸流，非 zlib 头）**，实测首字节 `b4fde972`。两种都要兜：

```python
import gzip, zlib

def decode_body(raw: bytes, encoding: str) -> bytes:
    encoding = (encoding or "").lower()
    if "gzip" in encoding:
        return gzip.decompress(raw)
    if "deflate" in encoding:
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompress(raw, -zlib.MAX_WBITS)  # 裸流
    return raw
```

---

## L0 视频元信息 ✅ 免登录

```
GET https://api.bilibili.com/x/web-interface/view?bvid={bvid}
```

也可用 `?aid={aid}`。返回 `data` 关键字段：

| 字段 | 说明 |
|------|------|
| `bvid` / `aid` / `cid` | 三个 ID，后续接口都要 |
| `title` / `desc` | 标题、简介 |
| `duration` | 时长（秒） |
| `owner.name` | UP 主 |
| `pages[]` | 多 P 列表，每项含 `page` / `cid` / `part` |
| `stat` | `view` `danmaku` `reply` `favorite` `coin` `share` `like` |

⚠ 多 P 视频：`data.cid` 是第 1 P 的 cid。要别的 P 必须去 `pages[]` 里取对应 `cid`，**弹幕和视频流都按 cid 走**。

---

## L1 弹幕 ✅ 免登录

### 路线 A：XML（MVP 默认，最省事）

```
GET https://api.bilibili.com/x/v1/dm/list.so?oid={cid}
```

返回 XML，结构：

```xml
<i>
  <chatserver>chat.bilibili.com</chatserver>
  <chatid>137649199</chatid>
  <d p="0.60100,4,25,15138834,1604742895,0,9e5adeaa,40685126698926083,10">弹幕内容</d>
</i>
```

`p` 属性逗号分隔，实测语义：

| 位置 | 含义 |
|------|------|
| 0 | 出现时间（秒，浮点） |
| 1 | 模式（1 滚动 / 4 底部 / 5 顶部） |
| 2 | 字号 |
| 3 | 颜色（十进制 RGB） |
| 4 | 发送时间戳（Unix 秒） |
| 5 | 弹幕池 |
| 6 | 用户 hash |
| 7 | 数据库 ID |

解析用 `xml.etree.ElementTree`：

```python
import xml.etree.ElementTree as ET

root = ET.fromstring(text)
items = []
for d in root.findall("d"):
    p = (d.get("p") or "").split(",")
    items.append({"t": float(p[0]), "text": (d.text or "").strip()})
```

### 路线 B：protobuf（需全量弹幕时）

```
GET https://api.bilibili.com/x/v2/dm/web/seg.so?type=1&oid={cid}&segment_index={n}
```

⚠ **返回 protobuf 二进制，不是 XML**。实测 `len=163777`、`head_hex=0a6d08...`。用 `json.loads` 解析会抛 `JSONDecodeError`。
`segment_index` 从 1 起，每段约 6 分钟。解 pb 需要 `bilibili-API-collect` 的 `dm.proto` 定义，无 pb 库时**不要走这条路**。

---

## L2 评论 ✅ 免登录（必须用 /main）

```
GET https://api.bilibili.com/x/v2/reply/main?type=1&oid={aid}&sort={0|1|2}&ps={n}&pn={1}
```

⚠ **`oid` 传 `aid` 不是 `cid`**（弹幕传 cid，评论传 aid，这是最容易踩的坑）。

⚠ **必须用 `/main` 端点**。实测对照（同一视频、ps=5）：

| 端点 | 返回条数 |
|------|---------|
| `x/v2/reply` | **3**（静默裁剪，code 仍是 0） |
| `x/v2/reply/main` | **5**（完整） |

`sort=0` 时间序、`sort=2` 热度序。

⚠ `x/v2/reply/wbi/main` 需要 WBI 签名，无签名返回 `code=-403 访问权限不足`。

返回结构：

```
data.page.count      总评论数（⚠ /main 端点实测恒为 0，不可用于翻页判定）
data.replies[]       评论列表
  ├─ like            点赞数（热度信号）
  ├─ ctime           时间戳
  ├─ member.uname    用户名
  ├─ content.message 评论正文
  └─ replies[]       二级回复（子评论）
```

⚠ **翻页终止条件**：`/main` 的 `page.count` 实测为 0，用它当总数会导致第一轮就退出、
只拿到 20 条。正确做法是「本页返回数 < 请求数 ps → 已无更多，停止」。

⚠ `sort=2` 的返回**不是严格按 like 降序**（B 站热度算法含置顶与加权）。
这是正常现象，不要当成 bug 去"修"。

---

## L3 官方 AI 总结 ❌ 免登录 -403

```
GET https://api.bilibili.com/x/web-interface/view/conclusion/get?bvid={bvid}&cid={cid}&up_mid=0
```

实测返回 `{"code":-403,"message":"访问权限不足"}`。这是**常态，不是故障**。
脚本里：请求一次，code≠0 就静默跳过，不重试、不报错、不上报为错误。

---

## L4 字幕 ❌ 免登录恒空

```
GET https://api.bilibili.com/x/player/wbi/v2?aid={aid}&cid={cid}&w_rid=...&wts=...
```

⚠ **必须 WBI 签名**，但即使签名正确，**无 Cookie 时 `data.subtitle.subtitles` 恒为 `[]`，且 `need_login_subtitle=true`**。
实测扫 10 个热门视频，带字幕者 0 个。这不是签名写错，是 B 站对未登录用户不返回字幕。

⚠ `x/v2/subtitle/web/view` 实测返回 `code=-400 请求错误`，不要用。

**结论：只有用户提供 SESSDATA 时才尝试这一层。**

### WBI 签名算法（需要时照抄，已验证与官方示例逐字符一致）

```python
import hashlib, time, urllib.parse

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]
FILTER = set("!'()*")

def get_wbi_keys():
    j = get_json("https://api.bilibili.com/x/web-interface/nav")
    wbi = (j.get("data") or {}).get("wbi_img") or {}
    return (wbi.get("img_url", "").rsplit("/", 1)[-1].split(".")[0],
            wbi.get("sub_url", "").rsplit("/", 1)[-1].split(".")[0])

def mixin_key(img_key, sub_key):
    raw = img_key + sub_key
    return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]

def sign(params, img_key, sub_key):
    mk = mixin_key(img_key, sub_key)
    params = {k: "".join(c for c in str(v) if c not in FILTER)
              for k, v in params.items()}
    params["wts"] = int(time.time())
    query = urllib.parse.urlencode(sorted(params.items()), safe="!*'()",
                                   quote_via=urllib.parse.quote)
    return query + "&w_rid=" + hashlib.md5((query + mk).encode()).hexdigest()
```

验证锚点：`img_key=7cd084941338484aae1ad9425b84077c` + `sub_key=4932caff0ff746eab6f01bf08b70ac45`
→ `mixin_key=ea1db124af3c7062474693fa704f4ff8`（与 wbi.md 官方示例一致）。

---

## L5 视频流（抽帧前置） ✅ 免登录

```
GET https://api.bilibili.com/x/player/wbi/playurl?{signed}
```

签名参数：`{"bvid": bvid, "cid": cid, "fnval": 16, "fnver": 0, "fourk": 1}`

返回 `data.dash.video[]`（含 `id` 画质、`baseUrl`）与 `data.dash.audio[]`。

⚠ 请求视频流必须带 `Referer: https://www.bilibili.com/`，否则 412。
实测未登录可直连，200 / 33MB。

抽帧细节 → `references/frames.md`
