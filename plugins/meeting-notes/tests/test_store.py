# -*- coding: utf-8 -*-
"""store 测试：WAV 拼接、会议文件夹持久化、改名跟目录、旧结构迁移。

运行：python plugins/meeting-notes/tests/test_store.py -v
（插件目录名含连字符不能直接 import，按 git-panel 惯例从 ui/ 目录加载模块）
"""

import importlib.util
import json
import os
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_DIR = os.path.join(PLUGIN_DIR, "ui")


def _load_store():
    sys.path.insert(0, UI_DIR)
    spec = importlib.util.spec_from_file_location("mn_store", os.path.join(UI_DIR, "store.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["mn_store"] = module
    spec.loader.exec_module(module)
    return module


store = _load_store()


def write_wav(path: Path, seconds: float, value: int = 0, rate: int = 16000) -> None:
    frames = struct.pack("<h", value) * int(rate * seconds)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(frames)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="mn_store_")
        self.tmp = Path(self._tmp.name)
        self._orig_root = store.data_root
        self._orig_migrated = store._migrated
        store.data_root = lambda: self.tmp
        store._migrated = True  # 跳过旧结构迁移
        store._index_cache["ts"] = 0.0  # 清目录扫描缓存，避免跨用例串目录

    def tearDown(self):
        store.data_root = self._orig_root
        store._migrated = self._orig_migrated
        self._tmp.cleanup()

    # ── 音频 ──

    def test_join_chunks_appends_frames(self):
        target = self.tmp / "main.wav"
        joiner = store.WavJoiner(target)
        for i in range(3):
            chunk = self.tmp / f"c{i}.wav"
            write_wav(chunk, 1.0, value=i)
            self.assertAlmostEqual(joiner.append(chunk), 1.0, places=2)

        self.assertAlmostEqual(joiner.duration_sec(), 3.0, places=2)
        with wave.open(str(target), "rb") as wf:
            self.assertEqual(wf.getnframes(), 48000)
            frames = wf.readframes(wf.getnframes())
        samples = struct.unpack(f"<{len(frames) // 2}h", frames)
        self.assertEqual(samples[0], 0)
        self.assertEqual(samples[16000], 1)
        self.assertEqual(samples[32000], 2)

    def test_join_append_mode_continues_existing_file(self):
        target = self.tmp / "main.wav"
        first = self.tmp / "a.wav"
        write_wav(first, 1.0, value=5)
        store.WavJoiner(target).append(first)

        joiner = store.WavJoiner(target, append=True)
        second = self.tmp / "b.wav"
        write_wav(second, 1.0, value=9)
        self.assertAlmostEqual(joiner.append(second), 1.0, places=2)
        self.assertAlmostEqual(joiner.duration_sec(), 2.0, places=2)

    def test_join_skips_mismatched_params(self):
        target = self.tmp / "main.wav"
        joiner = store.WavJoiner(target)
        a = self.tmp / "a.wav"
        write_wav(a, 1.0, rate=16000)
        self.assertAlmostEqual(joiner.append(a), 1.0, places=2)
        b = self.tmp / "b.wav"
        write_wav(b, 1.0, rate=8000)
        self.assertEqual(joiner.append(b), 0.0)
        self.assertAlmostEqual(joiner.duration_sec(), 1.0, places=2)

    def test_extract_wav_range(self):
        src = self.tmp / "full.wav"
        write_wav(src, 4.0, value=1)
        out = self.tmp / "part.wav"
        part = store.extract_wav_range(src, out, 1.0, 3.0)
        self.assertIsNotNone(part)
        with wave.open(str(part), "rb") as wf:
            self.assertEqual(wf.getnframes(), 32000)

    def test_import_wav_mono_copied(self):
        src = self.tmp / "in.wav"
        write_wav(src, 2.0)
        dst = self.tmp / "out.wav"
        duration = store.normalize_import_wav(src, dst)
        self.assertAlmostEqual(duration, 2.0, places=2)
        self.assertEqual(dst.read_bytes(), src.read_bytes())

    def test_import_wav_stereo_downmixed(self):
        src = self.tmp / "stereo.wav"
        with wave.open(str(src), "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            # 左右声道交替：100 与 200 → 下混应得 150
            wf.writeframes(struct.pack("<hhhh", 100, 200, 100, 200) * 8000)
        dst = self.tmp / "mono.wav"
        duration = store.normalize_import_wav(src, dst)
        self.assertAlmostEqual(duration, 1.0, places=2)
        with wave.open(str(dst), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            data = wf.readframes(2)
        self.assertEqual(struct.unpack("<h", data[:2])[0], 150)

    def test_import_wav_rejects_8bit(self):
        src = self.tmp / "bad.wav"
        with wave.open(str(src), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(1)
            wf.setframerate(16000)
            wf.writeframes(b"\x80" * 100)
        with self.assertRaises(ValueError):
            store.normalize_import_wav(src, self.tmp / "o.wav")

    # ── 会议文件夹 ──

    def test_save_creates_named_folder(self):
        m = store.new_meeting("model-x")
        m.title = "产品评审会"
        store.save(m)

        folder = self.tmp / "产品评审会"
        self.assertTrue((folder / "meeting.json").exists())
        self.assertEqual(m.folder, "产品评审会")

        got = store.load(m.id)
        self.assertIsNotNone(got)
        self.assertEqual(got.folder, "产品评审会")

    def test_duplicate_title_gets_suffix(self):
        a = store.new_meeting("m")
        a.title = "周会"
        store.save(a)
        b = store.new_meeting("m")
        b.title = "周会"
        store.save(b)
        self.assertEqual(a.folder, "周会")
        self.assertEqual(b.folder, "周会 (2)")
        self.assertIsNotNone(store.load(a.id))
        self.assertIsNotNone(store.load(b.id))

    def test_rename_moves_folder(self):
        m = store.new_meeting("m")
        m.title = "旧名字"
        store.save(m)
        m.title = "新名字"
        store.save(m)
        self.assertFalse((self.tmp / "旧名字").exists())
        self.assertTrue((self.tmp / "新名字" / "meeting.json").exists())
        self.assertEqual(m.folder, "新名字")

    def test_illegal_chars_sanitized(self):
        m = store.new_meeting("m")
        m.title = "11月11日 01:15 会议"
        store.save(m)
        self.assertNotIn(":", m.folder)
        self.assertTrue((self.tmp / m.folder / "meeting.json").exists())

    def test_roundtrip_fields(self):
        m = store.new_meeting("XingChenAGI/XingChenASR-Diarize-V3.0")
        m.title = "产品评审"
        m.segments = [
            store.Segment(t=0.0, speaker="1", text="大家好"),
            store.Segment(t=5.5, speaker="2", text="我先说"),
        ]
        m.speaker_names = {"2": "张三"}
        m.duration_sec = 12.0
        m.refined_until = 12.0
        store.save(m)

        got = store.load(m.id)
        self.assertEqual(got.title, "产品评审")
        self.assertEqual(got.speaker_label("2"), "张三")
        self.assertEqual(got.speaker_label("1"), "说话人 1")
        self.assertEqual(
            got.transcript_lines(), ["[00:00] 说话人 1: 大家好", "[00:05] 张三: 我先说"]
        )
        self.assertTrue(got.refined)

    def test_list_sorted_desc(self):
        a = store.new_meeting("m")
        a.created_at = 100
        store.save(a)
        b = store.new_meeting("m")
        b.created_at = 200
        store.save(b)
        ids = [x.id for x in store.list_meetings()]
        self.assertEqual(ids, [b.id, a.id])

    def test_delete_removes_folder(self):
        m = store.new_meeting("m")
        m.title = "待删"
        store.save(m)
        store.delete(m.id)
        self.assertFalse((self.tmp / "待删").exists())
        self.assertIsNone(store.load(m.id))

    def test_export_markdown(self):
        m = store.Meeting(id="x", title="周会", created_at=0.0, duration_sec=65)
        m.segments = [store.Segment(t=61, speaker="1", text="结束")]
        m.summary_md = "## 概要\n- 通过"
        md = store.export_markdown(m)
        self.assertIn("# 周会", md)
        self.assertIn("## 概要", md)
        self.assertIn("[01:01] 说话人 1: 结束", md)

    def test_migrate_legacy_layout(self):
        legacy = self.tmp / "meetings"
        legacy.mkdir()
        audio = self.tmp / "audio"
        audio.mkdir()
        m = store.Meeting(id="old1", title="老会议", created_at=1.0, status="done")
        (legacy / "old1.json").write_text(
            json.dumps(m.to_dict(), ensure_ascii=False), encoding="utf-8"
        )
        write_wav(audio / "old1.wav", 1.0)

        store._migrated = False
        store._migrate_legacy(self.tmp)
        store._migrated = True

        self.assertTrue((self.tmp / "老会议" / "meeting.json").exists())
        self.assertTrue((self.tmp / "老会议" / "audio.wav").exists())
        self.assertFalse(legacy.exists())
        got = store.load("old1")
        self.assertIsNotNone(got)
        self.assertEqual(got.folder, "老会议")


if __name__ == "__main__":
    unittest.main()
