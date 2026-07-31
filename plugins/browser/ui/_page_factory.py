# -*- coding: utf-8 -*-
"""页面工厂 — 统一创建具有正常浏览器链接行为的 QWebEnginePage。"""


def create_page(view, profile, new_page_callback=None, is_dark=True):
    """创建页面：左键在当前标签跳转，右键可显式在新标签打开。"""
    from PyQt5.QtCore import Qt, QUrl
    from PyQt5.QtWidgets import QApplication, QMenu
    from PyQt5.QtWebEngineWidgets import (
        QWebEnginePage,
        QWebEngineScript,
        QWebEngineSettings,
    )

    class BrowserPage(QWebEnginePage):
        def createWindow(self, window_type):
            # target=_blank/window.open 默认复用当前页，符合左键当前标签跳转的交互。
            return self

    page = BrowserPage(profile, view)
    settings = page.settings()
    settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
    settings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)
    settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
    settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
    settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)

    thumb = "rgba(255,255,255,.28)" if is_dark else "rgba(60,70,85,.32)"
    hover = "rgba(100,150,230,.78)"
    scrollbar_css = (
        "::-webkit-scrollbar{width:10px;height:10px}"
        "::-webkit-scrollbar-track{background:transparent}"
        f"::-webkit-scrollbar-thumb{{background:{thumb};border:2px solid transparent;"
        "background-clip:padding-box;border-radius:8px}"
        f"::-webkit-scrollbar-thumb:hover{{background:{hover};border:2px solid transparent;"
        "background-clip:padding-box}"
        "::-webkit-scrollbar-corner{background:transparent}"
    )
    script = QWebEngineScript()
    script.setName("drifox-modern-scrollbars")
    script.setInjectionPoint(QWebEngineScript.DocumentCreation)
    script.setWorldId(QWebEngineScript.ApplicationWorld)
    script.setRunsOnSubFrames(True)
    script.setSourceCode(
        "(()=>{const add=()=>{if(document.getElementById('drifox-scrollbars'))return;"
        "const s=document.createElement('style');s.id='drifox-scrollbars';"
        f"s.textContent={scrollbar_css!r};(document.head||document.documentElement).appendChild(s);}};"
        "if(document.documentElement)add();else document.addEventListener('DOMContentLoaded',add,{once:true});})();"
    )
    page.scripts().insert(script)

    # target=_blank 链接改为当前页导航，保证历史栈完整（后退/前进可靠）
    nav_script = QWebEngineScript()
    nav_script.setName("drifox-inline-navigation")
    nav_script.setInjectionPoint(QWebEngineScript.DocumentCreation)
    nav_script.setWorldId(QWebEngineScript.ApplicationWorld)
    nav_script.setRunsOnSubFrames(True)
    nav_script.setSourceCode(
        "document.addEventListener('click',function(e){"
        "if(e.button!==0||e.ctrlKey||e.shiftKey||e.metaKey||e.altKey)return;"
        "var a=e.target&&e.target.closest?e.target.closest('a[target=\"_blank\"]'):null;"
        "if(a&&a.href){e.preventDefault();window.location.href=a.href;}"
        "},true);"
    )
    page.scripts().insert(nav_script)

    # 覆盖 navigator.* 为现代 Chrome，防止网站按 JS UA 拒绝 HTML5 播放
    # ⚠️ 必须注入 MainWorld：页面脚本在此上下文读取 navigator，
    #    ApplicationWorld 有独立的 navigator 对象，修改对页面不可见。
    ua_script = QWebEngineScript()
    ua_script.setName("drifox-chrome-ua")
    ua_script.setInjectionPoint(QWebEngineScript.DocumentCreation)
    ua_script.setWorldId(QWebEngineScript.MainWorld)
    ua_script.setRunsOnSubFrames(True)
    ua_script.setSourceCode(
        "(function(){"
        "var ua='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';"
        "try{Object.defineProperty(navigator,'userAgent',{get:function(){return ua;},configurable:true});"
        "Object.defineProperty(navigator,'vendor',{get:function(){return 'Google Inc.';},configurable:true});"
        "Object.defineProperty(navigator,'platform',{get:function(){return 'Win32';},configurable:true});"
        "}catch(e){}"
        "if('userAgentData' in navigator){try{"
        "var d={brands:[{brand:'Chromium',version:'131'},{brand:'Google Chrome',version:'131'},"
        "{brand:'Not_A Brand',version:'24'}],mobile:false,platform:'Windows'};"
        "Object.defineProperty(navigator,'userAgentData',{get:function(){return d;},configurable:true});"
        "}catch(e){}}"
        "})();"
    )
    page.scripts().insert(ua_script)

    def show_context_menu(pos):
        data = page.contextMenuData()
        link_url = QUrl(data.linkUrl())
        menu = QMenu(view)

        if link_url.isValid() and not link_url.isEmpty():
            menu.addAction("在当前标签打开", lambda: view.setUrl(link_url))
            if new_page_callback is not None:
                menu.addAction("在新标签打开", lambda: new_page_callback(link_url))
            menu.addAction(
                "复制链接地址",
                lambda: QApplication.clipboard().setText(link_url.toString()),
            )
            menu.addSeparator()

        back = menu.addAction("后退", view.back)
        back.setEnabled(view.history().canGoBack())
        forward = menu.addAction("前进", view.forward)
        forward.setEnabled(view.history().canGoForward())
        menu.addAction("刷新", view.reload)
        menu.addSeparator()
        menu.addAction("复制", lambda: page.triggerAction(QWebEnginePage.Copy))
        menu.addAction("全选", lambda: page.triggerAction(QWebEnginePage.SelectAll))
        menu.exec_(view.mapToGlobal(pos))

    view.setContextMenuPolicy(Qt.CustomContextMenu)
    view.customContextMenuRequested.connect(show_context_menu)
    return page
