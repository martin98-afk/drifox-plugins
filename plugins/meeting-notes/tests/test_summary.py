# -*- coding: utf-8 -*-
"""summary 提示词构建测试（不调用大模型）。"""

import importlib.util
import os
import sys
import unittest

UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")


def _load(module_name: str, file_name: str):
    sys.path.insert(0, UI_DIR)
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(UI_DIR, f"{file_name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


summary = _load("mn_summary", "summary")


class FakeSeg:
    def __init__(self, t, speaker, text):
        self.t = t
        self.speaker = speaker
        self.text = text


class FakeMeeting:
    def __init__(self, segments):
        self.segments = segments
        self.speaker_names = {"2": "张三"}

    def speaker_label(self, spk):
        if not spk:
            return ""
        return self.speaker_names.get(spk) or f"说话人 {spk}"


class BuildMessagesTests(unittest.TestCase):
    def test_transcript_includes_speaker_labels(self):
        m = FakeMeeting([FakeSeg(0, "1", "大家好"), FakeSeg(5, "2", "我说两句")])
        text, truncated = summary.build_transcript_text(m)
        self.assertFalse(truncated)
        self.assertEqual(text, "说话人 1: 大家好\n张三: 我说两句")

    def test_messages_have_system_and_user(self):
        m = FakeMeeting([FakeSeg(0, "1", "大家好")])
        msgs = summary.build_messages(m)
        self.assertEqual([x["role"] for x in msgs], ["system", "user"])
        self.assertIn("说话人 1: 大家好", msgs[1]["content"])
        self.assertIn("## 待办", msgs[1]["content"])

    def test_empty_transcript_raises(self):
        with self.assertRaises(ValueError):
            summary.build_messages(FakeMeeting([FakeSeg(0, "1", "   ")]))

    def test_long_transcript_truncated_and_flagged(self):
        segs = [FakeSeg(i, "1", "字" * 1000) for i in range(80)]  # 8 万字
        text, truncated = summary.build_transcript_text(FakeMeeting(segs))
        self.assertTrue(truncated)
        self.assertLessEqual(len(text), summary.MAX_TRANSCRIPT_CHARS + 20)
        msgs = summary.build_messages(FakeMeeting(segs))
        self.assertIn("被截断", msgs[1]["content"])


if __name__ == "__main__":
    unittest.main()
