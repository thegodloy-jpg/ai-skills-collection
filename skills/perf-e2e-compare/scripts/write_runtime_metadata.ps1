[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$WorkbookPath,
    [Parameter(Mandatory=$true)][string]$MetadataPath,
    [Parameter(Mandatory=$true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$metadataSheetName = '运行配置'
$allowedStatuses = @('observed', 'candidate')
$secretNamePattern = '(?i)(^|[_.-])(password|passwd|pwd|secret|credential|credentials|token|bearer|api[_-]?key|access[_-]?token|auth[_-]?token|hf[_-]?token|private[_-]?key)([_.-]|$)'
$secretTextPattern = '(?i)(?:--(?:api[-_]key|password|secret|token)(?:\s+|=)\S+|\b[A-Za-z_][A-Za-z_0-9]*(?:TOKEN|PASSWORD|PASSWD|SECRET|API_KEY)\s*[:=]\s*[^\s,;]+|\b(?:token|password|passwd|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+|authorization\s*:\s*bearer\s+\S+|https?://[^/\s:@]+:[^/\s@]+@|-----BEGIN [A-Z ]*PRIVATE KEY-----)'

function Release-ComObject([object]$Object) {
    if ($null -ne $Object -and [Runtime.InteropServices.Marshal]::IsComObject($Object)) {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($Object)
    }
}

function Assert-Text([object]$Value, [string]$Field, [bool]$AllowEmpty=$false) {
    if ($null -eq $Value) { if ($AllowEmpty) { return '' }; throw "Missing required field: $Field" }
    if ($Value -isnot [string]) { throw "Field must be a string: $Field" }
    $s = [string]$Value
    if (-not $AllowEmpty -and [string]::IsNullOrWhiteSpace($s)) { throw "Missing required field: $Field" }
    if ($s.Length -gt 32767) { throw "Field exceeds Excel cell limit: $Field" }
    if ($s -match $secretTextPattern) { throw "Potential credential detected in $Field; redact before writing." }
    return $s
}

function Assert-Map([object]$Value, [string]$Field) {
    if ($null -eq $Value) { return }
    if ($Value -isnot [System.Management.Automation.PSCustomObject]) { throw "Field must be an object: $Field" }
    foreach ($p in $Value.PSObject.Properties) {
        if ($p.Name -match $secretNamePattern) { throw "Potential credential key in $Field; redact before writing." }
        [void](Assert-Text $p.Name "$Field key")
        [void](Assert-Text $p.Value "$Field value" $true)
    }
}

function Fingerprint([object]$Sheet) {
    $used = $null
    try {
        $used = $Sheet.UsedRange
        $formula = $used.Formula
        $value = $used.Value2
        $obj = [ordered]@{Name=[string]$Sheet.Name; Row=[int]$used.Row; Column=[int]$used.Column; Rows=[int]$used.Rows.Count; Columns=[int]$used.Columns.Count; Formula=$formula; Value=$value}
        $bytes = [Text.Encoding]::UTF8.GetBytes(($obj | ConvertTo-Json -Compress -Depth 30))
        $hash = [Security.Cryptography.SHA256]::Create()
        try { return ([BitConverter]::ToString($hash.ComputeHash($bytes))).Replace('-', '') }
        finally { $hash.Dispose() }
    }
    finally { Release-ComObject $used }
}

function Style-Fingerprint([object]$Sheet) {
    $used=$null; $cells=$null; $hash=$null
    try {
        $used=$Sheet.UsedRange
        $cells=$Sheet.Cells
        $builder=New-Object System.Text.StringBuilder
        for ($r=[int]$used.Row; $r -lt ([int]$used.Row+[int]$used.Rows.Count); $r++) {
            for ($c=[int]$used.Column; $c -lt ([int]$used.Column+[int]$used.Columns.Count); $c++) {
                $cell=$null; $interior=$null; $merge=$null; $borders=$null
                try {
                    $cell=$cells.Item($r,$c); $interior=$cell.Interior
                    [void]$builder.Append("$r,$c|").Append([string]$cell.NumberFormat).Append('|').Append([string]$interior.ColorIndex).Append('|').Append([string]$interior.Color).Append('|')
                    if ([bool]$cell.MergeCells) { $merge=$cell.MergeArea; [void]$builder.Append([string]$merge.Address()) }
                    [void]$builder.Append('|')
                    $borders=$cell.Borders
                    foreach ($edge in @(7,8,9,10)) {
                        $border=$null
                        try { $border=$borders.Item($edge); [void]$builder.Append([string]$border.LineStyle).Append(',').Append([string]$border.Weight).Append(',').Append([string]$border.Color).Append(';') }
                        finally { Release-ComObject $border }
                    }
                    [void]$builder.AppendLine()
                }
                finally { Release-ComObject $borders; Release-ComObject $merge; Release-ComObject $interior; Release-ComObject $cell }
            }
        }
        $hash=[Security.Cryptography.SHA256]::Create()
        return ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($builder.ToString())))).Replace('-', '')
    }
    finally { if ($null -ne $hash) { $hash.Dispose() }; Release-ComObject $cells; Release-ComObject $used }
}

function Workbook-Calculation([string]$Path) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive=[IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $entry=$archive.GetEntry('xl/workbook.xml')
        if ($null -eq $entry) { throw 'Workbook XML missing.' }
        $reader=New-Object IO.StreamReader($entry.Open())
        try { [xml]$xml=$reader.ReadToEnd() } finally { $reader.Dispose() }
        $node=$xml.SelectSingleNode("//*[local-name()='calcPr']")
        $settings=[ordered]@{}
        foreach ($key in @('calcMode','refMode','iterate','iterateCount','iterateDelta','fullCalcOnLoad','forceFullCalc','calcOnSave','concurrentCalc','concurrentManualCount')) {
            $value=if ($null -ne $node -and $node.HasAttribute($key)) { $node.GetAttribute($key) } else { '' }
            if ($key -eq 'calcMode' -and $value -eq '') { $value='auto' }
            $settings[$key]=$value
        }
        return ($settings | ConvertTo-Json -Compress)
    }
    finally { $archive.Dispose() }
}

function Set-TextCell([object]$Sheet, [int]$Row, [int]$Column, [string]$Value) {
    $cell = $null
    try {
        $cell = $Sheet.Cells.Item($Row, $Column)
        $cell.NumberFormat = '@'
        $cell.Value2 = [string]$Value
        $cell.WrapText = $true
    }
    finally { Release-ComObject $cell }
}

function Get-SheetByName([object]$Sheets, [string]$Name) {
    for ($i = 1; $i -le $Sheets.Count; $i++) {
        $candidate = $Sheets.Item($i)
        if ([string]$candidate.Name -ceq $Name) { return $candidate }
        Release-ComObject $candidate
    }
    return $null
}

$source = [IO.Path]::GetFullPath($WorkbookPath)
$metadata = [IO.Path]::GetFullPath($MetadataPath)
$output = [IO.Path]::GetFullPath($OutputPath)
if ([IO.Path]::GetExtension($source).ToLowerInvariant() -ne '.xlsx' -or [IO.Path]::GetExtension($output).ToLowerInvariant() -ne '.xlsx') { throw 'Workbook paths must end in .xlsx.' }
if (-not [IO.File]::Exists($source) -or -not [IO.File]::Exists($metadata)) { throw 'Source workbook or metadata JSON is missing.' }
if ($source.Equals($output, [StringComparison]::OrdinalIgnoreCase)) { throw 'Output must differ from source.' }
if ([IO.File]::Exists($output)) { throw 'Output already exists.' }
$outputParent = [IO.Path]::GetDirectoryName($output)
if (-not [IO.Directory]::Exists($outputParent)) { throw 'Output directory does not exist.' }
$lock = Join-Path $outputParent ('~$' + [IO.Path]::GetFileName($output))
if (Test-Path -LiteralPath $lock) { throw 'Output lock exists.' }

# Exclusive preflight: never open, close, or change an already-open user workbook.
$probe = $null
try { $probe = [IO.File]::Open($source, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None) }
catch { throw 'Source workbook is locked or cannot be read exclusively.' }
finally { if ($null -ne $probe) { $probe.Dispose() } }

$doc = Get-Content -LiteralPath $metadata -Raw -Encoding UTF8 | ConvertFrom-Json
if ($null -eq $doc -or $doc.records -isnot [array] -or $doc.records.Count -eq 0) { throw 'metadata JSON must have a non-empty records array.' }
foreach ($p in $doc.PSObject.Properties) { if ($p.Name -cne 'records') { throw "Unknown metadata field: $($p.Name)" } }
$keys = New-Object 'System.Collections.Generic.HashSet[string]'
$rows = New-Object 'System.Collections.Generic.List[object]'
foreach ($record in $doc.records) {
    if ($record -isnot [System.Management.Automation.PSCustomObject]) { throw 'Each record must be an object.' }
    foreach ($p in $record.PSObject.Properties) {
        if ($p.Name -cnotin @('role','label','evidence_status','source','validation','software','environment','startup_command')) { throw "Unknown record field: $($p.Name)" }
    }
    $role = Assert-Text $record.role 'role'
    if ($role -cnotin @('baseline','tuning')) { throw 'role must be baseline or tuning.' }
    $status = Assert-Text $record.evidence_status 'evidence_status'
    if ($status -cnotin $allowedStatuses) { throw 'evidence_status must be observed or candidate.' }
    $label = Assert-Text $record.label 'label'
    if (-not $keys.Add($role + [char]31 + $label)) { throw 'Duplicate role and label.' }
    $sourceText = Assert-Text $record.source 'source'
    $validationText = Assert-Text $record.validation 'validation'
    [void](Assert-Text $record.startup_command 'startup_command' $true)
    Assert-Map $record.software 'software'
    Assert-Map $record.environment 'environment'
    $rows.Add(@($role, $label, $status, 'source', $sourceText))
    $rows.Add(@($role, $label, $status, 'validation', $validationText))
    foreach ($field in @('software','environment')) {
        if ($null -ne $record.$field) {
            foreach ($property in $record.$field.PSObject.Properties) { $rows.Add(@($role, $label, $status, "$field.$($property.Name)", [string]$property.Value)) }
        }
    }
    if ($null -ne $record.startup_command -and $record.startup_command -ne '') { $rows.Add(@($role, $label, $status, 'startup_command', [string]$record.startup_command)) }
}

Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class RuntimeMetadataExcelPid {
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
'@
$before = @(Get-Process EXCEL -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$stage = Join-Path $outputParent ('.' + [IO.Path]::GetFileNameWithoutExtension($output) + '.' + [Guid]::NewGuid().ToString('N') + '.partial.xlsx')
$sourceCalculation = $null
$excel=$null; $books=$null; $workbook=$null; $sheets=$null; $sheet=$null; $ownedPid=0; $ownedStart=$null; $published=$false; $failure=$null
try {
    # Keep the source exclusively locked for the entire snapshot copy.  A
    # workbook opened after the initial preflight must not be copied in place.
    $inputStream=$null; $outputStream=$null
    try {
        $inputStream=[IO.File]::Open($source,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None)
        $outputStream=[IO.File]::Open($stage,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        $inputStream.CopyTo($outputStream)
        $outputStream.Flush($true)
    }
    finally { if ($null -ne $outputStream) { $outputStream.Dispose() }; if ($null -ne $inputStream) { $inputStream.Dispose() } }
    $sourceCalculation = Workbook-Calculation $stage
    $excel = New-Object -ComObject Excel.Application
    $pidValue = [uint32]0
    [void][RuntimeMetadataExcelPid]::GetWindowThreadProcessId([IntPtr]$excel.Hwnd, [ref]$pidValue)
    if ($pidValue -eq 0 -or $pidValue -in $before) { throw 'Could not establish a private Excel process; no user session was closed.' }
    $ownedPid = [int]$pidValue
    $ownedStart = (Get-Process -Id $ownedPid).StartTime
    $excel.Visible = $false; $excel.DisplayAlerts = $false; $excel.AutomationSecurity = 3
    $books = $excel.Workbooks
    $workbook = $books.Open($stage, 0, $false)
    $sheets = $workbook.Worksheets
    $existing = Get-SheetByName $sheets $metadataSheetName
    if ($null -ne $existing) { Release-ComObject $existing; throw 'Runtime metadata sheet already exists; refusing to replace user content.' }
    $fingerprints = [ordered]@{}
    $styleFingerprints = [ordered]@{}
    for ($i=1; $i -le $sheets.Count; $i++) {
        $s = $sheets.Item($i)
        try { $fingerprints[[string]$s.Name] = Fingerprint $s; $styleFingerprints[[string]$s.Name] = Style-Fingerprint $s }
        finally { Release-ComObject $s }
    }
    $after = $sheets.Item($sheets.Count)
    try { $sheet = $sheets.Add([Type]::Missing, $after) }
    finally { Release-ComObject $after }
    $sheet.Name = $metadataSheetName
    $headers = @('角色','记录','证据状态','字段','值')
    for ($c=1; $c -le $headers.Count; $c++) { Set-TextCell $sheet 1 $c $headers[$c-1] }
    $rowIndex=2
    foreach ($row in $rows) {
        for ($c=1; $c -le 5; $c++) { Set-TextCell $sheet $rowIndex $c ([string]$row[$c-1]) }
        $rowIndex++
    }
    $sheet.Columns.Item(1).ColumnWidth = 14
    $sheet.Columns.Item(2).ColumnWidth = 24
    $sheet.Columns.Item(3).ColumnWidth = 16
    $sheet.Columns.Item(4).ColumnWidth = 34
    $sheet.Columns.Item(5).ColumnWidth = 100
    $workbook.Save()
    $workbook.Close($false)
    Release-ComObject $sheet; $sheet=$null
    Release-ComObject $sheets; $sheets=$null
    Release-ComObject $workbook; $workbook=$null
    $workbook = $books.Open($stage, 0, $true)
    $sheets = $workbook.Worksheets
    if ($sheets.Count -ne ($fingerprints.Count + 1)) { throw 'Worksheet count changed.' }
    foreach ($name in $fingerprints.Keys) {
        $s = Get-SheetByName $sheets $name
        if ($null -eq $s) { throw 'An existing sheet is missing after save.' }
        try {
            if ((Fingerprint $s) -cne $fingerprints[$name]) { throw "An existing sheet changed after save: $name" }
            if ((Style-Fingerprint $s) -cne $styleFingerprints[$name]) { throw "An existing sheet style or merge changed after save: $name" }
        }
        finally { Release-ComObject $s }
    }
    $sheet = Get-SheetByName $sheets $metadataSheetName
    if ($null -eq $sheet) { throw 'Runtime metadata sheet missing after save.' }
    $rowIndex=2
    foreach ($row in $rows) {
        for ($c=1; $c -le 5; $c++) {
            $cell=$sheet.Cells.Item($rowIndex,$c)
            try { if ([string]$cell.Value2 -cne [string]$row[$c-1] -or [bool]$cell.HasFormula) { throw "Metadata readback mismatch at row $rowIndex column $c" } }
            finally { Release-ComObject $cell }
        }
        $rowIndex++
    }
    $workbook.Close($false)
    Release-ComObject $sheet; $sheet=$null
    Release-ComObject $sheets; $sheets=$null
    Release-ComObject $workbook; $workbook=$null
    if ((Workbook-Calculation $stage) -cne $sourceCalculation) { throw 'Workbook calculation settings changed after save.' }
}
catch {
    $failure = $_
}
finally {
    if ($null -ne $workbook) { try { $workbook.Close($false) } catch {} }
    Release-ComObject $sheet; Release-ComObject $sheets; Release-ComObject $workbook; Release-ComObject $books
    if ($null -ne $excel -and $ownedPid -gt 0) { try { $excel.Quit() } catch {} }
    Release-ComObject $excel
    [GC]::Collect(); [GC]::WaitForPendingFinalizers(); [GC]::Collect(); [GC]::WaitForPendingFinalizers()
    if ($ownedPid -gt 0) {
        for ($i=0; $i -lt 60; $i++) { if (-not (Get-Process -Id $ownedPid -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Milliseconds 500 }
        $leftover=Get-Process -Id $ownedPid -ErrorAction SilentlyContinue
        if ($null -ne $leftover -and $null -ne $ownedStart -and $leftover.ProcessName -eq 'EXCEL' -and $leftover.StartTime -eq $ownedStart) {
            Stop-Process -Id $ownedPid -Force -ErrorAction Stop
            Wait-Process -Id $ownedPid -ErrorAction SilentlyContinue
            Write-Output ('CLEANED_OWN_EXCEL_PID=' + $ownedPid)
        }
        elseif ($null -ne $leftover) {
            if ($null -eq $failure) { $failure = "Cannot verify owned Excel process identity: $ownedPid" }
            else { Write-Warning "Cannot verify owned Excel process identity: $ownedPid" }
        }
    }
}
if ($null -ne $failure) {
    if ([IO.File]::Exists($stage)) { try { [IO.File]::Delete($stage) } catch {} }
    throw $failure
}
try {
    [IO.File]::Move($stage, $output)
    $published = $true
    Write-Output ('OUTPUT=' + $output)
    Write-Output ('RECORDS=' + $doc.records.Count)
    Write-Output ('METADATA_ROWS=' + $rows.Count)
    Write-Output ('OUTPUT_SHA256=' + (Get-FileHash -Algorithm SHA256 -LiteralPath $output).Hash)
    Write-Output 'RUNTIME_METADATA_VALIDATION=PASS'
}
finally { if (-not $published -and [IO.File]::Exists($stage)) { [IO.File]::Delete($stage) } }
