<#
.SYNOPSIS
    Ставит FamilyVersionStamp в Revit на этой машине одним запуском: без
    параметров сам находит установленные версии Revit, копирует DLL в
    стабильную папку профиля пользователя и кладёт .addin-манифест в папку
    Addins каждой найденной версии.

.PARAMETER RevitVersion
    Поставить только для одной конкретной версии Revit (например "2025"),
    вместо автоопределения всех установленных версий.

.PARAMETER AllUsers
    Установить в %ProgramData% (для всех пользователей) вместо %APPDATA%
    (текущий пользователь). Требует прав администратора.

.EXAMPLE
    .\install.ps1
    .\install.ps1 -RevitVersion 2025
#>
param(
    [string]$RevitVersion,
    [switch]$AllUsers
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# ------------------------------------------------------------
# 1. Найти DLL: готовая сборка в dist/ (не нужен .NET SDK) -> уже собранная
#    в bin/Release/ -> собрать самим, если стоит .NET SDK.
# ------------------------------------------------------------

$distDll = Join-Path $root "dist\FamilyVersionStamp.dll"
$builtDll = Join-Path $root "bin\Release\FamilyVersionStamp.dll"
$sourceDll = $null
$builtFresh = $false

if (Test-Path $builtDll) {
    $sourceDll = $builtDll
} elseif (Test-Path $distDll) {
    $sourceDll = $distDll
} else {
    Write-Host "Готовой DLL не найдено - пробую собрать (.NET SDK)..."
    $dotnet = Join-Path $env:USERPROFILE ".dotnet\dotnet.exe"
    if (-not (Test-Path $dotnet)) { $dotnet = "dotnet" }
    $buildForVersion = if ($RevitVersion) { $RevitVersion } else { "2024" }
    $revitInstallDir = "C:\Program Files\Autodesk\Revit $buildForVersion"
    & $dotnet build "$root\FamilyVersionStamp.csproj" -c Release "-p:RevitInstallDir=$revitInstallDir"
    if ($LASTEXITCODE -ne 0) { throw "Сборка не удалась, и готовой DLL нет ни в dist/, ни в bin/Release/." }
    $sourceDll = $builtDll
    $builtFresh = $true
}

# ------------------------------------------------------------
# 2. Скопировать DLL в стабильную папку профиля - манифест будет указывать
#    сюда, а не на путь склонированного репозитория (который может
#    переехать/пропасть).
# ------------------------------------------------------------

$installDir = Join-Path $env:LOCALAPPDATA "LowLife\FamilyVersionStamp"
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
$installedDll = Join-Path $installDir "FamilyVersionStamp.dll"
Copy-Item $sourceDll $installedDll -Force

# ------------------------------------------------------------
# 3. Определить версии Revit.
# ------------------------------------------------------------

if ($RevitVersion) {
    $versions = @($RevitVersion)
} else {
    $versions = @(
        Get-ChildItem "C:\Program Files\Autodesk" -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^Revit (\d{4})$' } |
            ForEach-Object { $Matches[1] } |
            Sort-Object -Unique
    )
}

if (-not $versions -or $versions.Count -eq 0) {
    Write-Host "Установленный Revit не найден в 'C:\Program Files\Autodesk' - ставлю манифест для 2024 по умолчанию."
    $versions = @("2024")
}

# ------------------------------------------------------------
# 4. Записать .addin-манифест для каждой версии.
# ------------------------------------------------------------

$addinTemplate = Join-Path $root "FamilyVersionStamp.addin"
$addinsRoot = if ($AllUsers) { $env:ProgramData } else { $env:APPDATA }

foreach ($v in $versions) {
    [xml]$xml = Get-Content $addinTemplate -Encoding UTF8
    $xml.SelectSingleNode("//Assembly").InnerText = $installedDll

    $targetDir = Join-Path $addinsRoot "Autodesk\Revit\Addins\$v"
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

    $targetFile = Join-Path $targetDir "FamilyVersionStamp.addin"
    $xml.Save($targetFile)

    Write-Host "Revit ${v}: манифест -> $targetFile"
}

Write-Host ""
Write-Host "DLL: $installedDll"
if (-not $builtFresh -and $sourceDll -eq $distDll -and $versions.Count -gt 0 -and ($versions | Where-Object { $_ -ne "2024" })) {
    Write-Host "Внимание: DLL из dist/ собрана под Revit API 2024 - для версий Revit, отличных от 2024, она может не загрузиться (RevitAPI.dll между мажорными версиями меняется). Для другой версии поставьте .NET SDK и запустите: .\install.ps1 -RevitVersion <версия>"
}
Write-Host ""
Write-Host "Перезапустите Revit - команда появится в Надстройки -> Внешние инструменты."

