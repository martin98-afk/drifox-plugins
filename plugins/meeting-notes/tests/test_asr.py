# -*- coding: utf-8 -*-
"""asr 解析与重试测试（不联网，全部走纯函数/桩）。"""

import importlib.util
import os
import sys
import unittest
from unittest import mock

UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")


def _load(module_name: str, file_name: str):
    sys.path.insert(0, UI_DIR)
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(UI_DIR, f"{file_name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


asr = _load("mn_asr", "asr")


class ParsePayloadTests(unittest.TestCase):
    def test_diarize_payload(self):
        payload = {
            "text": "1: 大家好\n2: 我先说",
            "duration": 13.3,
            "segments": [
                {"start": 0.08, "end": 5.16, "text": "大家好", "speaker": "1"},
                {"start": 5.6, "end": 9.2, "text": "我先说", "speaker": "2"},
            ],
        }
        out = asr.parse_payload(payload)
        self.assertEqual(len(out["segments"]), 2)
        self.assertEqual(out["segments"][1]["speaker"], "2")
        self.assertAlmostEqual(out["segments"][0]["start"], 0.08)
        self.assertAlmostEqual(out["duration"], 13.3)

    def test_plain_text_payload(self):
        out = asr.parse_payload({"text": "只有一句话", "usage": {"seconds": 7}})
        self.assertEqual(out["text"], "只有一句话")
        self.assertEqual(len(out["segments"]), 1)
        self.assertEqual(out["segments"][0]["speaker"], "")
        self.assertAlmostEqual(out["duration"], 7.0)

    def test_empty_segments_are_dropped(self):
        out = asr.parse_payload(
            {"segments": [{"start": 0, "end": 1, "text": "  ", "speaker": "1"}, {"start": 1, "end": 2, "text": "有效"}]}
        )
        self.assertEqual([s["text"] for s in out["segments"]], ["有效"])

    def test_error_field_raises(self):
        with self.assertRaises(asr.AsrError):
            asr.parse_payload({"error": {"message": "bad key"}})

    def test_no_content_raises(self):
        with self.assertRaises(asr.AsrError) as ctx:
            asr.parse_payload({"segments": []})
        self.assertIn("未识别到语音", str(ctx.exception))


class SegmentOffsetTests(unittest.TestCase):
    def test_to_absolute(self):
        result = {"segments": [{"start": 1.0, "end": 2.0, "text": "a", "speaker": "1"}]}
        out = asr.to_absolute_segments(result, 20.0)
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out[0]["t"], 21.0)
        self.assertEqual(out[0]["speaker"], "1")

    def test_blank_text_filtered(self):
        result = {"segments": [{"start": 0, "end": 1, "text": "", "speaker": "1"}]}
        self.assertEqual(asr.to_absolute_segments(result, 0.0), [])


class RetryTests(unittest.TestCase):
    def test_retry_then_success(self):
        calls = []

        def fake_transcribe(*_a, **_kw):
            calls.append(1)
            if len(calls) < 3:
                raise asr.AsrError("请求被限流（HTTP 429）")
            return {"text": "ok", "segments": [{"start": 0, "end": 1, "text": "ok", "speaker": ""}]}

        with mock.patch.object(asr, "transcribe", side_effect=fake_transcribe):
            out = asr.transcribe_with_retry("u", "m", "k", "x.wav", sleep=lambda _s: None)
        self.assertEqual(out["text"], "ok")
        self.assertEqual(len(calls), 3)

    def test_auth_error_not_retried(self):
        calls = []

        def fake(*_a, **_kw):
            calls.append(1)
            raise asr.AsrError("API Key 无效或无权限（HTTP 401）")

        with mock.patch.object(asr, "transcribe", side_effect=fake):
            with self.assertRaises(asr.AsrError):
                asr.transcribe_with_retry("u", "m", "k", "x.wav", sleep=lambda _s: None)
        self.assertEqual(len(calls), 1)

    def test_gives_up_after_retries(self):
        with mock.patch.object(asr, "transcribe", side_effect=asr.AsrError("识别超时")):
            with self.assertRaises(asr.AsrError):
                asr.transcribe_with_retry("u", "m", "k", "x.wav", sleep=lambda _s: None)


if __name__ == "__main__":
    unittest.main()
