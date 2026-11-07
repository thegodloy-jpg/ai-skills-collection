[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$WorkbookPath,

    [Parameter(Mandatory = $true)]
    [string]$BaselineSheetName,

    [Parameter(Mandatory = $true)]
    [string]$TuningSheetName,

    [Parameter(Mandatory = $true)]
    [string]$BaselineHeader,

    [Parameter(Mandatory = $true)]
    [string]$RatioHeader,

    [string]$BackupPath,

    [switch]$ClearMisplacedComparisonFromNotes
)

$ErrorActionPreference = 'Stop'
$culture = [Globalization.CultureInfo]::InvariantCulture

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class E2ECompareExcelWindowProcess {
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
"@

function Release-ComObject {
    param([object]$Object)
    if ($null -ne $Object -and [Runtime.InteropServices.Marshal]::IsComObject($Object)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Object)
    }
}

function Get-CellValue {
    param([object]$Cells, [int]$Row, [int]$Column)
    $cell = $null
    try {
        $cell = $Cells.Item($Row, $Column)
        return $cell.Value2
    }
    finally {
        Release-ComObject $cell
    }
}

function Get-CellFormula {
    param([object]$Cells, [int]$Row, [int]$Column)
    $cell = $null
    try {
        $cell = $Cells.Item($Row, $Column)
        return [string]$cell.Formula
    }
    finally {
        Release-ComObject $cell
    }
}

function Get-CellNumberFormat {
    param([object]$Cells, [int]$Row, [int]$Column)
    $cell = $null
    try {
        $cell = $Cells.Item($Row, $Column)
        return [string]$cell.NumberFormat
    }
    finally {
        Release-ComObject $cell
    }
}

function Set-CellText {
    param([object]$Cells, [int]$Row, [int]$Column, [string]$Value)
    $cell = $null
    try {
        $cell = $Cells.Item($Row, $Column)
        $cell.Value2 = [string]$Value
    }
    finally {
        Release-ComObject $cell
    }
}

function Set-CellNumber {
    param([object]$Cells, [int]$Row, [int]$Column, [double]$Value)
    $cell = $null
    try {
        $cell = $Cells.Item($Row, $Column)
        $cell.Value2 = [double]$Value
    }
    finally {
        Release-ComObject $cell
    }
}

function Set-CellFormula {
    param([object]$Cells, [int]$Row, [int]$Column, [string]$Formula)
    $cell = $null
    try {
        $cell = $Cells.Item($Row, $Column)
        $cell.Formula = [string]$Formula
    }
    finally {
        Release-ComObject $cell
    }
}

function Normalize-Scenario {
    param([object]$Value)
    if ($null -eq $Value) { return '' }
    return [regex]::Replace(([string]$Value).Trim(), '\s+', ' ')
}

function Make-Key {
    param([string]$Scenario, [double]$Concurrency)
    return $Scenario + [char]31 + $Concurrency.ToString('G17', $culture)
}

function Get-LastUsedRow {
    param([object]$Sheet)
    $used = $null
    $rows = $null
    try {
        $used = $Sheet.UsedRange
        $rows = $used.Rows
        return [int]($used.Row + $rows.Count - 1)
    }
    finally {
        Release-ComObject $rows
        Release-ComObject $used
    }
}

function Get-UsedColumnCount {
    param([object]$Sheet)
    $used = $null
    $columns = $null
    try {
        $used = $Sheet.UsedRange
        $columns = $used.Columns
        return [int]$columns.Count
    }
    finally {
        Release-ComObject $columns
        Release-ComObject $used
    }
}

function Find-SheetIndex {
    param([object]$Worksheets, [string]$Name)
    for ($index = 1; $index -le $Worksheets.Count; $index++) {
        $candidate = $null
        try {
            $candidate = $Worksheets.Item($index)
            if ($candidate.Name -eq $Name) { return $index }
        }
        finally {
            Release-ComObject $candidate
        }
    }
    return 0
}

function Assert-NumericClose {
    param([double]$Actual, [double]$Expected, [string]$Label)
    $tolerance = [Math]::Max(0.000001, [Math]::Abs($Expected) * 0.00000001)
    if ([Math]::Abs($Actual - $Expected) -gt $tolerance) {
        throw "$Label mismatch: actual=$Actual expected=$Expected"
    }
}

function Validate-E2E {
    param([object]$Cells, [int]$LastRow, [string]$Label)
    $checked = 0
    for ($row = 2; $row -le $LastRow; $row++) {
        $concurrencyValue = Get-CellValue $Cells $row 10
        if ($null -eq $concurrencyValue -or ([string]$concurrencyValue) -eq '') { continue }
        try {
            $concurrency = [Convert]::ToDouble($concurrencyValue, $culture)
            $perRequest = [Convert]::ToDouble((Get-CellValue $Cells $row 19), $culture)
            $total = [Convert]::ToDouble((Get-CellValue $Cells $row 20), $culture)
        }
        catch {
            throw "$Label row $row has a non-numeric concurrency or E2E throughput value."
        }
        Assert-NumericClose $total ($perRequest * $concurrency) "$Label T$row"
        $checked++
    }
    return $checked
}

function Assert-BordersMatch {
    param([object]$Cells, [int]$Row, [int]$SourceColumn, [int]$TargetColumn)
    $sourceCell = $null
    $targetCell = $null
    $sourceBorders = $null
    $targetBorders = $null
    try {
        $sourceCell = $Cells.Item($Row, $SourceColumn)
        $targetCell = $Cells.Item($Row, $TargetColumn)
        $sourceBorders = $sourceCell.Borders
        $targetBorders = $targetCell.Borders
        foreach ($index in @(7, 8, 9, 10)) {
            $sourceBorder = $null
            $targetBorder = $null
            try {
                $sourceBorder = $sourceBorders.Item($index)
                $targetBorder = $targetBorders.Item($index)
                if ([int]$sourceBorder.LineStyle -ne [int]$targetBorder.LineStyle -or [int]$sourceBorder.Weight -ne [int]$targetBorder.Weight) {
                    throw "Border mismatch at row $Row, target column $TargetColumn, edge $index."
                }
            }
            finally {
                Release-ComObject $targetBorder
                Release-ComObject $sourceBorder
            }
        }
    }
    finally {
        Release-ComObject $targetBorders
        Release-ComObject $sourceBorders
        Release-ComObject $targetCell
        Release-ComObject $sourceCell
    }
}

if (-not [IO.File]::Exists($WorkbookPath)) {
    throw "Workbook does not exist: $WorkbookPath"
}
if ([IO.Path]::GetExtension($WorkbookPath) -ne '.xlsx') {
    throw "Only .xlsx workbooks are supported: $WorkbookPath"
}
if ($BaselineSheetName -eq $TuningSheetName) {
    throw 'Baseline and tuning worksheet names must differ.'
}

$probe = $null
try {
    $probe = [IO.File]::Open($WorkbookPath, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
}
catch {
    throw "Workbook is locked or not writable. Close it in Excel before retrying: $WorkbookPath"
}
finally {
    if ($null -ne $probe) { $probe.Dispose() }
}

if ([string]::IsNullOrWhiteSpace($BackupPath)) {
    $backupDirectory = Join-Path $env:TEMP 'codex-excel-backups'
    $backupName = [IO.Path]::GetFileNameWithoutExtension($WorkbookPath) + '_before-e2e-compare_' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.xlsx'
    $BackupPath = Join-Path $backupDirectory $backupName
}
$backupParent = [IO.Path]::GetDirectoryName($BackupPath)
if (-not [IO.Directory]::Exists($backupParent)) {
    [void][IO.Directory]::CreateDirectory($backupParent)
}
Copy-Item -LiteralPath $WorkbookPath -Destination $BackupPath -Force

$excel = $null
$workbooks = $null
$workbook = $null
$worksheets = $null
$baselineSheet = $null
$tuningSheet = $null
$baselineCells = $null
$tuningCells = $null
$ownedExcelPid = 0
$saved = $false
$matched = 0
$missing = 0
$notesNonblankBefore = 0
$missingKeys = New-Object System.Collections.Generic.List[string]

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    [uint32]$excelProcessId = 0
    [void][E2ECompareExcelWindowProcess]::GetWindowThreadProcessId([IntPtr]$excel.Hwnd, [ref]$excelProcessId)
    $ownedExcelPid = [int]$excelProcessId

    $workbooks = $excel.Workbooks
    $workbook = $workbooks.Open($WorkbookPath, 0, $false)
    $worksheets = $workbook.Worksheets
    $baselineIndex = Find-SheetIndex $worksheets $BaselineSheetName
    $tuningIndex = Find-SheetIndex $worksheets $TuningSheetName
    if ($baselineIndex -eq 0) { throw "Baseline worksheet not found: $BaselineSheetName" }
    if ($tuningIndex -eq 0) { throw "Tuning worksheet not found: $TuningSheetName" }
    $baselineSheet = $worksheets.Item($baselineIndex)
    $tuningSheet = $worksheets.Item($tuningIndex)
    $baselineCells = $baselineSheet.Cells
    $tuningCells = $tuningSheet.Cells

    $baselineLastRow = Get-LastUsedRow $baselineSheet
    $tuningLastRow = Get-LastUsedRow $tuningSheet
    if ($baselineLastRow -lt 2 -or $tuningLastRow -lt 2) { throw 'Both worksheets must contain data rows.' }
    if ((Get-UsedColumnCount $baselineSheet) -ne 22) { throw 'Baseline worksheet must end at column V before comparison columns are added.' }

    $baselineE2EChecked = Validate-E2E $baselineCells $baselineLastRow 'baseline'
    $tuningE2EChecked = Validate-E2E $tuningCells $tuningLastRow 'tuning'

    $baselineMap = New-Object 'System.Collections.Generic.Dictionary[string,double]'
    $scenario = ''
    for ($row = 2; $row -le $baselineLastRow; $row++) {
        $scenarioValue = Get-CellValue $baselineCells $row 7
        if ($null -ne $scenarioValue -and -not [string]::IsNullOrWhiteSpace([string]$scenarioValue)) {
            $scenario = Normalize-Scenario $scenarioValue
        }
        $concurrencyValue = Get-CellValue $baselineCells $row 10
        if ($null -eq $concurrencyValue -or ([string]$concurrencyValue) -eq '') { continue }
        if ([string]::IsNullOrWhiteSpace($scenario)) { throw "Missing baseline scenario at row $row." }
        $concurrency = [Convert]::ToDouble($concurrencyValue, $culture)
        $total = [Convert]::ToDouble((Get-CellValue $baselineCells $row 20), $culture)
        $key = Make-Key $scenario $concurrency
        if ($baselineMap.ContainsKey($key)) { throw "Duplicate baseline scenario and concurrency at row $row." }
        $baselineMap.Add($key, $total)
    }

    for ($row = 2; $row -le $tuningLastRow; $row++) {
        $notesValue = Get-CellValue $tuningCells $row 22
        if ($null -eq $notesValue -or ([string]$notesValue) -eq '') { continue }
        $notesNonblankBefore++
        if ($ClearMisplacedComparisonFromNotes) {
            try { [void][Convert]::ToDouble($notesValue, $culture) }
            catch { throw "V$row contains text or a formula. Refusing to clear possible real notes." }
        }
    }

    $sourceHeader = $null
    $wHeader = $null
    $xHeader = $null
    $sourceData = $null
    $wData = $null
    $xData = $null
    $vData = $null
    $wColumn = $null
    $xColumn = $null
    try {
        $sourceHeader = $tuningSheet.Range('T1')
        $wHeader = $tuningSheet.Range('W1')
        $xHeader = $tuningSheet.Range('X1')
        [void]$sourceHeader.Copy($wHeader)
        [void]$sourceHeader.Copy($xHeader)

        $sourceData = $tuningSheet.Range("T2:T$tuningLastRow")
        $wData = $tuningSheet.Range("W2:W$tuningLastRow")
        $xData = $tuningSheet.Range("X2:X$tuningLastRow")
        [void]$sourceData.Copy($wData)
        [void]$sourceData.Copy($xData)
        [void]$wData.ClearContents()
        [void]$xData.ClearContents()
        $xData.NumberFormat = '0.00%'

        if ($ClearMisplacedComparisonFromNotes) {
            $vData = $tuningSheet.Range("V2:V$tuningLastRow")
            [void]$vData.ClearContents()
        }

        $wColumn = $tuningSheet.Columns.Item(23)
        $xColumn = $tuningSheet.Columns.Item(24)
        $wColumn.ColumnWidth = 24
        $xColumn.ColumnWidth = 28
    }
    finally {
        Release-ComObject $xColumn
        Release-ComObject $wColumn
        Release-ComObject $vData
        Release-ComObject $xData
        Release-ComObject $wData
        Release-ComObject $sourceData
        Release-ComObject $xHeader
        Release-ComObject $wHeader
        Release-ComObject $sourceHeader
    }

    Set-CellText $tuningCells 1 23 $BaselineHeader
    Set-CellText $tuningCells 1 24 $RatioHeader

    $scenario = ''
    for ($row = 2; $row -le $tuningLastRow; $row++) {
        $scenarioValue = Get-CellValue $tuningCells $row 7
        if ($null -ne $scenarioValue -and -not [string]::IsNullOrWhiteSpace([string]$scenarioValue)) {
            $scenario = Normalize-Scenario $scenarioValue
        }
        $concurrencyValue = Get-CellValue $tuningCells $row 10
        if ($null -eq $concurrencyValue -or ([string]$concurrencyValue) -eq '') { continue }
        if ([string]::IsNullOrWhiteSpace($scenario)) { throw "Missing tuning scenario at row $row." }
        $concurrency = [Convert]::ToDouble($concurrencyValue, $culture)
        $key = Make-Key $scenario $concurrency
        if ($baselineMap.ContainsKey($key)) {
            Set-CellNumber $tuningCells $row 23 ([double]$baselineMap[$key])
            Set-CellFormula $tuningCells $row 24 ('=IFERROR((T{0}-W{0})/W{0},"")' -f $row)
            $matched++
        }
        else {
            $missing++
            $missingKeys.Add("$scenario @ C$concurrency")
        }
    }

    $excel.CalculateFull()
    $workbook.Save()
    $saved = $true

    $workbook.Close($false)
    Release-ComObject $tuningCells; $tuningCells = $null
    Release-ComObject $baselineCells; $baselineCells = $null
    Release-ComObject $tuningSheet; $tuningSheet = $null
    Release-ComObject $baselineSheet; $baselineSheet = $null
    Release-ComObject $worksheets; $worksheets = $null
    Release-ComObject $workbook; $workbook = $null

    $workbook = $workbooks.Open($WorkbookPath, 0, $true)
    $worksheets = $workbook.Worksheets
    $baselineIndex = Find-SheetIndex $worksheets $BaselineSheetName
    $tuningIndex = Find-SheetIndex $worksheets $TuningSheetName
    if ($baselineIndex -eq 0 -or $tuningIndex -eq 0) { throw 'Worksheet names changed after saving.' }
    $baselineSheet = $worksheets.Item($baselineIndex)
    $tuningSheet = $worksheets.Item($tuningIndex)
    $baselineCells = $baselineSheet.Cells
    $tuningCells = $tuningSheet.Cells

    if ((Get-UsedColumnCount $baselineSheet) -ne 22) { throw 'Saved baseline worksheet does not end at V.' }
    if ((Get-UsedColumnCount $tuningSheet) -ne 24) { throw 'Saved tuning worksheet does not end at X.' }
    if ([string](Get-CellValue $tuningCells 1 23) -ne $BaselineHeader) { throw 'Saved W header is incorrect.' }
    if ([string](Get-CellValue $tuningCells 1 24) -ne $RatioHeader) { throw 'Saved X header is incorrect.' }

    $baselineLastRow = Get-LastUsedRow $baselineSheet
    $tuningLastRow = Get-LastUsedRow $tuningSheet
    $validationBaseMap = New-Object 'System.Collections.Generic.Dictionary[string,double]'
    $scenario = ''
    for ($row = 2; $row -le $baselineLastRow; $row++) {
        $scenarioValue = Get-CellValue $baselineCells $row 7
        if ($null -ne $scenarioValue -and -not [string]::IsNullOrWhiteSpace([string]$scenarioValue)) { $scenario = Normalize-Scenario $scenarioValue }
        $concurrencyValue = Get-CellValue $baselineCells $row 10
        if ($null -eq $concurrencyValue -or ([string]$concurrencyValue) -eq '') { continue }
        $concurrency = [Convert]::ToDouble($concurrencyValue, $culture)
        $total = [Convert]::ToDouble((Get-CellValue $baselineCells $row 20), $culture)
        $validationBaseMap.Add((Make-Key $scenario $concurrency), $total)
    }

    $validatedMatched = 0
    $validatedMissing = 0
    $notesNonblankAfter = 0
    $scenario = ''
    for ($row = 2; $row -le $tuningLastRow; $row++) {
        $notesValue = Get-CellValue $tuningCells $row 22
        if ($null -ne $notesValue -and ([string]$notesValue) -ne '') { $notesNonblankAfter++ }

        $scenarioValue = Get-CellValue $tuningCells $row 7
        if ($null -ne $scenarioValue -and -not [string]::IsNullOrWhiteSpace([string]$scenarioValue)) { $scenario = Normalize-Scenario $scenarioValue }
        $concurrencyValue = Get-CellValue $tuningCells $row 10
        if ($null -eq $concurrencyValue -or ([string]$concurrencyValue) -eq '') { continue }
        $concurrency = [Convert]::ToDouble($concurrencyValue, $culture)
        $total = [Convert]::ToDouble((Get-CellValue $tuningCells $row 20), $culture)
        $key = Make-Key $scenario $concurrency
        $wValue = Get-CellValue $tuningCells $row 23
        $xValue = Get-CellValue $tuningCells $row 24
        $xFormula = Get-CellFormula $tuningCells $row 24
        if ($validationBaseMap.ContainsKey($key)) {
            $baselineTotal = $validationBaseMap[$key]
            Assert-NumericClose ([Convert]::ToDouble($wValue, $culture)) $baselineTotal "W$row"
            $expectedFormula = '=IFERROR((T{0}-W{0})/W{0},"")' -f $row
            if ($xFormula -ne $expectedFormula) { throw "Unexpected formula at X${row}: $xFormula" }
            Assert-NumericClose ([Convert]::ToDouble($xValue, $culture)) (($total - $baselineTotal) / $baselineTotal) "X$row"
            if ((Get-CellNumberFormat $tuningCells $row 24) -ne '0.00%') { throw "Unexpected number format at X$row." }
            $validatedMatched++
        }
        else {
            if (($null -ne $wValue -and ([string]$wValue) -ne '') -or ($null -ne $xValue -and ([string]$xValue) -ne '') -or $xFormula.StartsWith('=')) {
                throw "W/X must be blank without a same-concurrency baseline at row $row."
            }
            $validatedMissing++
        }
        Assert-BordersMatch $tuningCells $row 20 23
        Assert-BordersMatch $tuningCells $row 20 24
    }
    Assert-BordersMatch $tuningCells 1 20 23
    Assert-BordersMatch $tuningCells 1 20 24

    if ($validatedMatched -ne $matched -or $validatedMissing -ne $missing) { throw 'Validation counts differ from write counts.' }
    if ($ClearMisplacedComparisonFromNotes) {
        if ($notesNonblankAfter -ne 0) { throw 'Column V was requested to be cleared but still contains data.' }
    }
    elseif ($notesNonblankAfter -ne $notesNonblankBefore) {
        throw 'Column V notes changed unexpectedly.'
    }

    Write-Output ('BASE_SHEET=' + $baselineSheet.Name)
    Write-Output ('TUNING_SHEET=' + $tuningSheet.Name)
    Write-Output ('BASE_E2E_CHECKED=' + $baselineE2EChecked)
    Write-Output ('TUNING_E2E_CHECKED=' + $tuningE2EChecked)
    Write-Output ('MATCHED=' + $validatedMatched)
    Write-Output ('MISSING=' + $validatedMissing)
    Write-Output ('MISSING_KEYS=' + ($missingKeys -join ' || '))
    Write-Output ('NOTES_NONBLANK_BEFORE=' + $notesNonblankBefore)
    Write-Output ('NOTES_NONBLANK_AFTER=' + $notesNonblankAfter)
    Write-Output ('BACKUP=' + $BackupPath)
    Write-Output ('SAVED=' + $WorkbookPath)
    Write-Output 'VALIDATION=PASS'
}
catch {
    Write-Error ("E2E_COMPARE_FAILED: {0}`nSTACK: {1}" -f $_.Exception.Message, $_.ScriptStackTrace)
    throw
}
finally {
    if ($null -ne $workbook) {
        try { $workbook.Close($false) } catch {}
    }
    Release-ComObject $tuningCells
    Release-ComObject $baselineCells
    Release-ComObject $tuningSheet
    Release-ComObject $baselineSheet
    Release-ComObject $worksheets
    Release-ComObject $workbook
    Release-ComObject $workbooks
    if ($null -ne $excel) {
        try { $excel.Quit() } catch {}
    }
    Release-ComObject $excel
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()

    if ($ownedExcelPid -gt 0) {
        Start-Sleep -Milliseconds 800
        $ownedProcess = Get-Process -Id $ownedExcelPid -ErrorAction SilentlyContinue
        if ($null -ne $ownedProcess) {
            Stop-Process -Id $ownedExcelPid -Force
            Wait-Process -Id $ownedExcelPid -ErrorAction SilentlyContinue
            Write-Output ('CLEANED_OWN_EXCEL_PID=' + $ownedExcelPid)
        }
        else {
            Write-Output ('OWN_EXCEL_EXITED=' + $ownedExcelPid)
        }
    }
}
