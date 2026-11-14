# -*- coding: utf-8 -*-
<#
    uia.ps1 — Windows UI Automation 桥（desktop-automation 插件专用）

    设计要点：
    - 零第三方依赖：只用系统自带的 UIAutomationClient / UIAutomationTypes 程序集
    - 每次调用一个进程（约 250~400ms），输出单行 JSON 到 stdout
    - 进程启动即声明 DPI 感知，否则 BoundingRectangle 返回虚拟化坐标，与截图/SetCursorPos 不同源
    - Chromium 系（Electron/Edge/Chrome）的 UIA 树按需激活：首次请求只返回窗口框，
      需等 600ms 重取。脚本在节点数异常少时自动重试一次。
    - 入参走 base64(json)，避开 PowerShell 命令行引号转义地狱

    调用约定：
        powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File uia.ps1 -Op <op> -ArgsB64 <b64>

    op 列表：
        list      枚举可交互顶层窗口
        snapshot  取目标窗口的元素树（裁剪后）
        invoke    元素默认动作（InvokePattern）
        setvalue  写入值（ValuePattern）
        toggle    TogglePattern
        focus     SetFocus
        window    单取窗口信息（轻量，用于校验窗口是否还在原处）
#>
param(
    [Parameter(Mandatory = $false)][string]$Op = "",
    [string]$ArgsB64 = "",
    [switch]$Server
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try { [Console]::InputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# ── DPI 感知：必须在任何 UIA 调用之前 ────────────────────────────
try {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class DriFoxDpi {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool SetProcessDpiAwarenessContext(IntPtr value);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int nIndex);
}
"@ -ErrorAction SilentlyContinue
    # 先试 Win10 1703+ 的 per-monitor v2，失败退回旧 API
    $okCtx = $false
    try { $okCtx = [DriFoxDpi]::SetProcessDpiAwarenessContext([IntPtr](-4)) } catch { $okCtx = $false }
    if (-not $okCtx) { [DriFoxDpi]::SetProcessDPIAware() | Out-Null }
} catch {
    # 重复加载程序集时忽略，DPI 已由前次调用设置
}

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$UIA = [System.Windows.Automation.AutomationElement]
$TS = [System.Windows.Automation.TreeScope]
$root = $UIA::RootElement

# ── 入参解析 ────────────────────────────────────────────────────
function Get-Args {
    if ([string]::IsNullOrWhiteSpace($ArgsB64)) { return [pscustomobject]@{} }
    $json = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($ArgsB64))
    if ([string]::IsNullOrWhiteSpace($json)) { return [pscustomobject]@{} }
    return $json | ConvertFrom-Json
}

$A = Get-Args

# ── 输出 ────────────────────────────────────────────────────────
# 用于终止当前 op 并携带结果（服务模式下不能 exit，否则进程就没了）
class OpResult : Exception {
    [object]$Payload
    OpResult([object]$p) { $this.Payload = $p }
}

function Write-Ok($data) {
    throw [OpResult]::new([ordered]@{ ok = $true; data = $data })
}
function Write-Err([string]$msg) {
    throw [OpResult]::new([ordered]@{ ok = $false; error = $msg })
}

# ── 工具函数 ────────────────────────────────────────────────────
function Get-Rect($el) {
    try {
        $r = $el.Current.BoundingRectangle
        if ($r.IsEmpty) { return $null }
        return @([int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height)
    } catch { return $null }
}

# 全部走 Current：CacheRequest 在 Qt 上实测更慢（2.7s -> 27s）且移除后
# Cached 属性访问会抛异常，双重开销直接失控（-> 79s）。不要为「理论上更快」买单。
function Get-ElName($el) {
    try { return [string]$el.Current.Name } catch { return "" }
}

function Get-ElClass($el) {
    try { return [string]$el.Current.ClassName } catch { return "" }
}

function Get-ElRole($el) {
    try { return ([string]$el.Current.ControlType.ProgrammaticName).Replace("ControlType.", "") } catch { return "" }
}

function Get-ElOffscreen($el) {
    try { return [bool]$el.Current.IsOffscreen } catch { return $false }
}

function Get-Actions($el) {
    $acts = @()
    try {
        if ($el.GetCurrentPropertyValue($UIA::IsInvokePatternAvailableProperty)) { $acts += "invoke" }
        if ($el.GetCurrentPropertyValue($UIA::IsValuePatternAvailableProperty)) { $acts += "value" }
        if ($el.GetCurrentPropertyValue($UIA::IsTogglePatternAvailableProperty)) { $acts += "toggle" }
        if ($el.GetCurrentPropertyValue($UIA::IsSelectionItemPatternAvailableProperty)) { $acts += "select" }
        if ($el.GetCurrentPropertyValue($UIA::IsExpandCollapsePatternAvailableProperty)) { $acts += "expand" }
        if ($el.GetCurrentPropertyValue($UIA::IsTextPatternAvailableProperty)) { $acts += "text" }
        if ($el.GetCurrentPropertyValue($UIA::IsScrollPatternAvailableProperty)) { $acts += "scroll" }
    } catch { }
    return $acts
}

function Get-WindowInfo($w) {
    $r = Get-Rect $w
    return [ordered]@{
        title = [string]$w.Current.Name
        pid   = [int]$w.Current.ProcessId
        cls   = [string]$w.Current.ClassName
        hwnd  = [int64]$w.Current.NativeWindowHandle
        rect  = $r
    }
}

# 窗口选择打分：标题全等 100 / 标题包含 60 / 进程名包含 40 / 类名包含 20
function Resolve-Window($args_) {
    $q = [string]$args_.app
    $pid_ = 0
    if ($null -ne $args_.pid) { $pid_ = [int]$args_.pid }
    $hwnd_ = 0
    if ($null -ne $args_.hwnd) { $hwnd_ = [int64]$args_.hwnd }

    $wins = $root.FindAll($TS::Children, [System.Windows.Automation.Condition]::TrueCondition)
    $best = $null
    $bestScore = -1
    for ($i = 0; $i -lt $wins.Count; $i++) {
        $w = $wins.Item($i)
        try {
            $wid = [int]$w.Current.ProcessId
            if ($wid -le 0) { continue }
            $wh = [int64]$w.Current.NativeWindowHandle
            $rect = Get-Rect $w
            if ($null -eq $rect) { continue }
            if ($rect[2] -le 1 -or $rect[3] -le 1) { continue }
            if ($pid_ -gt 0 -and $wid -ne $pid_) { continue }
            if ($hwnd_ -gt 0 -and $wh -ne $hwnd_) { continue }
            if ($hwnd_ -gt 0 -or $pid_ -gt 0) { return $w }
            if ([string]::IsNullOrWhiteSpace($q)) {
                # 无查询条件：只收有名窗口，取第一个可见的
                if (-not [string]::IsNullOrWhiteSpace($w.Current.Name) -and $bestScore -lt 0) {
                    $best = $w; $bestScore = 0
                }
                continue
            }
            $title = [string]$w.Current.Name
            $cls = [string]$w.Current.ClassName
            $score = -1
            if ($title -eq $q) { $score = 100 }
            elseif ($title -like "*$q*") { $score = 60 }
            else {
                try {
                    $pn = (Get-Process -Id $wid -ErrorAction Stop).ProcessName
                    if ($pn -like "*$q*") { $score = 40 }
                } catch { }
                if ($score -lt 0 -and $cls -like "*$q*") { $score = 20 }
            }
            if ($score -gt $bestScore) { $best = $w; $bestScore = $score }
        } catch { continue }
    }
    return $best
}

# 角色权重：数字越小越像「可操作控件」，用于裁剪排序
# 说明：Qt5 的 MSAA→UIA 桥会给几乎所有元素（含 QLabel/QImage）都报
# IsInvokePatternAvailable=true，acts 字段对 Qt 应用不可信，不能据此判定可点性。
# 唯一可靠的排序依据是 role + name + 面积。
$script:ROLE_WEIGHT = @{
    Button = 0; Edit = 0; CheckBox = 0; RadioButton = 0; ComboBox = 0; MenuItem = 0
    ListItem = 0; TabItem = 0; Hyperlink = 0; Slider = 0; Spinner = 0; Document = 0
    TreeItem = 1; DataItem = 1; Menu = 2; ToolBar = 2; Tab = 2
    Custom = 3; Header = 3; HeaderItem = 3; Separator = 3
    Text = 4; Group = 5; Pane = 5; Image = 6; TitleBar = 6; ScrollBar = 6
}

function Get-RoleWeight([string]$role) {
    if ($script:ROLE_WEIGHT.ContainsKey($role)) { return $script:ROLE_WEIGHT[$role] }
    return 3
}

# 元素筛选：返回 @{ ok; weight; area } ；ok=false 表示丢弃
# 现实约束（实测所得）：
#   1. Qt5 的 MSAA→UIA 桥给几乎所有元素都报 IsInvokePatternAvailable=true，acts 无判别力
#   2. WinForms 的 UIA bridge 把 Button/TextBox 都报成 ControlType.Pane，role 无判别力
#   => 只能靠 Name + ClassName 组合识别。ClassName 是唯一跨框架稳定的线索。
function Get-ElementInfo($el, $winRect, $find) {
    try {
        if (Get-ElOffscreen $el) { return @{ ok = $false } }
        $name = Get-ElName $el
        # 名字过滤：直连定位用。精确匹配优先（matchRank=0），模糊次之（1）。
        # 只用模糊会出问题：找「点击」会命中一堆「点击折叠/展开」。
        $matchRank = 1
        if (-not [string]::IsNullOrEmpty($find)) {
            if ([string]::IsNullOrWhiteSpace($name)) { return @{ ok = $false } }
            if ($name -eq $find) { $matchRank = 0 }
            elseif ($name -like "*$find*") { $matchRank = 1 }
            else { return @{ ok = $false } }
        }
        $cls = ""
        if ([string]::IsNullOrWhiteSpace($name)) {
            # 无名元素先看类名，能一眼判死的就别再取 rect（跨进程取属性开销大）
            $cls = Get-ElClass $el
            $cu = $cls.ToUpperInvariant()
            $looksInput = $cu.Contains("EDIT") -or $cu.Contains("TEXTBOX") -or $cu.Contains("RICHEDIT") -or $cu.Contains("COMBOBOX")
            if (-not $looksInput) {
                $roleProbe = Get-ElRole $el
                if ($roleProbe -notin @("Edit", "Document", "ComboBox")) { return @{ ok = $false } }
            }
        }
        $r = $null
        try { $r = $el.Current.BoundingRectangle } catch { return @{ ok = $false } }
        if ($null -eq $r -or $r.IsEmpty) { return @{ ok = $false } }
        if ($r.Width -le 1 -or $r.Height -le 1) { return @{ ok = $false } }
        $role = Get-ElRole $el
        $weight = Get-RoleWeight $role
        # WinForms 把按钮报成 Pane：按类名纠正权重，否则按钮会被排到文本后面
        if (-not [string]::IsNullOrWhiteSpace($cls)) {
            $cu2 = $cls.ToUpperInvariant()
            if ($cu2.Contains("BUTTON")) { $weight = 0 }
            elseif ($cu2.Contains("EDIT") -or $cu2.Contains("TEXTBOX")) { $weight = 0 }
        }
        $area = [double]$r.Width * [double]$r.Height

        # 背景层：面积接近整窗且无名字（Qt 的 _WindowBaseLayer / QWidget 容器）
        $winArea = [double]$winRect[2] * [double]$winRect[3]
        if ($winArea -gt 0 -and $area -ge $winArea * 0.85 -and [string]::IsNullOrWhiteSpace($name)) {
            return @{ ok = $false }
        }

        # 注意：此处不查 pattern 可用性。跨进程查询每个元素 7 个属性代价极高
        # （582 个候选耗时 2s+），且结果对 Qt 无判别力。
        # pattern 只在最终入选的元素上按需探测。
        return @{ ok = $true; weight = $weight; area = $area; role = $role; has_name = (-not [string]::IsNullOrWhiteSpace($name)); matchRank = $matchRank }
    } catch { return @{ ok = $false } }
}

# 矩形是否与窗口相交（Qt 滚动内容返回内容坐标，可能为负或超出窗口；
# 只要求有交集，不能用中心点判定，否则拖出视口的控件会被误杀）
function Test-InWindow($rect, $winRect) {
    if ($null -eq $rect) { return $false }
    $x1 = [double]$rect[0]; $y1 = [double]$rect[1]
    $x2 = $x1 + [double]$rect[2]; $y2 = $y1 + [double]$rect[3]
    $wx1 = [double]$winRect[0]; $wy1 = [double]$winRect[1]
    $wx2 = $wx1 + [double]$winRect[2]; $wy2 = $wy1 + [double]$winRect[3]
    return ($x2 -gt $wx1 -and $x1 -lt $wx2 -and $y2 -gt $wy1 -and $y1 -lt $wy2)
}

# 按名字/类型/类名/runtimeId 定位元素
# 优先级：rid > (name/cls/ctype + 矩形最近)
# rid（UIA RuntimeId）在同一窗口生命周期内稳定，是 Qt 无名控件唯一可靠的引用方式
function Find-Element($win, $name, $cls, $ctype, $rectArr, $rid) {
    if (-not [string]::IsNullOrEmpty($rid)) {
        $all = $win.FindAll($TS::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
        for ($i = 0; $i -lt $all.Count; $i++) {
            $h = $all.Item($i)
            try {
                $hr = ($h.GetRuntimeId() -join ".")
                if ($hr -eq $rid) { return $h }
            } catch { continue }
        }
        return $null
    }
    $conds = @()
    if (-not [string]::IsNullOrEmpty($name)) {
        $conds += New-Object System.Windows.Automation.PropertyCondition($UIA::NameProperty, $name)
    }
    if (-not [string]::IsNullOrEmpty($cls)) {
        $conds += New-Object System.Windows.Automation.PropertyCondition($UIA::ClassNameProperty, $cls)
    }
    if ($null -ne $ctype -and -not [string]::IsNullOrEmpty($ctype)) {
        $ct = [System.Windows.Automation.ControlType]::$ctype
        if ($null -ne $ct) {
            $conds += New-Object System.Windows.Automation.PropertyCondition($UIA::ControlTypeProperty, $ct)
        }
    }
    if ($conds.Count -eq 0) { return $null }
    $cond = if ($conds.Count -eq 1) { $conds[0] } else { New-Object System.Windows.Automation.AndCondition($conds) }
    $hits = $win.FindAll($TS::Descendants, $cond)
    if ($hits.Count -eq 0) { return $null }
    if ($hits.Count -eq 1) { return $hits.Item(0) }
    if ($null -eq $rectArr -or $rectArr.Count -lt 4) { return $hits.Item(0) }
    # 多个同名元素：取矩形中心距离最近的
    $cx = [double]$rectArr[0] + [double]$rectArr[2] / 2
    $cy = [double]$rectArr[1] + [double]$rectArr[3] / 2
    $best = $null; $bestD = [double]::MaxValue
    for ($i = 0; $i -lt $hits.Count; $i++) {
        $h = $hits.Item($i)
        $r = Get-Rect $h
        if ($null -eq $r) { continue }
        $dx = ([double]$r[0] + [double]$r[2] / 2) - $cx
        $dy = ([double]$r[1] + [double]$r[3] / 2) - $cy
        $d = $dx * $dx + $dy * $dy
        if ($d -lt $bestD) { $bestD = $d; $best = $h }
    }
    return $best
}

# ══ op 分发（函数化，供单次模式与服务模式共用）═══════════
function Invoke-Op {
    param($Op, $A)
    try {
        # ══ op: list ═══════════════════════════════════════════════════
        if ($Op -eq "list") {
            $wins = $root.FindAll($TS::Children, [System.Windows.Automation.Condition]::TrueCondition)
    $out = @()
    for ($i = 0; $i -lt $wins.Count; $i++) {
        $w = $wins.Item($i)
        try {
            $wid = [int]$w.Current.ProcessId
            if ($wid -le 0) { continue }
            $rect = Get-Rect $w
            if ($null -eq $rect) { continue }
            if ($rect[2] -le 1 -or $rect[3] -le 1) { continue }
            $info = Get-WindowInfo $w
            try { $info["process"] = (Get-Process -Id $wid -ErrorAction Stop).ProcessName } catch { $info["process"] = "" }
            $info["index"] = $i
            $out += $info
        } catch { continue }
    }
    Write-Ok @{ windows = $out; count = $out.Count }
}

# ══ op: screen ════════════════════════════════════════════════
# 返回物理像素尺寸。调用方（Python 进程未必是 DPI 感知的）据此换算坐标空间：
# 物理 -> 逻辑 = 除以 (物理宽 / 自身 GetSystemMetrics 宽)
if ($Op -eq "screen") {
    Write-Ok ([ordered]@{
            width  = [DriFoxDpi]::GetSystemMetrics(0)
            height = [DriFoxDpi]::GetSystemMetrics(1)
        })
}

# ══ op: activate ═════════════════════════════════════════════
# 坐标点击前必须先把目标窗口带到前台：
# Windows 对后台窗口的第一次点击只用于激活，不会传递给控件。
if ($Op -eq "activate") {
    $w = Resolve-Window $A
    if ($null -eq $w) { Write-Err "找不到目标窗口" }
    $hwnd = [IntPtr][int64]$w.Current.NativeWindowHandle
    $method = ""
    try { [DriFoxDpi]::ShowWindow($hwnd, 9) | Out-Null } catch { }   # SW_RESTORE

    # 方案1：直接设前台
    if ([DriFoxDpi]::SetForegroundWindow($hwnd)) {
        $method = "direct"
    } else {
        # 方案2：AttachThreadInput 解除 Windows 的前台锁
        # （后台进程默认不允许抢前台，直接 SetForegroundWindow 会静默失败）
        try {
            $fgWnd = [DriFoxDpi]::GetForegroundWindow()
            $tmpPid = 0
            $fgThread = [DriFoxDpi]::GetWindowThreadProcessId($fgWnd, [ref]$tmpPid)
            $curThread = [DriFoxDpi]::GetCurrentThreadId()
            if ($fgThread -ne 0 -and $fgThread -ne $curThread) {
                [DriFoxDpi]::AttachThreadInput($curThread, $fgThread, $true) | Out-Null
                $null = [DriFoxDpi]::SetForegroundWindow($hwnd)
                [DriFoxDpi]::AttachThreadInput($curThread, $fgThread, $false) | Out-Null
                $method = "attach-thread-input"
            }
        } catch { }
        # 方案3：模拟一次 Alt 键，解除前台锁后再试
        $now = [DriFoxDpi]::GetForegroundWindow()
        if ($now -ne $hwnd) {
            try {
                [DriFoxDpi]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
                [DriFoxDpi]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
                $null = [DriFoxDpi]::SetForegroundWindow($hwnd)
                $method = "alt-key"
            } catch { }
        }
    }
    Start-Sleep -Milliseconds 150
    $now = [DriFoxDpi]::GetForegroundWindow()
    Write-Ok ([ordered]@{
            activated = ($now -eq $hwnd)
            hwnd      = [int64]$w.Current.NativeWindowHandle
            title     = [string]$w.Current.Name
            method    = $method
        })
}

# ══ op: window ═══════════════════════════════════════════════════
if ($Op -eq "window") {
    $w = Resolve-Window $A
    if ($null -eq $w) { Write-Err "找不到目标窗口" }
    Write-Ok (Get-WindowInfo $w)
}

# ══ op: snapshot ═══════════════════════════════════════════════
if ($Op -eq "snapshot") {
    $w = Resolve-Window $A
    if ($null -eq $w) { Write-Err "找不到目标窗口" }
    $win = Get-WindowInfo $w

    $condTrue = [System.Windows.Automation.Condition]::TrueCondition
    # 优先在 .NET 侧用条件过滤，避免逐元素跨进程取属性
    # （1173 节点逐个取 4 个属性约 1.5s，预过滤后只对有名元素取）
    $condNamed = New-Object System.Windows.Automation.AndCondition(
        (New-Object System.Windows.Automation.PropertyCondition($UIA::IsOffscreenProperty, $false)),
        (New-Object System.Windows.Automation.NotCondition(
                (New-Object System.Windows.Automation.PropertyCondition($UIA::NameProperty, ""))
            ))
    )
    $max = 120
    if ($null -ne $A.max_elements) { $max = [int]$A.max_elements }
    $offscreen = $false
    if ($null -ne $A.include_offscreen) { $offscreen = [bool]$A.include_offscreen }
    $find = ""
    if ($null -ne $A.find) { $find = [string]$A.find }

    # 取全量后代后客户端过滤：不能只用「Name≠空」在 .NET 侧预过滤，
    # 因为 WinForms 的 TextBox/Button 都没有 Name，会被整批漏掉。
    #
    # 实测否决：CacheRequest 在 Qt 应用上反而慢一个数量级
    # （2.7s -> 27s），因为 Qt 的 provider 要为缓存视图重建整棵树。
    # 不要因「官方推荐批量缓存」就套上，得按目标框架实测。
    do {
        # 精确名字命中的场景走 UIA 条件查找：provider 内部会剪枝
        $raw = $null
        $activated = $false
        if (-not [string]::IsNullOrEmpty($find)) {
            $exactCond = New-Object System.Windows.Automation.PropertyCondition($UIA::NameProperty, $find)
            $exact = $w.FindAll($TS::Descendants, $exactCond)
            if ($exact.Count -gt 0) { $raw = $exact }
        }
        if ($null -eq $raw) {
            $raw = $w.FindAll($TS::Descendants, $condTrue)
            # Chromium 系按需激活 UIA 树：首次只返回窗口框，等 600ms 重取一次
            if ($raw.Count -lt 20) {
                Start-Sleep -Milliseconds 600
                $raw = $w.FindAll($TS::Descendants, $condTrue)
                $activated = $true
            }
        }
    } while ($false)

    # 补充无名输入控件（Edit 常有 value 无 name）
    $editExtra = @()
    if (-not $offscreen) {
        $condEdit = New-Object System.Windows.Automation.AndCondition(
            (New-Object System.Windows.Automation.PropertyCondition($UIA::IsOffscreenProperty, $false)),
            (New-Object System.Windows.Automation.PropertyCondition($UIA::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit))
        )
        $editExtra = @($w.FindAll($TS::Descendants, $condEdit))
    }

    $els = @()
    $cand = @()
    $seen = @{}
    for ($i = 0; $i -lt $raw.Count; $i++) {
        $e = $raw.Item($i)
        try {
            # 读 Cached 属性（已随 FindAll 一起拿回，不再跨进程）
            $rect = Get-Rect $e
            if ($null -eq $rect) { continue }
            if (-not $offscreen) {
                $info = Get-ElementInfo $e $win.rect $find
                if (-not $info.ok) { continue }
            } else {
                $info = @{ ok = $true; weight = 3; area = [double]$rect[2] * [double]$rect[3]; has_name = $true }
            }
            $rid = ""
            try { $rid = ($e.GetRuntimeId() -join ".") } catch { $rid = "$($rect -join ',')|" + $e.Cached.Name }
            if ($seen.ContainsKey($rid)) { continue }
            $seen[$rid] = 1
            $cand += @{
                el = $e; rect = $rect; weight = $info.weight; area = $info.area
                has_name = $info.has_name; matchRank = $info.matchRank
                inwin = (Test-InWindow $rect $win.rect)
            }
        } catch { continue }
    }
    foreach ($e in $editExtra) {
        # 按名字过滤时不补无名输入框：调用方明确要按名字找，无名元素不该混进来
        if (-not [string]::IsNullOrEmpty($find)) { break }
        try {
            $rect = Get-Rect $e
            if ($null -eq $rect) { continue }
            $rid = ""
            try { $rid = ($e.GetRuntimeId() -join ".") } catch { $rid = "$($rect -join ',')|edit" }
            if ($seen.ContainsKey($rid)) { continue }
            $seen[$rid] = 1
            $cand += @{
                el = $e; rect = $rect; weight = 0; area = [double]$rect[2] * [double]$rect[3]
                has_name = $false
                inwin = (Test-InWindow $rect $win.rect)
            }
        } catch { continue }
    }

    # 排序：可操作控件优先 → 在窗口内优先 → 有名优先 → 尺寸小的优先 → 位置
    # 注意 weight 必须排在 has_name 之前：无名 Edit 是重要写入目标，
    # 若按「有名优先」会被 360 个 QLabel 文本挤到截断线之外。
    $sorted = $cand | Sort-Object `
        @{ Expression = { if ($null -ne $_.matchRank) { $_.matchRank } else { 1 } } }, `
        @{ Expression = { $_.weight } }, `
        @{ Expression = { if ($_.inwin) { 0 } else { 1 } } }, `
        @{ Expression = { if ($_.has_name) { 0 } else { 1 } } }, `
        @{ Expression = { $_.area } }, `
        @{ Expression = { $_.rect[1] } }, `
        @{ Expression = { $_.rect[0] } }

    foreach ($c in $sorted) {
        if ($els.Count -ge $max) { break }
        $e = $c.el
        try {
            $acts = Get-Actions $e
            $val = ""
            if ($acts -contains "value") {
                try {
                    $vp = $e.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
                    $val = [string]$vp.Current.Value
                    if ($val.Length -gt 200) { $val = $val.Substring(0, 200) }
                } catch { }
            }
            $rid = ""
            try { $rid = ($e.GetRuntimeId() -join ".") } catch { $rid = "" }
            $els += [ordered]@{
                i         = $els.Count
                name      = [string]$e.Current.Name
                cls       = [string]$e.Current.ClassName
                role      = ([string]$e.Current.ControlType.ProgrammaticName).Replace("ControlType.", "")
                rect      = $c.rect
                acts      = $acts
                value     = $val
                in_window = $c.inwin
                rid       = $rid
            }
        } catch { continue }
    }

    # 指纹：窗口标识 + 元素名序列，用于动作前判断快照是否过期
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append("$($win.pid)|$($win.hwnd)|")
    foreach ($e in $els) { [void]$sb.Append($e.name).Append("|") }
    $sha = [System.Security.Cryptography.SHA1]::Create()
    $hash = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($sb.ToString()))
    $fp = ([System.BitConverter]::ToString($hash) -replace "-", "").Substring(0, 12).ToLower()

    Write-Ok ([ordered]@{
            snapshot_id = $fp
            window      = $win
            elements    = $els
            total_raw   = $raw.Count
            candidates  = $cand.Count
            activated   = $activated
            truncated   = ($els.Count -ge $max)
        })
}

# ══ 元素类动作：invoke / setvalue / toggle / focus ═══════════
if ($Op -in @("invoke", "setvalue", "toggle", "focus")) {
    $w = Resolve-Window $A
    if ($null -eq $w) { Write-Err "找不到目标窗口" }

    $el = $null
    if ([string]::IsNullOrWhiteSpace($A.name) -and [string]::IsNullOrWhiteSpace($A.cls) -and [string]::IsNullOrWhiteSpace($A.rid)) {
        # 无定位信息：退化为按坐标点击（由 Python 侧处理），此处仅报错
        Write-Err "缺少 name/cls/rid，无法定位元素"
    }
    $el = Find-Element $w $A.name $A.cls $A.ctype $A.rect $A.rid
    if ($null -eq $el) {
        Write-Err "元素未找到（界面可能已变化，请重新 ui_tree）"
    }

    try {
        switch ($Op) {
            "invoke" {
                $p = $el.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
                $p.Invoke()
                Write-Ok @{ done = "invoke"; name = [string]$el.Current.Name }
            }
            "toggle" {
                $p = $el.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
                $p.Toggle()
                Write-Ok @{ done = "toggle"; state = [string]$p.Current.ToggleState }
            }
            "focus" {
                $el.SetFocus()
                Write-Ok @{ done = "focus"; name = [string]$el.Current.Name }
            }
            "setvalue" {
                $text = [string]$A.text
                # 不能靠 IsValuePatternAvailableProperty 判断：WinForms 对它报 false，
                # 但实际取 ValuePattern 是成功的。直接取，失败再退。
                $vp = $null
                try { $vp = $el.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern) } catch { $vp = $null }
                if ($null -ne $vp) {
                    if ($vp.Current.IsReadOnly) { Write-Err "元素只读，无法写入" }
                    $vp.SetValue($text)
                    Write-Ok @{ done = "setvalue"; via = "ValuePattern"; name = [string]$el.Current.Name }
                } else {
                    # 调用方据此改走键盘输入
                    Write-Err "该元素不支持 ValuePattern（可用 keyboard type 兜底）"
                }
            }
        }
    } catch {
        Write-Err ("动作失败: " + $_.Exception.Message)
    }
}

Write-Err "未知 op: $Op"
    } catch [OpResult] {
        return $_.Exception.Payload
    } catch {
        return [ordered]@{ ok = $false; error = "内部异常: " + $_.Exception.Message }
    }
}

# ══ 入口：单次模式 / 服务模式 ═══════════════════════════════════
# 服务模式：stdin 一行一个 JSON 请求 {"id":1,"op":"snapshot","args":{...}}，
# stdout 一行一个 JSON 响应。避免每次调用重新起进程、重载程序集（约 400ms/次）。
if ($Server) {
    $stdin = [Console]::In
    $stdout = [Console]::Out
    while ($true) {
        $line = $stdin.ReadLine()
        if ($null -eq $line) { break }
        $line = $line.Trim()
        if ($line -eq "") { continue }

        $reqId = $null
        $res = $null
        try {
            $req = $line | ConvertFrom-Json
            if ($null -ne $req.id) { $reqId = $req.id }
            $opName = [string]$req.op
            $opArgs = $req.args
            if ($null -eq $opArgs) { $opArgs = [pscustomobject]@{} }
            $res = Invoke-Op -Op $opName -A $opArgs
        } catch {
            $res = [ordered]@{ ok = $false; error = "请求解析失败: " + $_.Exception.Message }
        }
        if ($null -eq $res) { $res = [ordered]@{ ok = $false; error = "空响应" } }
        if ($null -ne $reqId) { $res["id"] = $reqId }
        $stdout.WriteLine(($res | ConvertTo-Json -Depth 8 -Compress))
        $stdout.Flush()
    }
    exit 0
}

$final = Invoke-Op -Op $Op -A $A
if ($null -eq $final) { $final = [ordered]@{ ok = $false; error = "未知 op: $Op" } }
$final | ConvertTo-Json -Depth 8 -Compress
exit 0
