[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$InputPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [Parameter(Mandatory = $true)]
    [string]$ModelName,

    [Parameter(Mandatory = $true)]
    [string]$CardMachine,

    [Parameter(Mandatory = $true)]
    [string]$BaselineSheetName,

    [Parameter(Mandatory = $true)]
    [string]$TuningSheetName,

    [Parameter(Mandatory = $true)]
    [string]$BaselineHeader,

    [Parameter(Mandatory = $true)]
    [string]$RatioHeader,

    [string]$ManifestPath,

    [string]$WorkDirectory,

    [string]$BackupPath,

    [switch]$Overwrite
)

$ErrorActionPreference = 'Stop'

function Get-ExcelProcessIds {
    return @(Get-Process EXCEL -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
}

function Assert-NoNewExcelProcesses {
    param([int[]]$BeforeIds, [string]$Label)
    $newIds = @()
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        $afterIds = Get-ExcelProcessIds
        $newIds = @($afterIds | Where-Object { $_ -notin $BeforeIds })
        if ($newIds.Count -eq 0) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "$Label left unexpected EXCEL.EXE process IDs: $($newIds -join ',')"
}

if (-not (Test-Path -LiteralPath $InputPath)) {
    throw "Input path does not exist: $InputPath"
}
if ([IO.Path]::GetExtension($OutputPath).ToLowerInvariant() -ne '.xlsx') {
    throw "Output path must end in .xlsx: $OutputPath"
}
if ($BaselineSheetName -eq $TuningSheetName) {
    throw 'Baseline and tuning worksheet names must differ.'
}
foreach ($sheetName in @($BaselineSheetName, $TuningSheetName)) {
    if ($sheetName.Length -gt 31) { throw "Worksheet name exceeds 31 characters: $sheetName" }
    if ($sheetName -match '[:\\/\?\*\[\]]') { throw "Worksheet name contains an invalid Excel character: $sheetName" }
}
if (-not [string]::IsNullOrWhiteSpace($ManifestPath) -and -not (Test-Path -LiteralPath $ManifestPath)) {
    throw "Manifest does not exist: $ManifestPath"
}

$resolvedOutputPath = [IO.Path]::GetFullPath($OutputPath)
$outputExists = Test-Path -LiteralPath $resolvedOutputPath
if ($outputExists -and -not $Overwrite) {
    throw "Output already exists. Choose a new path or pass -Overwrite: $resolvedOutputPath"
}
if ($outputExists) {
    $probe = $null
    try {
        $probe = [IO.File]::Open($resolvedOutputPath, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    }
    catch {
        throw "Existing output is locked or not writable: $resolvedOutputPath"
    }
    finally {
        if ($null -ne $probe) { $probe.Dispose() }
    }
}

$skillRoot = Split-Path -Parent $PSScriptRoot
$skillsRoot = Split-Path -Parent $skillRoot
$normalizer = Join-Path $PSScriptRoot 'normalize_scattered_perf.py'
$e2eUpdater = Join-Path $PSScriptRoot 'update_e2e_compare.ps1'
$perfGenerator = Join-Path $skillsRoot 'perf-benchmark\scripts\build_perf_xlsx.ps1'
foreach ($dependency in @($normalizer, $e2eUpdater, $perfGenerator)) {
    if (-not (Test-Path -LiteralPath $dependency)) { throw "Required dependency is missing: $dependency" }
}

if ([string]::IsNullOrWhiteSpace($WorkDirectory)) {
    $WorkDirectory = Join-Path $env:TEMP 'perf-e2e-compare-builds'
}
if (-not (Test-Path -LiteralPath $WorkDirectory)) {
    [void](New-Item -ItemType Directory -Path $WorkDirectory)
}
$runName = 'run-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + ([Guid]::NewGuid().ToString('N').Substring(0, 8))
$runDirectory = Join-Path ([IO.Path]::GetFullPath($WorkDirectory)) $runName
$normalizedDirectory = Join-Path $runDirectory 'normalized'
[void](New-Item -ItemType Directory -Path $normalizedDirectory)

$normalizerArgs = @(
    '-X', 'utf8', $normalizer,
    '--input', ([IO.Path]::GetFullPath($InputPath)),
    '--output-dir', $normalizedDirectory,
    '--exclude', $resolvedOutputPath
)
if (-not [string]::IsNullOrWhiteSpace($ManifestPath)) {
    $normalizerArgs += @('--manifest', ([IO.Path]::GetFullPath($ManifestPath)))
}
$normalizerOutput = & python @normalizerArgs 2>&1
$normalizerExit = $LASTEXITCODE
$normalizerOutput | Write-Output
if ($normalizerExit -ne 0 -or -not ($normalizerOutput -match 'NORMALIZATION=PASS')) {
    throw "Normalization failed. Inspect: $(Join-Path $normalizedDirectory 'normalization-report.json')"
}

$baselineCsv = Join-Path $normalizedDirectory 'baseline.csv'
$tuningCsv = Join-Path $normalizedDirectory 'tuning.csv'
$normalizationReport = Join-Path $normalizedDirectory 'normalization-report.json'
foreach ($normalizedArtifact in @($baselineCsv, $tuningCsv, $normalizationReport)) {
    if (-not (Test-Path -LiteralPath $normalizedArtifact)) { throw "Expected normalization artifact is missing: $normalizedArtifact" }
}

$stagedWorkbook = Join-Path $runDirectory 'staged-performance-report.xlsx'
$excelBeforeGenerator = Get-ExcelProcessIds
$generatorOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $perfGenerator `
    -OutputPath $stagedWorkbook `
    -BaseCsv $baselineCsv `
    -TuningCsv $tuningCsv `
    -CardMachine $CardMachine `
    -ModelName $ModelName `
    -SheetBaselineName $BaselineSheetName `
    -SheetTuningName $TuningSheetName 2>&1
$generatorExit = $LASTEXITCODE
$generatorOutput | Write-Output
Assert-NoNewExcelProcesses $excelBeforeGenerator 'perf-benchmark generator'
if ($generatorExit -ne 0 -or -not ($generatorOutput -match 'OK:')) {
    throw "Workbook generation failed with exit code $generatorExit"
}
if (-not (Test-Path -LiteralPath $stagedWorkbook)) { throw "Generated workbook is missing: $stagedWorkbook" }

$e2eOutput = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $e2eUpdater `
    -WorkbookPath $stagedWorkbook `
    -BaselineSheetName $BaselineSheetName `
    -TuningSheetName $TuningSheetName `
    -BaselineHeader $BaselineHeader `
    -RatioHeader $RatioHeader 2>&1
$e2eExit = $LASTEXITCODE
$e2eOutput | Write-Output
if ($e2eExit -ne 0 -or -not ($e2eOutput -match 'VALIDATION=PASS')) {
    throw "E2E comparison validation failed with exit code $e2eExit"
}

$outputParent = [IO.Path]::GetDirectoryName($resolvedOutputPath)
if (-not (Test-Path -LiteralPath $outputParent)) {
    [void](New-Item -ItemType Directory -Path $outputParent)
}

$publishedBackup = ''
if ($outputExists) {
    if ([string]::IsNullOrWhiteSpace($BackupPath)) {
        $backupDirectory = Join-Path $env:TEMP 'codex-excel-backups'
        if (-not (Test-Path -LiteralPath $backupDirectory)) { [void](New-Item -ItemType Directory -Path $backupDirectory) }
        $backupName = [IO.Path]::GetFileNameWithoutExtension($resolvedOutputPath) + '_before-scattered-build_' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.xlsx'
        $BackupPath = Join-Path $backupDirectory $backupName
    }
    $backupParent = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($BackupPath))
    if (-not (Test-Path -LiteralPath $backupParent)) { [void](New-Item -ItemType Directory -Path $backupParent) }
    Copy-Item -LiteralPath $resolvedOutputPath -Destination $BackupPath -Force
    $publishedBackup = [IO.Path]::GetFullPath($BackupPath)
}

$stagedHash = (Get-FileHash -LiteralPath $stagedWorkbook -Algorithm SHA256).Hash
Copy-Item -LiteralPath $stagedWorkbook -Destination $resolvedOutputPath -Force
$outputHash = (Get-FileHash -LiteralPath $resolvedOutputPath -Algorithm SHA256).Hash
if ($stagedHash -ne $outputHash) { throw 'Published workbook hash differs from the validated staged workbook.' }

$lockPath = Join-Path $outputParent ('~$' + [IO.Path]::GetFileName($resolvedOutputPath))
if (Test-Path -LiteralPath $lockPath) { throw "Unexpected output lock file exists: $lockPath" }

Write-Output ('NORMALIZATION_REPORT=' + $normalizationReport)
Write-Output ('EVIDENCE_DIR=' + $runDirectory)
Write-Output ('PUBLISHED_BACKUP=' + $publishedBackup)
Write-Output ('OUTPUT=' + $resolvedOutputPath)
Write-Output ('OUTPUT_SHA256=' + $outputHash)
Write-Output 'BUILD_VALIDATION=PASS'
