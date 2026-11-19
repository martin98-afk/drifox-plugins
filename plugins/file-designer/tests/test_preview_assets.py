# -*- coding: utf-8 -*-
"""预览图片落盘：data URI → 唯一命名的本地文件（拖拽文件名修复）。"""

import base64

import pytest

from ui.preview_assets import PreviewAssets


PNG_A = "data:image/png;base64," + base64.b64encode(b"\x89PNG-A").decode("ascii")
PNG_B = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8B").decode("ascii")


@pytest.fixture()
def assets(tmp_path):
    return PreviewAssets(tmp_path, "季度报告 v2")


def test_distinct_images_get_distinct_names(assets):
    html = f'<img src="{PNG_A}"><img src="{PNG_B}">'
    out, changed = assets.rewrite_html(html)
    assert changed is True
    assert "data:image/" not in out
    names = [p.name for p in sorted(assets.dir.iterdir())]
    assert names == ["季度报告_v2_01.png", "季度报告_v2_02.jpg"]
    assert 'src="preview_assets/季度报告_v2_01.png"' in out
    assert (assets.dir / "季度报告_v2_01.png").read_bytes() == b"\x89PNG-A"


def test_same_image_reuses_one_file(assets):
    html = f'<img src="{PNG_A}"><div data-bg="{PNG_A}"></div>'
    out, changed = assets.rewrite_html(html)
    assert changed is True
    assert out.count("preview_assets/季度报告_v2_01.png") == 2
    assert len(list(assets.dir.iterdir())) == 1


def test_non_image_data_uri_untouched(assets):
    html = '<a href="data:text/plain;base64,QQ==">x</a>'
    out, changed = assets.rewrite_html(html)
    assert changed is False
    assert out == html
    assert list(assets.dir.iterdir()) == []


def test_pptx_asset_json_is_rewritten(assets):
    """pptx 的图片走 window.__assets JSON 注入，同样要能被抽出。"""
    from ui.pptx_renderer import render_pptx_html

    model = {
        "w_pt": 960,
        "h_pt": 540,
        "slides": [
            {
                "shapes": [
                    {
                        "kind": "image",
                        "asset": "h1",
                        "anchor": "s1",
                        "left": 0,
                        "top": 0,
                        "width": 100,
                        "height": 80,
                    }
                ]
            }
        ],
        "assets": {"h1": PNG_A},
    }
    html = render_pptx_html(model)
    assert "data:image/png" in html
    out, changed = assets.rewrite_html(html)
    assert changed is True
    assert "data:image/png" not in out
    assert 'assets/季度报告_v2_01.png' in out


def test_reset_drops_previous_document_files(assets):
    assets.rewrite_html(f'<img src="{PNG_A}">')
    assets.reset()
    assert list(assets.dir.iterdir()) == []
    assets.rewrite_html(f'<img src="{PNG_B}">')
    assert [p.name for p in assets.dir.iterdir()] == ["季度报告_v2_01.jpg"]
