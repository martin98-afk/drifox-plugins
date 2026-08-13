[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectDir,

    [ValidateSet('auto', 'claude', 'codex', 'both', 'manual')]
    [string]$Platform = 'auto'
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $ProjectDir -PathType Container)) {
    throw "ProjectDir does not exist or is not a directory: $ProjectDir"
}

$resolvedProject = (Resolve-Path -LiteralPath $ProjectDir).Path
$installer = Join-Path $PSScriptRoot 'scripts\install_memory_3layer.py'

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & $python.Source $installer --project-dir $resolvedProject --platform $Platform
    exit $LASTEXITCODE
}

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    & $py.Source -3 $installer --project-dir $resolvedProject --platform $Platform
    exit $LASTEXITCODE
}

throw 'Python 3 was not found on PATH. Install Python 3, then rerun this wrapper.'
