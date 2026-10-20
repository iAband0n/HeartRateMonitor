#requires -Version 5.1
<#
    一键构建 Windows 发布版：
      1) PyInstaller onedir 输出：dist_onedir/HeartRateOverlay/
      2) 免安装单文件版：release/心率悬浮窗.exe
      3) 安装包：release/心率悬浮窗安装程序.exe

    安装版把运行文件解压到用户选择的安装目录，缓存保存在安装目录的 cache\。
#>
param(
    [switch]$SkipInstall,
    [string]$CertificateThumbprint = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "Creating .venv ..."
    python -m venv --copies .venv
}

if (-not $SkipInstall) {
    Write-Host "Installing dependencies ..."
    & $Python -m pip install -r requirements-dev.txt
}

New-Item -ItemType Directory -Force build\tmp, build_onedir\tmp, dist_onedir, release | Out-Null
$env:TEMP = (Resolve-Path "build\tmp").Path
$env:TMP = $env:TEMP

Write-Host "Building onedir runtime ..."
& $Python tools\pyinstaller_run.py --noconfirm --clean --workpath build_onedir --distpath dist_onedir HeartRateOverlay_onedir.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$singleScript = Join-Path $Root "tools\build_single_exe.ps1"
$psExe = Join-Path $PSHOME "powershell.exe"
if (-not (Test-Path $psExe)) { $psExe = "powershell.exe" }

Write-Host "Packaging single-file exe ..."
$packageArgs = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $singleScript,
    '-SkipBuild', '-SourceDir', 'dist_onedir\HeartRateOverlay',
    '-Output', 'release\心率悬浮窗.exe'
)
if ($CertificateThumbprint) {
    $packageArgs += @('-CertificateThumbprint', $CertificateThumbprint)
}
& $psExe @packageArgs
if ($LASTEXITCODE -ne 0) { throw "Single-file packaging failed" }

Write-Host "Build finished: release\心率悬浮窗.exe"

$installerScript = Join-Path $Root "tools\build_installer.ps1"
Write-Host "Packaging installer ..."
& $psExe -NoProfile -ExecutionPolicy Bypass -File $installerScript
if ($LASTEXITCODE -ne 0) { throw "Installer packaging failed" }

Write-Host "Build finished: release\心率悬浮窗安装程序.exe"
