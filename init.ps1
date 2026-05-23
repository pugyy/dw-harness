# init.ps1 - dw-harness 初始化脚本
# 用法: .\init.ps1 C:\path\to\your-dw-project

param(
    [Parameter(Mandatory=$false)]
    [string]$Target
)

if (-not $Target) {
    Write-Host "用法 / Usage: .\init.ps1 C:\path\to\your-dw-project"
    exit 1
}

$ErrorActionPreference = "Stop"
$Source = Join-Path $PSScriptRoot "template\.claude"
$TargetClaude = Join-Path $Target ".claude"

if (-not (Test-Path $Source)) {
    Write-Host "错误: 找不到模板目录 template\.claude"
    Write-Host "Error: template directory not found at template\.claude"
    exit 1
}

if (-not (Test-Path $Target)) {
    $answer = Read-Host "目标目录不存在，是否创建? / Target not found. Create it? (y/n)"
    if ($answer -eq "y" -or $answer -eq "Y") {
        New-Item -ItemType Directory -Path $Target -Force | Out-Null
    } else {
        exit 0
    }
}

if (Test-Path $TargetClaude) {
    $answer = Read-Host "$TargetClaude 已存在，是否覆盖? / Already exists. Overwrite? (y/n)"
    if ($answer -ne "y" -and $answer -ne "Y") {
        Write-Host "已取消 / Aborted"
        exit 0
    }
    Remove-Item -Recurse -Force $TargetClaude
}

Copy-Item -Recurse $Source $TargetClaude

Write-Host ""
Write-Host "========================================"
Write-Host "  模板已复制到 / Template copied to:"
Write-Host "  $TargetClaude"
Write-Host "========================================"
Write-Host ""
Write-Host "下一步 / Next steps:"
Write-Host ""
Write-Host "  1. 编辑 CLAUDE.md，填写你的项目信息 / Edit CLAUDE.md:"
Write-Host "     $TargetClaude\CLAUDE.md"
Write-Host ""
Write-Host "  2. 如果你的系统只有 python3，改一下 settings.json 里的命令"
Write-Host "     If you only have python3, update commands in settings.json:"
Write-Host "     (Get-Content $TargetClaude\settings.json) -replace 'python ', 'python3 ' | Set-Content $TargetClaude\settings.json"
Write-Host ""
Write-Host "  3. 启动 Claude Code / Start Claude Code:"
Write-Host "     Set-Location $Target; claude"
Write-Host ""

$answer = Read-Host "是否现在编辑 CLAUDE.md? / Edit CLAUDE.md now? (y/n)"
if ($answer -eq "y" -or $answer -eq "Y") {
    if (Get-Command code -ErrorAction SilentlyContinue) {
        code "$TargetClaude\CLAUDE.md"
    } elseif (Get-Command notepad -ErrorAction SilentlyContinue) {
        notepad "$TargetClaude\CLAUDE.md"
    }
}
