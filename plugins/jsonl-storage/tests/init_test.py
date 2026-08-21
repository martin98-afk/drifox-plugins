# -*- coding: utf-8 -*-
"""验证 __init__ 立即初始化（is_initialized=True，让 history_manager 接受引擎）"""
import sys
import tempfile

sys.path.insert(0, '.')
from storages.jsonl_storage import JsonlStorageEngine


def main():
    # 场景 1：正常构造 → is_initialized=True
    with tempfile.TemporaryDirectory() as tmp:
        eng = JsonlStorageEngine(db_dir=tmp)
        assert eng.is_initialized is True, f'期望 True，实际 {eng.is_initialized}'
        print('[ok] is_initialized=True 让 history_manager 接受引擎')

    # 场景 2：构造时立即可用（不调任何 lazy 方法就能用）
    with tempfile.TemporaryDirectory() as tmp:
        eng = JsonlStorageEngine(db_dir=tmp)
        # 直接调 save，不需先调 _ensure_init
        ok = eng.save({'session_id': 'lazy-test', 'messages': [{'role': 'user', 'content': 'hi'}]})
        assert ok is True
        rec = eng.get('lazy-test')
        assert rec and rec.get('session_id') == 'lazy-test'
        print('[ok] 构造后立即可读写')

    # 场景 3：input_history 路径
    with tempfile.TemporaryDirectory() as tmp:
        eng = JsonlStorageEngine(db_dir=tmp)
        ok = eng.add_input_history('test', [])
        assert ok is True
        items = eng.get_input_history(limit=10)
        assert len(items) == 1
        assert items[0]['content'] == 'test'
        print('[ok] add_input_history 构造后立即可用')

    print('INIT TESTS PASS')


if __name__ == '__main__':
    main()