# -*- coding: utf-8 -*-
"""回归测试：Windows 黑窗抑制 + 转写行复用 + mac 转码 + 纪要超时配置。

跑法（需 Qt）：
    QT_QPA_PLATFORM=offscreen uv run --with loguru --with PyQt5 \
        --with PyQt-Fluent-Widgets python plugins/meeting-notes/tests/test_perf_regression.py

黑窗用 mock 断言 subprocess 参数，不真的调 ffmpeg；行复用用真实 QWidget
断言刷新前后行对象是同一个，且数据被就地改写。
"""

import importlib.util
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI_DIR = os.path.join(PLUGIN_DIR, "ui")

def _load(module_name, file_name):
    sys.path.insert(0, UI_DIR)
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(UI_DIR, f"{file_name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

store = _load("mn_perf_store", "store")

class BlackWindowTests(unittest.TestCase):
    """GUI 宿主里起 console 子进程会闪黑框：必须传窗口抑制参数。"""

    def test_convert_audio_suppresses_console_window(self):
        src = Path("/nonexistent/in.mp3")
        dst = Path(tempfile.mkdtemp(prefix="mn_perf_")) / "out.wav"
        try:
            # 锁定为非 darwin：mac 会优先走系统 afconvert，不进 ffmpeg 分支
            with mock.patch.object(store.sys, "platform", "win32"), \
                 mock.patch.object(store.shutil, "which", return_value="ffmpeg"), \
                 mock.patch.object(subprocess, "run") as run, \
                 mock.patch.object(store.wave, "open") as wf:
                run.return_value = mock.Mock(returncode=0, stderr=b"")
                # 让 dst 存在且够大，跳过 wave.open 读取
                dst.write_bytes(b"\0" * 128)
                wf.return_value.__enter__ = lambda s: s
                wf.return_value.__exit__ = lambda *a: None
                wf.return_value.getnframes.return_value = 0
                wf.return_value.getframerate.return_value = 16000
                store.convert_audio(src, dst)
            kwargs = run.call_args.kwargs
            self.assertIn("creationflags", kwargs, "必须传 creationflags 抑制黑窗")
            self.assertEqual(kwargs["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        finally:
            shutil.rmtree(dst.parent, ignore_errors=True)

    def test_creationflags_is_posix_safe(self):
        # 跨平台兜底：win32 有该常量，其余平台取 0（实测传非零会 ValueError）
        expected = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.assertEqual(expected, 0x08000000 if sys.platform == "win32" else 0)


class AfconvertTests(unittest.TestCase):
    """macOS 系统转码器：extensible 头改写 + 平台分派（不依赖 ffmpeg）。"""

    def _extensible_wav(self, path, nch=1, rate=16000, bits=16, frames=b"\x01\x02" * 100):
        # 造一个 fmt tag=0xFFFE、带扩展区的 WAV，模拟 afconvert 从 m4a 解码
        fmt = struct.pack(
            "<HHIIHH", 0xFFFE, nch, rate, rate * nch * (bits // 8),
            nch * (bits // 8), bits
        ) + struct.pack("<HHI", 22, bits, 0) + b"\x00" * 18
        body = (
            b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
            + b"data" + struct.pack("<I", len(frames)) + frames
        )
        path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)

    def test_rewrite_extensible_wav_makes_standard_pcm(self):
        p = Path(tempfile.mkdtemp(prefix="mn_af_")) / "ext.wav"
        try:
            self._extensible_wav(p)
            with self.assertRaises(store.wave.Error):
                store.wave.open(str(p), "rb")
            store._rewrite_extensible_wav(p)
            with store.wave.open(str(p), "rb") as w:
                self.assertEqual(w.getcomptype(), "NONE")
                self.assertEqual(w.getnchannels(), 1)
                self.assertEqual(w.getframerate(), 16000)
                self.assertEqual(w.getsampwidth(), 2)
                self.assertEqual(w.readframes(w.getnframes()), b"\x01\x02" * 100)
        finally:
            shutil.rmtree(p.parent, ignore_errors=True)

    def test_rewrite_leaves_standard_pcm_untouched(self):
        p = Path(tempfile.mkdtemp(prefix="mn_af_")) / "std.wav"
        try:
            with store.wave.open(str(p), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
                w.writeframes(b"\x03\x04" * 50)
            before = p.read_bytes()
            store._rewrite_extensible_wav(p)
            self.assertEqual(p.read_bytes(), before, "标准 PCM 不应被改写")
        finally:
            shutil.rmtree(p.parent, ignore_errors=True)

    def test_convert_audio_prefers_afconvert_on_darwin(self):
        """mac 上非 WAV 导入必须走 /usr/bin/afconvert，不能要求装 ffmpeg。"""
        src = Path(tempfile.mkdtemp(prefix="mn_af_")) / "in.m4a"
        dst = src.parent / "out.wav"
        try:
            self._extensible_wav(dst)  # 模拟 afconvert 已产出 extensible WAV
            src.write_bytes(b"fake")
            with mock.patch.object(store.sys, "platform", "darwin"), \
                 mock.patch.object(store.Path, "is_file", return_value=True), \
                 mock.patch.object(subprocess, "run") as run, \
                 mock.patch.object(store.shutil, "which", return_value=None) as which:
                run.return_value = mock.Mock(returncode=0, stderr=b"")
                dur = store.convert_audio(src, dst)
            cmd = run.call_args.args[0]
            self.assertEqual(cmd[0], "/usr/bin/afconvert")
            self.assertIn("LEI16@16000", cmd)
            self.assertIn("-c", cmd)
            which.assert_not_called()  # 不该再去找 ffmpeg
            self.assertGreater(dur, 0)
            with store.wave.open(str(dst), "rb") as w:
                self.assertEqual(w.getnchannels(), 1)
        finally:
            shutil.rmtree(src.parent, ignore_errors=True)


class SummaryTimeoutTests(unittest.TestCase):
    """纪要超时可配置：默认值/越界收敛/脏值回退，且真的传到 turn()。"""

    @classmethod
    def setUpClass(cls):
        cls.cfg = _load("mn_perf_config", "config")
        cls.sum = _load("mn_perf_summary", "summary")

    def _read_with(self, store_get):
        class FakeStore:
            def get(self, _plugin, key):
                return store_get.get(key)
        with mock.patch.object(self.cfg, "_store", return_value=FakeStore()):
            return self.cfg.read_config()

    def test_default_is_180(self):
        self.assertEqual(
            self._read_with({})["summary_timeout_sec"],
            self.cfg.DEFAULT_SUMMARY_TIMEOUT_SEC,
        )

    def test_clamps_out_of_range(self):
        self.assertEqual(
            self._read_with({"summary_timeout_sec": 5})["summary_timeout_sec"],
            self.cfg.SUMMARY_TIMEOUT_MIN,
        )
        self.assertEqual(
            self._read_with({"summary_timeout_sec": 99999})["summary_timeout_sec"],
            self.cfg.SUMMARY_TIMEOUT_MAX,
        )

    def test_dirty_value_falls_back(self):
        self.assertEqual(
            self._read_with({"summary_timeout_sec": "abc"})["summary_timeout_sec"],
            self.cfg.DEFAULT_SUMMARY_TIMEOUT_SEC,
        )

    def test_string_number_normalized(self):
        self.assertEqual(
            self._read_with({"summary_timeout_sec": "240"})["summary_timeout_sec"], 240
        )

    def test_timeout_reaches_session_turn(self):
        """配置的超时必须传到 session.turn，不能停在 180 秒硬编码。"""
        seen = {}

        class FakeSession:
            def turn(self, **kw):
                seen.update(kw)
                return type("R", (), {"text": "# 标题\n\n## 一句话概要\n好"})()

        class M:
            segments = [type("S", (), {"text": "发言内容", "speaker": "1"})()]
            def speaker_label(self, _s):
                return "说话人 1"

        # generate_summary 内部另起线程跑 turn，用 Event 等它完成即可
        self.sum.generate_summary(FakeSession(), M(), timeout=321.0)
        self.assertEqual(seen.get("timeout"), 321.0)


class RowReuseTests(unittest.TestCase):
    """转写整页刷新必须复用行对象，不销毁重建（否则 600 行卡 300ms+）。"""

    @classmethod
    def setUpClass(cls):
        try:
            import PyQt5  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("需要 PyQt5（用 uv --with PyQt5 跑，或走 smoke 脚本）")
        pkg = type(sys)("meeting_notes_ui_perf")
        pkg.__path__ = [UI_DIR]
        sys.modules["meeting_notes_ui_perf"] = pkg
        spec = importlib.util.spec_from_file_location(
            "meeting_notes_ui_perf.__init__", os.path.join(UI_DIR, "__init__.py")
        )
        ui = importlib.util.module_from_spec(spec)
        sys.modules["meeting_notes_ui_perf.__init__"] = ui
        spec.loader.exec_module(ui)

        cls.store_mod = importlib.import_module("meeting_notes_ui_perf.store")
        cls._tmp = tempfile.TemporaryDirectory(prefix="mn_reuse_test_")
        cls.store_mod.data_root = lambda: Path(cls._tmp.name)
        cls.store_mod._migrated = True
        cls.store_mod._index_cache["ts"] = 0.0

        class R:
            def __init__(self): self.card = {}
            def register_floating_card(self, **kw): self.card.update(kw)
        reg = R()
        ui.register_ui(reg)

        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)
        cls.card = reg.card["widget_class"]()
        cls.card.show_card()
        cls.card.resize(1180, 720)
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.card.deleteLater()
        cls._tmp.cleanup()

    def _meeting_with(self, segments):
        m = self.store_mod.new_meeting("model")
        m.title = "复用测试"
        m.status = "done"
        m.segments = [
            self.store_mod.Segment(t=t, speaker=spk, text=text)
            for (t, spk, text) in segments
        ]
        self.store_mod.save(m)
        return m

    def test_render_transcript_reuses_row_objects(self):
        m = self._meeting_with([(0.0, "1", "第一句"), (5.0, "2", "第二句")])
        self.card._meeting = m
        self.card._render_transcript()
        self.app.processEvents()
        before = self.card._find_rows()
        self.assertEqual(len(before), 2)

        # 数据变化后再次整页刷新：行对象必须是同一批，只是内容就地改写
        m.segments[0].text = "第一句（精转后）"
        m.segments[1].speaker = "3"
        m.segments.append(self.store_mod.Segment(t=9.0, speaker="1", text="第三句"))
        self.card._render_transcript()
        self.app.processEvents()
        after = self.card._find_rows()

        self.assertEqual(len(after), 3)
        self.assertIs(after[0], before[0], "已有行被重建了")
        self.assertIs(after[1], before[1], "已有行被重建了")
        self.assertEqual(after[0]._text.text(), "第一句（精转后）")
        self.assertEqual(after[1]._badge.speaker, "3")

    def test_render_transcript_removes_extra_rows(self):
        m = self._meeting_with([(0.0, "1", "甲"), (1.0, "1", "乙"), (2.0, "1", "丙")])
        self.card._meeting = m
        self.card._render_transcript()
        self.app.processEvents()
        self.assertEqual(len(self.card._find_rows()), 3)

        m.segments = m.segments[:1]
        self.card._render_transcript()
        self.app.processEvents()
        self.assertEqual(len(self.card._find_rows()), 1, "多余行没有被收掉")

    def test_rename_speaker_updates_badges_without_rebuild(self):
        m = self._meeting_with([(0.0, "1", "甲"), (3.0, "2", "乙"), (6.0, "1", "丙")])
        self.card._meeting = m
        self.card._render_transcript()
        self.app.processEvents()
        before = self.card._find_rows()

        m.speaker_names["1"] = "张三"
        self.card._on_speaker_renamed("1", "张三")
        self.app.processEvents()
        after = self.card._find_rows()

        self.assertEqual(len(after), len(before))
        self.assertIs(after[0], before[0])
        self.assertEqual(after[0]._badge.text(), "张三")
        self.assertEqual(after[2]._badge.text(), "张三")
        self.assertEqual(after[1]._badge.text(), "说话人 2")

    def test_reused_row_reports_current_speaker(self):
        """行被复用改了 speaker 后，徽章改名必须回传新编号，不能是构造时的旧值。"""
        m = self._meeting_with([(0.0, "1", "甲")])
        self.card._meeting = m
        self.card._render_transcript()
        self.app.processEvents()
        row = self.card._find_rows()[0]

        captured = []
        row.speaker_renamed.connect(lambda spk, name: captured.append((spk, name)))
        row.set_data(1.0, "7", m.speaker_label("7"), "复用后的文本", self.card._theme)
        row._badge.edited.emit("李四")

        self.assertEqual(captured, [("7", "李四")])


if __name__ == "__main__":
    unittest.main()
