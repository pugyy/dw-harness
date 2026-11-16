# init.ps1 — thin wrapper over the dw CLI (merge-style, never destructive)
# usage: .\init.ps1 C:\path\to\your-dw-project [-DryRun] [-Mcp]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$dw = Get-Command dw -ErrorAction SilentlyContinue
if ($dw) {
    & dw init @Rest
    exit $LASTEXITCODE
}

$Python = if ($env:DW_PYTHON) { $env:DW_PYTHON } else { "python" }
$env:PYTHONPATH = "$ScriptDir\src;$env:PYTHONPATH"
& $Python -m dw_core.cli init @Rest
exit $LASTEXITCODE
