# 创建一键启动的桌面快捷方式：scripts/create-shortcut.ps1 -Target <exe|bat> [-Name CleanSearch] [-Icon <ico>]
# 只写用户桌面，不改注册表、不装服务。
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Target,
    [string]$Name = "CleanSearch",
    [string]$Icon,
    [string]$WorkDir
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $Target)) { throw "找不到目标：$Target" }
$targetPath = (Resolve-Path -LiteralPath $Target).Path
if (-not $WorkDir) { $WorkDir = Split-Path -Parent $targetPath }

# 用 web 图标生成 .ico（ICO 允许直接内嵌 PNG），省得依赖画图工具
function New-Icon {
    param([string]$Png, [string]$Out)
    if (-not (Test-Path -LiteralPath $Png)) { return $false }
    $bytes = [System.IO.File]::ReadAllBytes($Png)
    $size = [System.Drawing.Image]::FromFile((Resolve-Path -LiteralPath $Png).Path).Width
    $w = if ($size -ge 256) { 0 } else { $size }   # 0 表示 256，ICO 单字节里放不下 256
    $ico = New-Object System.IO.MemoryStream
    $bw = New-Object System.IO.BinaryWriter($ico)
    $bw.Write([UInt16]0); $bw.Write([UInt16]1); $bw.Write([UInt16]1)   # ICONDIR
    $bw.Write([Byte]$w); $bw.Write([Byte]$w); $bw.Write([Byte]0); $bw.Write([Byte]0)
    $bw.Write([UInt16]1); $bw.Write([UInt16]32)                       # planes / bpp
    $bw.Write([UInt32]$bytes.Length); $bw.Write([UInt32]22)           # 数据长度 / 偏移
    $bw.Write($bytes)
    $bw.Flush()
    [System.IO.File]::WriteAllBytes($Out, $ico.ToArray())
    $bw.Dispose(); $ico.Dispose()
    return $true
}

if (-not $Icon) {
    $candidate = Join-Path $WorkDir "web\icon-192.png"
    $icoPath = Join-Path $WorkDir "CleanSearch.ico"
    if ((Test-Path -LiteralPath $icoPath) -or (New-Icon -Png $candidate -Out $icoPath)) { $Icon = $icoPath }
}

Add-Type -AssemblyName System.Drawing
$desktop = [Environment]::GetFolderPath("Desktop")
$link = Join-Path $desktop ($Name + ".lnk")
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($link)
$sc.TargetPath = $targetPath
$sc.WorkingDirectory = $WorkDir
$sc.Description = "CleanSearch · 本机搜索与书签"
$sc.WindowStyle = 1
if ($Icon) { $sc.IconLocation = $Icon + ",0" }
$sc.Save()
Write-Host ("已创建桌面快捷方式：{0}" -f $link) -ForegroundColor Green