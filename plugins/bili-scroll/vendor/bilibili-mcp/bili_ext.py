# -*- coding: utf-8 -*-
"""B站写能力与补齐读能力的工具实现（bili-scroll 自有，非上游 AGI_Ananas 原件）。

为什么不直接塞进 mcp_server.py：
    mcp_server.py 是 vendor 进来的上游文件，迁移报告里写明「重新 vendor 时
    要原样补回补丁」——往它里面堆几百行自有逻辑，下次同步上游就变成手工合并
    的战场。这里做成独立模块，由 mcp_server.py 末尾一行 import 挂载；上游更新
    时只要保留那一行 import，本文件整体不动。

挂载方式：
    mcp_server.py 尾部 `from bili_ext import register_all; register_all(globals())`
    —— 把 mcp_server 的模块命名空间整个传进来，本模块复用它的 `tool()`
    白名单装饰器、`get_cred()` 凭证校验、CRED_FILE 等，不重复实现。

工具命名：一律 bili_ 前缀，且不得以 duty_ / bili_transcribe 开头
（bili_impl._EXCLUDED 会按前缀过滤掉那些）。
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

# ─── 本模块的公共小工具 ───────────────────────────────────────────────

def _ok(**kw) -> str:
    """成功回执：统一 {"ok": true, ...} 形态（新增工具一律用这个，便于模型判定）"""
    kw.setdefault("ok", True)
    return json.dumps(kw, ensure_ascii=False)

def _err(msg: str, **kw) -> str:
    """失败回执：带 ok=false，模型能立刻分辨是失败而不是空数据"""
    kw.update({"ok": False, "error": str(msg)})
    return json.dumps(kw, ensure_ascii=False)

def _split_ids(raw) -> list:
    """把 "1,2,3" / [1,2,3] / 1 统一成 int 列表。"""
    if raw is None or raw == "":
        return []
    if isinstance(raw, int):
        return [raw]
    if isinstance(raw, (list, tuple)):
        out = []
        for x in raw:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out
    out = []
    for part in str(raw).replace("，", ",").split(","):
        part = part.strip()
        if part:
            try:
                out.append(int(part))
            except ValueError:
                continue
    return out


def register_all(ns: dict) -> None:
    """把本模块的工具注册进 mcp_server 的命名空间。

    Args:
        ns: mcp_server 模块的 globals()。用它在运行时取 tool / get_cred /
            video / user / comment 等已 import 好的名字，避免循环 import。
    """
    tool = ns["tool"]
    get_cred = ns["get_cred"]
    _guard = ns.get("_guard", lambda _n: "")

    # SDK 模块（mcp_server 已 import，这里复用同一份，避免二次 import 出双实例）
    video = ns["video"]
    user = ns["user"]
    comment = ns["comment"]
    dynamic = ns["dynamic"]
    favorite_list = ns["favorite_list"]
    Picture = ns["Picture"]

    # ─── 内部辅助：懒加载更重的模块 ────────────────────────────────

    def _sdk(name: str):
        """按需 import bilibili_api 子模块（video_uploader 等较重，启动期不拉）。"""
        import importlib

        return importlib.import_module(f"bilibili_api.{name}")

    def _uploader_mods():
        vu = _sdk("video_uploader")
        return vu.VideoUploader, vu.VideoUploaderPage, vu.VideoMeta, vu.Lines

    # ================================================================
    #  一、动态（发 / 删 / 转 / 点赞）—— dynamic 模块
    # ================================================================

    @tool()
    async def bili_dynamic_publish(text: str = "", image_paths: str = "",
                                   topic_id: int = 0, at_uids: str = "",
                                   send_at: str = "") -> str:
        """
        发一条B站动态（纯文本 / 带图 / 带话题 / @人 / 定时发布）

        Args:
            text: 动态正文。纯文本动态必填；带图动态可留空
            image_paths: 本地图片路径，多张用英文逗号分隔（最多 9 张）。图片会先传到B站图床
            topic_id: 话题 ID（可选）。不确定就别填，填错会被B站拒
            at_uids: 要 @ 的 UID，多个用逗号分隔（可选）
            send_at: 定时发布时间，格式 "YYYY-MM-DD HH:MM:SS"（可选，留空=立即发）

        Returns:
            JSON：成功含 dynamic_id 与链接；失败含 error
        """
        denied = _guard("bili_dynamic_publish")
        if denied:
            return _err(denied)
        cred = get_cred()
        if not text.strip() and not image_paths.strip():
            return _err("正文和图片至少给一个")

        pics = []
        for p in [x.strip() for x in image_paths.replace("，", ",").split(",") if x.strip()]:
            fp = Path(p)
            if not fp.is_file():
                return _err(f"图片不存在: {p}")
            pics.append(Picture().from_file(str(fp)))
        if len(pics) > 9:
            return _err(f"图片最多 9 张，给了 {len(pics)} 张")

        builder = dynamic.BuildDynamic.empty()
        if text.strip():
            builder.add_plain_text(text)
        for uid in _split_ids(at_uids):
            builder.add_at(uid=uid)
        if pics:
            builder.add_image(pics)
        if topic_id:
            builder.set_topic(int(topic_id))
        if send_at.strip():
            from datetime import datetime

            try:
                builder.set_send_time(datetime.strptime(send_at.strip(), "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                return _err(f"send_at 格式不对，要 YYYY-MM-DD HH:MM:SS，收到: {send_at}")

        try:
            result = await dynamic.send_dynamic(builder, credential=cred)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        dyn_id = ""
        if isinstance(result, dict):
            dyn_id = str(result.get("dynamic_id") or result.get("dyn_id") or "")
        return _ok(
            sent=True,
            dynamic_id=dyn_id,
            url=f"https://t.bilibili.com/{dyn_id}" if dyn_id else "",
            scheduled=bool(send_at.strip()),
            raw=result if isinstance(result, dict) else str(result),
        )

    @tool()
    async def bili_dynamic_delete(dynamic_id: int) -> str:
        """
        删除自己发的某条动态

        Args:
            dynamic_id: 动态 ID（不是 BV 号）

        Returns:
            JSON：成功含 deleted=true
        """
        denied = _guard("bili_dynamic_delete")
        if denied:
            return _err(denied)
        cred = get_cred()
        try:
            raw = await dynamic.Dynamic(dynamic_id=int(dynamic_id), credential=cred).delete()
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(deleted=True, dynamic_id=dynamic_id, raw=raw)

    @tool()
    async def bili_dynamic_repost(dynamic_id: int, text: str = "转发动态") -> str:
        """
        转发一条动态

        Args:
            dynamic_id: 要转发的动态 ID
            text: 转发时说的话

        Returns:
            JSON：转发结果
        """
        denied = _guard("bili_dynamic_repost")
        if denied:
            return _err(denied)
        cred = get_cred()
        try:
            result = await dynamic.Dynamic(dynamic_id=int(dynamic_id), credential=cred).repost(text=text)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(reposted=True, source_dynamic_id=dynamic_id, raw=result)

    @tool()
    async def bili_dynamic_like(dynamic_id: int, like: bool = True) -> str:
        """
        给动态点赞 / 取消点赞

        Args:
            dynamic_id: 动态 ID
            like: true=点赞，false=取消

        Returns:
            JSON：操作结果
        """
        denied = _guard("bili_dynamic_like")
        if denied:
            return _err(denied)
        cred = get_cred()
        try:
            raw = await dynamic.Dynamic(dynamic_id=int(dynamic_id), credential=cred).set_like(status=like)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(dynamic_id=dynamic_id, liked=like, raw=raw)

    @tool()
    async def bili_dynamic_schedules() -> str:
        """
        列出还没发出去的定时动态

        Returns:
            JSON：定时动态草稿列表
        """
        cred = get_cred()
        try:
            result = await dynamic.get_schedules_list(credential=cred)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        items = []
        if isinstance(result, dict):
            for it in (result.get("list") or result.get("drafts") or []):
                if not isinstance(it, dict):
                    continue
                items.append({
                    "draft_id": it.get("draft_id") or it.get("id"),
                    "publish_time": it.get("publish_time") or it.get("timer_pub_time"),
                    "content": str(it.get("content") or it.get("text") or "")[:80],
                })
        return _ok(count=len(items), schedules=items)

    @tool()
    async def bili_dynamic_schedule_publish(draft_id: int) -> str:
        """
        把一条定时动态立刻发出去

        Args:
            draft_id: 定时动态 ID（从 bili_dynamic_schedules 拿）

        Returns:
            JSON：发送结果
        """
        denied = _guard("bili_dynamic_schedule_publish")
        if denied:
            return _err(denied)
        cred = get_cred()
        try:
            result = await dynamic.send_schedule_now(draft_id=int(draft_id), credential=cred)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(draft_id=draft_id, raw=result)

    # ================================================================
    #  二、视频投稿（上传 + 改稿）—— video_uploader 模块
    # ================================================================

    @tool()
    async def bili_video_upload(video_path: str, title: str, tid: int, tags: str,
                                desc: str = "", cover_path: str = "",
                                original: bool = True, source: str = "",
                                no_reprint: bool = False, open_elec: bool = False,
                                dynamic_text: str = "", line: str = "") -> str:
        """
        投稿一个视频到B站（单 P，完整走预检→分片上传→封面→提交）

        ⚠️ 这是真投稿，会占用你的账号额度，提交后进审核队列。先在 bili_video_zones
        查好 tid；分片上传耗时随文件大小增长（100MB 约 1-3 分钟），期间工具不返回。

        Args:
            video_path: 本地视频文件绝对路径
            title: 标题，最多 80 字
            tid: 分区 ID（用 bili_video_zones 查）
            tags: 标签，英文逗号分隔，1-10 个
            desc: 简介，最多 2000 字
            cover_path: 封面图本地路径（**必填**；bilibili_api 不接受空封面）
            original: true=原创，false=转载（转载必须同时给 source）
            source: 转载来源，如 "https://example.com/xxx"（original=false 时必填）
            no_reprint: 是否禁止转载
            open_elec: 是否开启充电
            dynamic_text: 投稿同时发的粉丝动态，最多 233 字（可选）
            line: 上传线路 bda2/qn/ws/bldsa，留空自动测速选最快

        Returns:
            JSON：成功含 bvid / aid；失败含 error 与阶段
        """
        denied = _guard("bili_video_upload")
        if denied:
            return _err(denied)
        cred = get_cred()

        vp = Path(video_path)
        if not vp.is_file():
            return _err(f"视频文件不存在: {video_path}")
        if not original and not source.strip():
            return _err("original=false（转载）时必须给 source")

        # 封面必填：VideoUploader 构造时会对空串调 Picture().from_file("")，
        # 抛的是 FileNotFoundError: '' —— 报错信息完全没有指向性。这里先拦下。
        cp = Path(cover_path) if cover_path.strip() else None
        if cp is None or not cp.is_file():
            return _err(
                "必须给 cover_path（封面图本地路径）。"
                "bilibili_api 的 VideoUploader 不接受空封面，"
                "不传会在构造阶段抛 FileNotFoundError。"
                if cp is None else f"封面文件不存在: {cover_path}"
            )

        VideoUploader, VideoUploaderPage, VideoMeta, Lines = _uploader_mods()
        try:
            meta = VideoMeta(
                tid=int(tid), title=title, desc=desc,
                cover=str(cp), tags=tags,
                original=original, source=source or None,
                no_reprint=no_reprint, open_elec=open_elec,
                dynamic=dynamic_text or None,
            )
        except ValueError as e:
            return _err(f"参数不合规: {e}")
        except Exception as e:
            # Picture.from_file 内部要用 PIL 识图；PIL 本身有问题时这里就会炸
            return _err(
                f"封面读取失败: {type(e).__name__}: {e}\n"
                "如果报 UnidentifiedImageError 或 cannot import _imaging，"
                "是宿主 PIL 不可用（格式解码器未注册），不是图片本身的问题。"
            )

        line_enum = None
        if line.strip():
            try:
                line_enum = Lines(line.strip().lower())
            except ValueError:
                return _err(f"line 只能是 bda2/qn/ws/bldsa，收到: {line}")

        pages = [VideoUploaderPage(path=str(vp), title=title)]
        uploader = VideoUploader(pages=pages, meta=meta, credential=cred, line=line_enum)

        stage = "verify"
        try:
            await meta.verify(cred)
            stage = "upload"
            result = await uploader.start()
        except Exception as e:
            return _err(f"[{stage}] {type(e).__name__}: {e}", stage=stage)

        bvid = ""
        aid = 0
        if isinstance(result, dict):
            bvid = str(result.get("bvid") or "")
            aid = result.get("aid") or 0
        return _ok(
            uploaded=True, bvid=bvid, aid=aid,
            url=f"https://www.bilibili.com/video/{bvid}" if bvid else "",
            raw=result if isinstance(result, dict) else str(result),
        )

    @tool()
    async def bili_video_edit(bvid: str, title: str = "", desc: str = "",
                              tags: str = "", tid: int = 0,
                              cover_path: str = "", dynamic_text: str = "") -> str:
        """
        修改已投稿视频的信息（标题/简介/标签/分区/封面/粉丝动态）

        只改传了值的字段；留空的保持原样。

        Args:
            bvid: 要修改的稿件 BV 号（必须是自己的稿件）
            title: 新标题（留空不改）
            desc: 新简介（留空不改）
            tags: 新标签，英文逗号分隔（留空不改）
            tid: 新分区 ID（0=不改）
            cover_path: 新封面本地路径（留空不改）
            dynamic_text: 新粉丝动态（留空不改）

        Returns:
            JSON：修改结果
        """
        denied = _guard("bili_video_edit")
        if denied:
            return _err(denied)
        cred = get_cred()

        vu = _sdk("video_uploader")
        # VideoEditor 要求给完整 meta，先取现稿配置再覆盖
        from bilibili_api.utils.aid_bvid_transformer import bvid2aid
        from bilibili_api.utils.network import Api

        try:
            api = vu._API["upload_args"]
            current = (await Api(**api, credential=cred)
                       .update_params(bvid=bvid).result)
            archive = (current or {}).get("archive") or {}
        except Exception as e:
            return _err(f"读取现有稿件失败: {type(e).__name__}: {e}")

        meta = {
            "title": title or archive.get("title", ""),
            "copyright": archive.get("copyright", 1),
            "tid": int(tid) or archive.get("tid", 0),
            "tag": tags or ",".join(archive.get("tag", []) if isinstance(archive.get("tag"), list) else str(archive.get("tag", "")).split(",")),
            "desc_format_id": 0,
            "desc": desc or archive.get("desc", ""),
            "dynamic": dynamic_text or archive.get("dynamic", ""),
            "interactive": 0,
            "new_web_edit": 1,
            "act_reserve_create": 0,
            "no_reprint": archive.get("no_reprint", 0),
            "subtitle": {"lan": "", "open": 0},
            "web_os": 2,
        }

        cover = ""
        if cover_path.strip():
            cp = Path(cover_path)
            if not cp.is_file():
                return _err(f"封面不存在: {cover_path}")
            cover = str(cp)

        try:
            editor = vu.VideoEditor(bvid=bvid, meta=meta, cover=cover, credential=cred)
            result = await editor.start()
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(edited=True, bvid=bvid, aid=bvid2aid(bvid), raw=result)

    @tool()
    async def bili_video_zones_full() -> str:
        """
        获取完整的B站分区 ID 表（比 bili_video_zones 全，覆盖所有一级/二级分区）

        投稿前用来查 tid。返回 {一级分区: {tid: 二级分区名}}。

        Returns:
            JSON：完整分区表
        """
        try:
            import json as _json
            from pathlib import Path as _Path

            # 注意：get_api() 只读 data/api/ 下的文件，而分区表在 data/video_zone.json，
            # 用 get_api("video_zone") 会返回 {}（静默空结果，踩过）。这里直接定位文件。
            zone_file = _Path(__import__("bilibili_api").__file__).parent / "data" / "video_zone.json"
            data = _json.loads(zone_file.read_text(encoding="utf-8"))
            # 真实结构是顶层 list（不是 dict），每项 {tid, name, sub:[{tid,name}]}
            roots = data if isinstance(data, list) else (data.get("main") or [])
            out = {}
            for main in roots:
                if not isinstance(main, dict) or not main.get("tid"):
                    continue
                sub = {}
                for s in (main.get("sub") or []):
                    if isinstance(s, dict) and s.get("tid"):
                        sub[str(s["tid"])] = s.get("name", "")
                out[f'{main.get("name", "")}({main["tid"]})'] = sub
            return _ok(count=len(out), zones=out)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")

    @tool()
    async def bili_video_available_topics(tid: int) -> str:
        """
        查某个分区当前可参加的活动话题（投稿时填 topic_id 能加话题流量）

        Args:
            tid: 分区 ID

        Returns:
            JSON：话题列表，含 topic_id / 名称 / 任务 ID
        """
        cred = get_cred()
        vu = _sdk("video_uploader")
        try:
            topics = await vu.get_available_topics(tid=int(tid), credential=cred)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        items = []
        for t in (topics or []):
            if not isinstance(t, dict):
                continue
            # 真实返回字段与文档不一致（实测 200 条里 topic_id/name 都是 null，
            # 只有 mission_id 有值）。这里把见过的键都兜一遍，避免全空。
            items.append({
                "topic_id": t.get("id") or t.get("topic_id"),
                "mission_id": t.get("mission_id") or t.get("missionId"),
                "name": t.get("name") or t.get("title") or t.get("topic_name") or "",
            })
        # 只回前 40 条：200 条原样返回会把上下文撑爆，且字段大面积重复
        return _ok(tid=tid, count=len(items), topics=items[:40])

    # ================================================================
    #  三、稿件管理 —— creative_center 模块（自己的稿件/数据）
    # ================================================================

    @tool()
    async def bili_my_videos(pn: int = 1, ps: int = 10, status: str = "all") -> str:
        """
        列出自己的投稿稿件（含审核状态、播放量）

        Args:
            pn: 页码
            ps: 每页数量
            status: all=全部 pubed=已过审 is_pubing=审核中 not_pubed=未过审

        Returns:
            JSON：稿件列表
        """
        cred = get_cred()
        cc = _sdk("creative_center")
        try:
            status_map = {
                "all": cc.UploadManagerStatus.ALL,
                "pubed": cc.UploadManagerStatus.PUBED,
                "is_pubing": cc.UploadManagerStatus.IS_PUBING,
                "not_pubed": cc.UploadManagerStatus.NOT_PUBED,
            }
            st = status_map.get(status, cc.UploadManagerStatus.ALL)
            result = await cc.get_video_upload_manager_info(
                credential=cred, pn=int(pn), ps=int(ps), status=st
            )
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")

        items = []
        for v in ((result or {}).get("arc_audits") or []):
            arc = v.get("Archive") or {}
            stat = v.get("stat") or {}
            items.append({
                "bvid": arc.get("bvid", ""),
                "title": arc.get("title", ""),
                "state": arc.get("state"),
                "state_desc": arc.get("state_desc", ""),
                "view": stat.get("view", 0),
                "like": stat.get("like", 0),
                "comment": stat.get("reply", 0),
                "pubdate": arc.get("ptime") or arc.get("pubdate"),
            })
        # 真实返回结构里没有 page.total，总数在顶层，依次兜底
        total = None
        for key in ("total", "count", "total_count"):
            if isinstance(result, dict) and result.get(key) is not None:
                total = result.get(key)
                break
        return _ok(page=pn, count=len(items), videos=items, total=total)

    @tool()
    async def bili_my_stats(period: str = "week") -> str:
        """
        看自己账号的数据总览（播放/粉丝/点赞等涨跌）

        Args:
            period: yesterday=昨天 week=近一周 month=近一月 three_month=近三月 total=累计

        Returns:
            JSON：数据总览
        """
        cred = get_cred()
        cc = _sdk("creative_center")
        period_map = {
            "yesterday": cc.GraphPeriod.YESTERDAY,
            "week": cc.GraphPeriod.WEEK,
            "month": cc.GraphPeriod.MONTH,
            "three_month": cc.GraphPeriod.THREE_MONTH,
            "total": cc.GraphPeriod.TOTAL,
        }
        try:
            result = await cc.get_overview(
                credential=cred, period=period_map.get(period, cc.GraphPeriod.WEEK)
            )
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")

        # 上游返回嵌套的 {key: {"total": n, "diff": n}}，摊平成模型好读的形态
        flat = {}
        for k, v in (result or {}).items():
            if isinstance(v, dict) and ("total" in v or "diff" in v):
                flat[k] = {"total": v.get("total"), "diff": v.get("diff")}
            else:
                flat[k] = v
        return _ok(period=period, stats=flat)

    @tool()
    async def bili_my_drafts() -> str:
        """
        查自己的投稿草稿箱

        Returns:
            JSON：草稿列表
        """
        cred = get_cred()
        cc = _sdk("creative_center")
        try:
            result = await cc.get_video_draft_upload_manager_info(credential=cred)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(raw=result)

    # ================================================================
    #  四、视频互动 —— video 模块写操作
    # ================================================================

    @tool()
    async def bili_video_like(bvid: str, like: bool = True) -> str:
        """
        给视频点赞 / 取消点赞

        Args:
            bvid: 视频 BV 号
            like: true=点赞，false=取消

        Returns:
            JSON：操作结果
        """
        denied = _guard("bili_video_like")
        if denied:
            return _err(denied)
        cred = get_cred()
        try:
            v = video.Video(bvid=bvid, credential=cred)
            raw = await v.like(status=like)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(bvid=bvid, liked=like, raw=raw)

    @tool()
    async def bili_video_coin(bvid: str, num: int = 1, also_like: bool = False) -> str:
        """
        给视频投币

        Args:
            bvid: 视频 BV 号
            num: 投几个币（1 或 2）
            also_like: 投币时是否同时点赞

        Returns:
            JSON：投币结果
        """
        denied = _guard("bili_video_coin")
        if denied:
            return _err(denied)
        cred = get_cred()
        if num not in (1, 2):
            return _err(f"投币数只能是 1 或 2，收到: {num}")
        try:
            v = video.Video(bvid=bvid, credential=cred)
            result = await v.pay_coin(num=num, like=also_like)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(bvid=bvid, coins=num, liked=also_like, raw=result)

    @tool()
    async def bili_video_triple(bvid: str) -> str:
        """
        给视频一键三连（点赞 + 投币 + 收藏）

        Args:
            bvid: 视频 BV 号

        Returns:
            JSON：三连结果
        """
        denied = _guard("bili_video_triple")
        if denied:
            return _err(denied)
        cred = get_cred()
        try:
            v = video.Video(bvid=bvid, credential=cred)
            result = await v.triple()
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(bvid=bvid, raw=result)

    @tool()
    async def bili_video_favorite(bvid: str, add_media_ids: str = "",
                                  del_media_ids: str = "") -> str:
        """
        收藏 / 取消收藏视频到指定收藏夹

        Args:
            bvid: 视频 BV 号
            add_media_ids: 要加入的收藏夹 ID，多个用逗号分隔（用 bili_favorite_lists 查 ID）
            del_media_ids: 要移出的收藏夹 ID，多个用逗号分隔

        Returns:
            JSON：操作结果
        """
        denied = _guard("bili_video_favorite")
        if denied:
            return _err(denied)
        cred = get_cred()
        add_ids = _split_ids(add_media_ids)
        del_ids = _split_ids(del_media_ids)
        if not add_ids and not del_ids:
            return _err("add_media_ids 和 del_media_ids 至少给一个")
        try:
            v = video.Video(bvid=bvid, credential=cred)
            raw = await v.set_favorite(add_media_ids=add_ids, del_media_ids=del_ids)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(bvid=bvid, added=add_ids, removed=del_ids, raw=raw)

    @tool()
    async def bili_video_share(bvid: str) -> str:
        """
        分享视频（计入视频的分享数）

        Args:
            bvid: 视频 BV 号

        Returns:
            JSON：分享结果
        """
        denied = _guard("bili_video_share")
        if denied:
            return _err(denied)
        cred = get_cred()
        try:
            v = video.Video(bvid=bvid, credential=cred)
            result = await v.share()
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(bvid=bvid, raw=result)

    @tool()
    async def bili_danmaku_send(bvid: str, text: str, time_sec: float = 0.0,
                                mode: str = "fly", color: str = "ffffff",
                                font_size: str = "normal", page: int = 1) -> str:
        """
        给视频发一条弹幕

        Args:
            bvid: 视频 BV 号
            text: 弹幕内容
            time_sec: 出现在视频第几秒
            mode: fly=滚动 bottom=底部 top=顶部
            color: 颜色，6 位十六进制不带 #
            font_size: normal/small/large
            page: 第几个分 P（从 1 开始）

        Returns:
            JSON：发送结果
        """
        denied = _guard("bili_danmaku_send")
        if denied:
            return _err(denied)
        cred = get_cred()
        dm_mod = _sdk("utils.danmaku")
        mode_map = {
            "fly": dm_mod.DmMode.FLY, "roll": dm_mod.DmMode.FLY,
            "bottom": dm_mod.DmMode.BOTTOM, "top": dm_mod.DmMode.TOP,
        }
        if mode not in mode_map:
            return _err(f"mode 只能是 fly/bottom/top，收到: {mode}")
        size_map = {
            "normal": dm_mod.DmFontSize.NORMAL,
            "small": dm_mod.DmFontSize.SMALL,
            "large": dm_mod.DmFontSize.LARGE,
        }
        try:
            dm = dm_mod.Danmaku(
                text=text, dm_time=float(time_sec),
                mode=mode_map[mode], color=color.lstrip("#"),
                font_size=size_map.get(font_size, dm_mod.DmFontSize.NORMAL),
            )
            v = video.Video(bvid=bvid, credential=cred)
            result = await v.send_danmaku(page_index=max(0, int(page) - 1), danmaku=dm)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(bvid=bvid, raw=result)

    @tool()
    async def bili_video_tag_add(bvid: str, tag: str) -> str:
        """
        给视频加一个标签

        Args:
            bvid: 视频 BV 号
            tag: 标签名

        Returns:
            JSON：添加结果
        """
        denied = _guard("bili_video_tag_add")
        if denied:
            return _err(denied)
        cred = get_cred()
        try:
            v = video.Video(bvid=bvid, credential=cred)
            raw = await v.add_tag(name=tag)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(bvid=bvid, tag=tag, raw=raw)

    # ================================================================
    #  五、用户关系 —— user 模块写操作
    # ================================================================

    @tool()
    async def bili_follow(uid: int, follow: bool = True) -> str:
        """
        关注 / 取关一个 UP 主

        Args:
            uid: 目标用户 UID
            follow: true=关注，false=取关

        Returns:
            JSON：操作结果
        """
        denied = _guard("bili_follow")
        if denied:
            return _err(denied)
        cred = get_cred()
        try:
            u = user.User(uid=int(uid), credential=cred)
            rel = user.RelationType.SUBSCRIBE if follow else user.RelationType.UNSUBSCRIBE
            raw = await u.modify_relation(relation=rel)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(uid=uid, following=follow, raw=raw)

    @tool()
    async def bili_block(uid: int, block: bool = True) -> str:
        """
        拉黑 / 解除拉黑一个用户

        Args:
            uid: 目标用户 UID
            block: true=拉黑，false=解除

        Returns:
            JSON：操作结果
        """
        denied = _guard("bili_block")
        if denied:
            return _err(denied)
        cred = get_cred()
        try:
            u = user.User(uid=int(uid), credential=cred)
            rel = user.RelationType.BLOCK if block else user.RelationType.UNBLOCK
            raw = await u.modify_relation(relation=rel)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(uid=uid, blocked=block, raw=raw)

    @tool()
    async def bili_my_followings(max_pages: int = 5) -> str:
        """
        列出自己关注的 UP 主（分页拉取后汇总）

        Args:
            max_pages: 最多翻几页（每页约 20 条，默认 5 页 = 100 条）

        Returns:
            JSON：关注列表
        """
        cred = get_cred()
        u = user.User(uid=int(cred.dedeuserid), credential=cred)

        # 注意：get_all_followings() 走 x/web-interface/attentions 老接口，
        # 现在返回 {"list": null}（实测关注 206 人却拿到空），别用它。
        # get_followings() 走 x/relation/followings 仍可用，需自己翻页。
        out = []
        total = None
        try:
            for pn in range(1, max(1, int(max_pages)) + 1):
                result = await u.get_followings(pn=pn, ps=50)
                if isinstance(result, dict):
                    total = result.get("total", total)
                    page_list = result.get("list") or []
                else:
                    page_list = result or []
                if not page_list:
                    break
                for it in page_list:
                    if not isinstance(it, dict):
                        continue
                    out.append({
                        "mid": it.get("mid"),
                        "uname": it.get("uname", ""),
                        "sign": str(it.get("sign", ""))[:60],
                    })
                if total is not None and len(out) >= int(total):
                    break
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")

        return _ok(count=len(out), total=total, followings=out)

    @tool()
    async def bili_my_followers(pn: int = 1, ps: int = 50) -> str:
        """
        列出自己的粉丝

        Args:
            pn: 页码
            ps: 每页数量

        Returns:
            JSON：粉丝列表
        """
        cred = get_cred()
        try:
            result = await user.User(uid=int(cred.dedeuserid), credential=cred).get_followers(pn=pn, ps=ps)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        out = []
        for it in ((result or {}).get("list") or []):
            out.append({
                "mid": it.get("mid"),
                "uname": it.get("uname", ""),
                "sign": str(it.get("sign", ""))[:60],
            })
        return _ok(page=pn, count=len(out), total=(result or {}).get("total"), followers=out)

    @tool()
    async def bili_space_notice(content: str = "") -> str:
        """
        设置或查看自己主页的公告

        Args:
            content: 公告内容；留空则只查看当前公告

        Returns:
            JSON：当前公告内容
        """
        denied = _guard("bili_space_notice")
        if denied and content.strip():
            return _err(denied)
        cred = get_cred()
        u = user.User(uid=int(cred.dedeuserid), credential=cred)
        try:
            raw = None
            if content.strip():
                raw = await u.set_space_notice(content=content)
            info = await u.get_space_notice()
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(updated=bool(content.strip()), notice=info, raw=raw)

    # ================================================================
    #  六、收藏夹管理 —— favorite_list 模块写操作
    # ================================================================

    @tool()
    async def bili_favorite_create(title: str, introduction: str = "",
                                   private: bool = False) -> str:
        """
        新建一个视频收藏夹

        Args:
            title: 收藏夹名称
            introduction: 简介
            private: 是否私密

        Returns:
            JSON：新收藏夹 ID
        """
        denied = _guard("bili_favorite_create")
        if denied:
            return _err(denied)
        cred = get_cred()
        try:
            result = await favorite_list.create_video_favorite_list(
                title=title, introduction=introduction, private=private, credential=cred
            )
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(created=True, media_id=(result or {}).get("id"), raw=result)

    @tool()
    async def bili_favorite_modify(media_id: int, title: str,
                                   introduction: str = "", private: bool = False) -> str:
        """
        修改收藏夹名称 / 简介 / 公开性

        Args:
            media_id: 收藏夹 ID
            title: 新名称
            introduction: 新简介
            private: 是否私密

        Returns:
            JSON：修改结果
        """
        denied = _guard("bili_favorite_modify")
        if denied:
            return _err(denied)
        cred = get_cred()
        try:
            raw = await favorite_list.modify_video_favorite_list(
                media_id=int(media_id), title=title,
                introduction=introduction, private=private, credential=cred
            )
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(modified=True, media_id=media_id, raw=raw)

    @tool()
    async def bili_favorite_delete(media_ids: str) -> str:
        """
        删除收藏夹（夹内视频不会丢，只是从夹里移除）

        Args:
            media_ids: 收藏夹 ID，多个用逗号分隔

        Returns:
            JSON：删除结果
        """
        denied = _guard("bili_favorite_delete")
        if denied:
            return _err(denied)
        cred = get_cred()
        ids = _split_ids(media_ids)
        if not ids:
            return _err("media_ids 不能为空")
        try:
            raw = await favorite_list.delete_video_favorite_list(media_ids=ids, credential=cred)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(deleted=True, media_ids=ids, raw=raw)

    @tool()
    async def bili_favorite_move(media_id_from: int, media_id_to: int, aids: str) -> str:
        """
        把视频从一个收藏夹移动到另一个

        Args:
            media_id_from: 原收藏夹 ID
            media_id_to: 目标收藏夹 ID
            aids: 视频 aid，多个用逗号分隔

        Returns:
            JSON：移动结果
        """
        denied = _guard("bili_favorite_move")
        if denied:
            return _err(denied)
        cred = get_cred()
        id_list = _split_ids(aids)
        if not id_list:
            return _err("aids 不能为空（注意是 aid 不是 bvid）")
        try:
            raw = await favorite_list.move_video_favorite_list_content(
                media_id_from=int(media_id_from), media_id_to=int(media_id_to),
                aids=id_list, credential=cred
            )
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(moved=True, aids=id_list, to=media_id_to, raw=raw)

    # ================================================================
    #  七、评论管理 —— comment 模块写操作
    # ================================================================

    @tool()
    async def bili_comment_delete(bvid: str, rpid: int) -> str:
        """
        删除自己发的一条评论

        Args:
            bvid: 评论所在视频 BV 号
            rpid: 评论 ID

        Returns:
            JSON：删除结果
        """
        denied = _guard("bili_comment_delete")
        if denied:
            return _err(denied)
        cred = get_cred()
        try:
            info = await video.Video(bvid=bvid, credential=cred).get_info()
            c = comment.Comment(
                oid=int(info["aid"]), type_=comment.CommentResourceType.VIDEO,
                rpid=int(rpid), credential=cred
            )
            raw = await c.delete()
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(deleted=True, bvid=bvid, rpid=rpid, raw=raw)

    @tool()
    async def bili_comment_like(bvid: str, rpid: int, like: bool = True) -> str:
        """
        给视频下的评论点赞 / 取消点赞

        Args:
            bvid: 视频 BV 号
            rpid: 评论 ID
            like: true=点赞，false=取消

        Returns:
            JSON：B站原始回执（含 code）。注意 B站对不存在的 rpid 也可能返回
            成功，code=0 只代表请求被接受，不代表那条评论真的存在。
        """
        denied = _guard("bili_comment_like")
        if denied:
            return _err(denied)
        cred = get_cred()
        try:
            info = await video.Video(bvid=bvid, credential=cred).get_info()
            c = comment.Comment(
                oid=int(info["aid"]), type_=comment.CommentResourceType.VIDEO,
                rpid=int(rpid), credential=cred
            )
            raw = await c.like(status=like)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")
        return _ok(bvid=bvid, rpid=rpid, liked=like, raw=raw)

    # ================================================================
    #  八、补齐读能力 —— 私信会话 / 关注动态流 / 稍后再看
    # ================================================================

    @tool()
    async def bili_my_dynamics(offset: str = "") -> str:
        """
        看自己关注的人发了什么动态（时间线）

        Args:
            offset: 翻页游标，第一页留空；下一页用返回里的 offset

        Returns:
            JSON：动态时间线，含下页游标
        """
        cred = get_cred()
        try:
            result = await user.User(
                uid=int(cred.dedeuserid), credential=cred
            ).get_dynamics_new(offset=offset)
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")

        items = []
        for it in ((result or {}).get("items") or []):
            if not isinstance(it, dict):
                continue
            mod = it.get("modules") or {}
            author = (mod.get("module_author") or {})
            dyn = (mod.get("module_dynamic") or {})
            desc = (dyn.get("desc") or {})
            items.append({
                "dynamic_id": it.get("id_str", ""),
                "type": it.get("type", ""),
                "author": author.get("name", ""),
                "author_uid": author.get("mid"),
                "published": author.get("pub_time", ""),
                "text": str(desc.get("text") or "")[:200],
                "major_type": (dyn.get("major") or {}).get("type", ""),
            })
        return _ok(count=len(items), dynamics=items,
                   offset=str((result or {}).get("offset") or ""))

    @tool()
    async def bili_private_sessions(session_type: int = 1) -> str:
        """
        列出自己的私信会话（谁给你发过消息）

        Args:
            session_type: 1=私聊 2=通知 3=应援团 4=全部

        Returns:
            JSON：会话列表，含对方 UID 与最后一条消息
        """
        cred = get_cred()
        from bilibili_api.utils.network import Api
        from bilibili_api.utils.utils import get_api

        try:
            api = get_api("session")["session"]["get"]
            result = await Api(**api, credential=cred).update_params(
                session_type=int(session_type), group_fold=1,
                unfollow_fold=0, sort_rule=2, build=0, mobi_app="web",
            ).result
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")

        items = []
        for it in ((result or {}).get("session_list") or []):
            if not isinstance(it, dict):
                continue
            items.append({
                "talker_uid": it.get("talker_id"),
                "session_type": it.get("session_type"),
                "unread": it.get("unread_count", 0),
                "last_msg_ts": it.get("session_ts"),
                "last_msg": str((it.get("last_msg") or {}).get("content") or "")[:100],
            })
        return _ok(count=len(items), sessions=items)

    @tool()
    async def bili_private_messages(talker_uid: int, session_type: int = 1,
                                    begin_seqno: int = 0, size: int = 20) -> str:
        """
        读某个人的私信记录

        Args:
            talker_uid: 对方 UID
            session_type: 1=私聊 2=应援团
            begin_seqno: 翻页游标（从 0 开始取最新）
            size: 取多少条

        Returns:
            JSON：消息列表，按时间倒序
        """
        cred = get_cred()
        from bilibili_api.utils.network import Api
        from bilibili_api.utils.utils import get_api

        try:
            api = get_api("session")["session"]["fetch"]
            result = await Api(**api, credential=cred).update_params(
                talker_id=int(talker_uid), session_type=int(session_type),
                begin_seqno=int(begin_seqno), size=int(size),
            ).result
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")

        items = []
        for it in ((result or {}).get("messages") or [])[:int(size)]:
            if not isinstance(it, dict):
                continue
            items.append({
                "sender_uid": it.get("sender_uid"),
                "timestamp": it.get("timestamp"),
                "msg_type": it.get("msg_type"),
                "content": str(it.get("content") or "")[:200],
            })
        return _ok(talker_uid=talker_uid, count=len(items), messages=items)

    # ================================================================
    #  九、通用：任意 BV/aid 转换 + 稿件状态速查
    # ================================================================

    @tool()
    async def bili_id_convert(bvid: str = "", aid: int = 0) -> str:
        """
        BV 号与 aid 互转

        Args:
            bvid: BV 号（与 aid 二选一）
            aid: 稿件 aid（与 bvid 二选一）

        Returns:
            JSON：bvid 与 aid
        """
        from bilibili_api.utils.aid_bvid_transformer import aid2bvid, bvid2aid

        if not bvid and not aid:
            return _err("bvid 和 aid 至少给一个")
        try:
            if bvid:
                return _ok(bvid=bvid, aid=bvid2aid(bvid))
            return _ok(bvid=aid2bvid(int(aid)), aid=int(aid))
        except Exception as e:
            return _err(f"{type(e).__name__}: {e}")

    # ================================================================
    #  十、诊断：宿主 PIL 运行时状态（排查图片类能力为什么失败）
    # ================================================================

    @tool()
    async def bili_diag_pil() -> str:
        """查宿主进程里 PIL 的真实状态（排查发图/封面为什么失败时用）。

        Returns:
            JSON：PIL 路径、已注册的解码器、能否真解码一张 PNG
        """
        import io

        info = {}
        try:
            from PIL import Image

            info["PIL_file"] = getattr(Image, "__file__", "")
            info["PIL_version"] = getattr(Image, "__version__", "")
            Image.init()
            info["open_formats"] = sorted(Image.OPEN)
            info["has_png"] = "PNG" in Image.OPEN
            sample = bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108020000"
                "00907753de0000000c49444154789c63f8cfc0000003010100c9fe92ef"
                "0000000049454e44ae426082"
            )
            with Image.open(io.BytesIO(sample)) as im:
                im.load()
                info["decode_ok"] = True
                info["decoded_size"] = list(im.size)
        except Exception as e:
            info["decode_ok"] = False
            info["decode_error"] = f"{type(e).__name__}: {e}"
        try:
            import sys as _sys

            info["meta_finders"] = [
                type(f).__name__ for f in _sys.meta_path
            ]
            info["pil_in_modules"] = [
                k for k in _sys.modules if k == "PIL" or k.startswith("PIL.")
            ][:6]
        except Exception:
            pass
        return _ok(pil=info)
