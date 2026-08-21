# -*- coding: utf-8 -*-
"""jsonl-storage 烟雾测试 — 临时目录，无副作用"""
import sys
import tempfile
import json
from pathlib import Path

sys.path.insert(0, '.')
from storages.jsonl_storage import JsonlStorageEngine


def main():
    with tempfile.TemporaryDirectory() as tmp:
        eng = JsonlStorageEngine(db_dir=tmp)

        # save / get
        s = {'session_id': 's1', 'project': 'demo', 'title': 'Hello',
             'messages': [{'role': 'user', 'content': 'hi'}]}
        assert eng.save(s) is True
        g = eng.get('s1')
        assert g['session_id'] == 's1'
        assert g['title'] == 'Hello'
        assert len(g['messages']) == 1
        print('[ok] save/get')

        assert eng.update_session_title('s1', 'New Title') is True
        assert eng.get('s1')['title'] == 'New Title'
        print('[ok] update_session_title')

        eng.save({'session_id': 's2', 'project': 'demo', 'messages': []})
        eng.save({'session_id': 's3', 'project': 'other', 'messages': []})

        all_s = eng.get_all(limit=10)
        assert len(all_s) == 3
        demo = eng.get_by_project('demo')
        assert len(demo) == 2
        assert all(x['project'] == 'demo' for x in demo)
        print('[ok] list / by_project')

        c = eng.get_session_counts()
        assert c['total'] == 3
        print('[ok] session_counts:', c)

        eng.add_input_history('user said hi')
        eng.add_input_history('user said bye', attachments=[{'name': 'a.txt'}])
        hist = eng.get_input_history(limit=10)
        assert len(hist) == 2
        assert hist[0]['content'] == 'user said bye'
        print('[ok] input_history')

        eng.record_file_operation('s1', 'call-1', 'edit_file', '/tmp/a.py', '/tmp/a.py.bak')
        eng.record_file_operation('s1', 'call-2', 'edit_file', '/tmp/b.py', '/tmp/b.py.bak')
        ops = eng.get_all_file_operations('s1')
        assert len(ops) == 2
        by_id = eng.get_file_operations_by_call_id('s1', 'call-1')
        assert len(by_id) == 1
        removed = eng.remove_file_operation('s1', 'call-1')
        assert removed == 1
        print('[ok] file_ops')

        # 文件结构验证
        session_file = Path(tmp) / 'sessions' / 's1.jsonl'
        assert session_file.exists()
        lines = session_file.read_text(encoding='utf-8').strip().split('\n')
        assert len(lines) == 1, 'save 应当只占一行（全量快照）'
        parsed = json.loads(lines[0])
        assert parsed['title'] == 'New Title'
        print('[ok] session 文件：单行 jsonl，全量快照')

        file_ops_file = Path(tmp) / 'file_ops' / 's1.jsonl'
        assert file_ops_file.exists()
        print('[ok] file_ops 文件：append 流')

        moved = eng.archive_sessions_by_project('demo')
        assert moved == 2
        assert eng.get_session_count() == 1
        print('[ok] archive_sessions_by_project')

        assert eng.delete('s3') is True
        assert eng.get('s3') is None
        print('[ok] delete')

    print('ALL TESTS PASS')


if __name__ == '__main__':
    main()