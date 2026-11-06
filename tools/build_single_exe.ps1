#requires -Version 5.1
<#
    将 PyInstaller onedir 输出封装成一个真正的单文件 exe。

    原理：把 onedir 的 exe + _internal 压缩成 payload.zip，作为 .NET 资源嵌入
    一个很小的 C# 启动器。启动器首次运行时把 payload 解压到
    %LOCALAPPDATA%\HeartRateOverlay\runtime\v1.1.0，然后启动主程序。
    这样不依赖 PyInstaller 的 onefile 临时解包逻辑，也不会出现
    "Could not create temporary directory!"。

    用法：
      .\tools\build_single_exe.ps1 -Version 1.1.0
      .\tools\build_single_exe.ps1 -SkipBuild -SourceDir release
#>
param(
    [string]$Version = "1.1.0",
    [string]$SourceDir = "dist_onedir\HeartRateOverlay",
    [string]$Output = "release\心率悬浮窗.exe",
    [string]$ExistingPayload = "",
    [string]$CertificateThumbprint = "",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not $SkipBuild -and -not $ExistingPayload) {
    if (-not (Test-Path $Python)) {
        throw "找不到 $Python，请先创建 .venv 并安装 requirements-dev.txt"
    }
    Write-Host "Building onedir payload ..."
    & $Python -m PyInstaller --noconfirm --clean --distpath dist_onedir HeartRateOverlay_onedir.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
}

if ($ExistingPayload) {
    $payloadZip = (Resolve-Path -LiteralPath $ExistingPayload).Path
} else {
    $source = Resolve-Path $SourceDir
    $sourceExe = Join-Path $source "HeartRateOverlay.exe"
    if (-not (Test-Path $sourceExe)) {
        $sourceExe = Join-Path $source "心率悬浮窗.exe"
    }
    if (-not (Test-Path $sourceExe)) {
        throw "找不到源 exe：$SourceDir\HeartRateOverlay.exe 或 心率悬浮窗.exe"
    }
    if (-not (Test-Path (Join-Path $source "_internal"))) {
        throw "源目录缺少 _internal：$source"
    }

    $buildDir = Join-Path $Root "build_single"
    $payloadDir = Join-Path $buildDir "payload"
    $payloadZip = Join-Path $buildDir "payload.zip"
    if (Test-Path $buildDir) {
        $resolvedBuild = (Resolve-Path -LiteralPath $buildDir).Path
        if ($resolvedBuild -ne (Join-Path $Root 'build_single')) {
            throw "拒绝清理非预期构建目录：$resolvedBuild"
        }
        Remove-Item -LiteralPath $resolvedBuild -Recurse -Force
    }
    New-Item -ItemType Directory -Force $payloadDir | Out-Null

    Write-Host "Collecting payload ..."
    Copy-Item $sourceExe (Join-Path $payloadDir "心率悬浮窗.exe")
    Copy-Item (Join-Path $source "_internal") (Join-Path $payloadDir "_internal") -Recurse

    Write-Host "Compressing payload ..."
    Compress-Archive -Path (Join-Path $payloadDir "*") -DestinationPath $payloadZip -CompressionLevel Optimal
}

$csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) {
    throw "找不到 .NET Framework C# 编译器：$csc"
}

$outPath = Join-Path $Root $Output
$outDir = Split-Path -Parent $outPath
New-Item -ItemType Directory -Force $outDir | Out-Null
$launcher = Join-Path $Root "tools\launcher\Launcher.cs"
$icon = Join-Path $Root "assets\heart.ico"

$cscArgs = @(
    "/nologo",
    "/target:winexe",
    "/platform:x64",
    "/optimize+",
    "/codepage:65001",
    "/win32icon:$icon",
    "/win32manifest:$(Join-Path $Root 'app.manifest')",
    "/out:$outPath",
    "/resource:$payloadZip,payload.zip",
    "/r:System.dll",
    "/r:System.Core.dll",
    "/r:System.IO.Compression.dll",
    "/r:System.IO.Compression.FileSystem.dll",
    "/r:System.Windows.Forms.dll",
    $launcher
)

Write-Host "Compiling single-file launcher ..."
& $csc @cscArgs
if ($LASTEXITCODE -ne 0) { throw "C# compiler failed" }

if ($CertificateThumbprint) {
    $thumbprint = $CertificateThumbprint.Replace(" ", "").ToUpperInvariant()
    $certificate = Get-ChildItem Cert:\CurrentUser\My |
        Where-Object { $_.Thumbprint -eq $thumbprint -and $_.HasPrivateKey } |
        Select-Object -First 1
    if (-not $certificate) {
        throw "当前用户证书存储区中找不到带私钥的签名证书：$thumbprint"
    }
    $signature = Set-AuthenticodeSignature -FilePath $outPath `
        -Certificate $certificate -HashAlgorithm SHA256
    if ($signature.Status -ne "Valid") {
        throw "代码签名失败：$($signature.StatusMessage)"
    }
    Write-Host "Signed with $($certificate.Subject)"
} else {
    Write-Warning "未提供代码签名证书；Windows SmartScreen 仍可能显示未知发布者提示。"
}

# A locally built artifact must not retain a downloaded-file mark.
Unblock-File -LiteralPath $outPath -ErrorAction SilentlyContinue

$size = [math]::Round((Get-Item $outPath).Length / 1MB, 2)
Write-Host "Built $outPath ($size MB)"
Write-Host "Embedded payload: $payloadZip"
