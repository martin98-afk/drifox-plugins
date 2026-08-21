# -*- coding: utf-8 -*-
"""验证 config_schema 字段实际生效：db_dir 构造覆盖 + on_corrupt 两种行为"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, '.')
from storages.jsonl_storage import JsonlStorageEngine


def main():
    # db_dir 构造参数覆盖
    with tempfile.TemporaryDirectory() as tmp:
        eng = JsonlStorageEngine(db_dir=tmp)
        eng.save({'session_id': 'cfg-test', 'project': 'p', 'messages': []})
        p = Path(tmp) / 'sessions' / 'cfg-test.jsonl'
        assert p.exists(), f'expected {p}'
        print('[ok] db_dir constructor override works')

    # on_corrupt=empty：损坏行 → 视整文件空
    with tempfile.TemporaryDirectory() as tmp:
        eng = JsonlStorageEngine(db_dir=tmp)
        eng._on_corrupt = 'empty'
        bad = Path(tmp) / 'sessions' / 'badsession.jsonl'
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text('{"valid":1}\n{garbage line\n', encoding='utf-8')
        assert eng.get('badsession') is None, 'on_corrupt=empty 应返回空'
        print('[ok] on_corrupt=empty 行为正确')

        eng._on_corrupt = 'skip'
        rec = eng.get('badsession')
        assert rec and rec.get('valid') == 1, 'on_corrupt=skip 应跳过坏行返回有效行'
        print('[ok] on_corrupt=skip 行为正确')

    print('CONFIG TESTS PASS')


if __name__ == '__main__':
    main()