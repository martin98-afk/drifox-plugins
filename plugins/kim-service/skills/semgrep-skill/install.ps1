# claude-code-security-skill installer for Windows
# Run: powershell -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"

$SKILL_DIR = "$env:USERPROFILE\.claude\skills\code-security"
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "==================================" -ForegroundColor Cyan
Write-Host "  Claude Code Security Skill"
Write-Host "  One-Click Installer (Windows)"
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check Python
Write-Host "[1/4] Checking Python..." -ForegroundColor Yellow
$pyCmd = $null
try {
    $pyVer = & python --version 2>&1
    if ($pyVer -match "Python") {
        $pyCmd = "python"
        Write-Host "  OK $pyVer" -ForegroundColor Green
    }
} catch {}

if (-not $pyCmd) {
    try {
        $pyVer = & python3 --version 2>&1
        if ($pyVer -match "Python") {
            $pyCmd = "python3"
            Write-Host "  OK $pyVer" -ForegroundColor Green
        }
    } catch {}
}

if (-not $pyCmd) {
    Write-Host "  FAIL Python not found" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Please install Python 3.8+ first:"
    Write-Host "  https://www.python.org/downloads/"
    exit 1
}

# Step 2: Check/Install Semgrep
Write-Host "[2/4] Checking Semgrep..." -ForegroundColor Yellow
$sgInstalled = $false
try {
    $sgVer = & semgrep --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $sgInstalled = $true
        Write-Host "  OK Semgrep $sgVer" -ForegroundColor Green
    }
} catch {}

if (-not $sgInstalled) {
    Write-Host "  NOT FOUND Installing Semgrep..." -ForegroundColor Yellow
    & $pyCmd -m pip install semgrep --quiet
    try {
        $sgVer = & semgrep --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  OK Semgrep $sgVer installed" -ForegroundColor Green
        } else {
            throw "Install failed"
        }
    } catch {
        Write-Host "  FAIL Semgrep installation failed" -ForegroundColor Red
        Write-Host ""
        Write-Host "  Try manually: pip install semgrep"
        Write-Host "  Then add Python Scripts folder to PATH"
        exit 1
    }
}

# Step 3: Install Skill
Write-Host "[3/4] Installing Skill..." -ForegroundColor Yellow
$skillFile = Join-Path $SCRIPT_DIR "SKILL.md"
if (-not (Test-Path $skillFile)) {
    Write-Host "  FAIL SKILL.md not found in $SCRIPT_DIR" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $SKILL_DIR)) {
    New-Item -ItemType Directory -Path $SKILL_DIR -Force | Out-Null
}
Copy-Item $skillFile -Destination (Join-Path $SKILL_DIR "SKILL.md") -Force
Write-Host "  OK Copied to $SKILL_DIR\SKILL.md" -ForegroundColor Green

# Step 4: Verify
Write-Host "[4/4] Verifying..." -ForegroundColor Yellow
if (Test-Path (Join-Path $SKILL_DIR "SKILL.md")) {
    Write-Host "  OK Skill file exists" -ForegroundColor Green
} else {
    Write-Host "  FAIL Skill file not found after copy" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "==================================" -ForegroundColor Cyan
Write-Host "  Installation Complete!" -ForegroundColor Green
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Skill location: $SKILL_DIR\SKILL.md"
Write-Host "  Hot Reloading: No restart needed"
Write-Host ""
Write-Host "  Usage in Claude Code:"
Write-Host "    - Say: 安全扫描一下这个项目"
Write-Host "    - Say: 扫一下有没有漏洞"
Write-Host "    - Or:  /code-security"
Write-Host ""
