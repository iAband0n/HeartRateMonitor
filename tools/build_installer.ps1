#requires -Version 5.1
param(
    [string]$PayloadZip = "build_single\payload.zip",
    [string]$Output = "release\心率悬浮窗安装程序.exe"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$payload = (Resolve-Path -LiteralPath $PayloadZip).Path
$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { throw "找不到 C# 编译器：$csc" }
$work = Join-Path $root "build_installer"
if (Test-Path $work) { Remove-Item -LiteralPath $work -Recurse -Force }
New-Item -ItemType Directory -Force $work | Out-Null
$launcher = Join-Path $work "HeartRateOverlayLauncher.exe"
$uninstaller = Join-Path $work "uninstall.exe"
$installer = Join-Path $root $Output
New-Item -ItemType Directory -Force (Split-Path -Parent $installer) | Out-Null

& $csc /nologo /target:winexe /platform:x64 /optimize+ /codepage:65001 `
    ("/win32icon:" + (Resolve-Path "assets\heart.ico").Path) `
    ("/win32manifest:" + (Resolve-Path "app.manifest").Path) `
    ("/out:" + $launcher) `
    "/r:System.dll" "/r:System.Core.dll" `
    (Resolve-Path "tools\installed_launcher\InstalledLauncher.cs").Path
if ($LASTEXITCODE -ne 0) { throw "安装后启动器编译失败" }

& $csc /nologo /target:winexe /platform:x64 /optimize+ /codepage:65001 `
    ("/win32icon:" + (Resolve-Path "assets\heart.ico").Path) `
    ("/win32manifest:" + (Resolve-Path "tools\installer.manifest").Path) `
    ("/out:" + $uninstaller) `
    "/r:System.dll" "/r:System.Core.dll" "/r:System.Windows.Forms.dll" `
    (Resolve-Path "tools\uninstaller\Uninstaller.cs").Path
if ($LASTEXITCODE -ne 0) { throw "卸载程序编译失败" }

& $csc /nologo /target:winexe /platform:x64 /optimize+ /codepage:65001 `
    ("/win32icon:" + (Resolve-Path "assets\heart.ico").Path) `
    ("/win32manifest:" + (Resolve-Path "tools\installer.manifest").Path) `
    ("/out:" + $installer) `
    ("/resource:" + $payload + ",payload.zip") `
    ("/resource:" + $launcher + ",installed-launcher.exe") `
    ("/resource:" + $uninstaller + ",uninstaller.exe") `
    "/r:System.dll" "/r:System.Core.dll" "/r:System.Drawing.dll" `
    "/r:System.IO.Compression.dll" "/r:System.IO.Compression.FileSystem.dll" `
    "/r:System.Windows.Forms.dll" "/r:Microsoft.CSharp.dll" `
    (Resolve-Path "tools\installer\Installer.cs").Path
if ($LASTEXITCODE -ne 0) { throw "安装程序编译失败" }
Unblock-File -LiteralPath $installer -ErrorAction SilentlyContinue
$hash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "Built $installer"
Write-Host "SHA256 $hash"
