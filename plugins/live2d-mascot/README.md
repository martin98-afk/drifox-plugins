# 看板娘（live2d-mascot）

一个桌面 Live2D 看板：无边框、透明、置顶的悬浮窗，Qt 原生 OpenGL 渲染，
呼吸、眨眼、视线跟随、点击换表情都是实时计算，不是预渲染帧。

## 用法

- 左侧栏「看板」打开控制页 → 选模型 → 「召唤看板」
- 悬浮窗上：左键拖动窗口、单击换表情、右键可切换置顶 / 收起

## 换模型

把 Cubism 3/4 模型目录整个放进 `web/model/<名字>/`，入口文件命名为
`<名字>.model3.json`，控制页下拉框里就会出现它。缩放与居中在首次渲染时
自动标定，不需要手调参数。

内置示例模型 `odog` 来自 [L2D_library](https://github.com/Xnmk029/L2D_library)
（GPL-3.0），仅作演示。

## 为什么不做进欢迎卡片

DriFox 欢迎卡片的 WebView 没有 WebGL：实测 `canvas.getContext('webgl')`
返回 null，宿主启动参数带 `--disable-gpu-compositing`。pixi + Cubism Web SDK
这条网页渲染路线在卡片里跑不起来，所以看板做成独立悬浮窗，不往欢迎卡片注入内容。

## 依赖

`deps/darwin/` 内置 live2d-py 1.0.0（Cubism Native SDK 封装，MIT 之外的
Live2D 专有许可，见 `deps/darwin/LICENSE`）。

目前只在 macOS 26 / Apple Silicon 上实测通过；Windows / Linux 有对应 wheel，
但 OpenGL 上下文行为未验证。

固定 1.0.0 的原因：1.1.1 在本机 macOS 26 / Apple Silicon 上 `glInit()` 直接
段错误；1.0.0 需要兼容上下文（OpenGL 2.1 / GLSL 120），Core Profile 3.3 下
shader 编译失败。窗口在 `setFormat()` 里显式声明 2.1 NoProfile。
