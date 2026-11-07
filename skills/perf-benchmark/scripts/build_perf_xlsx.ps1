# build_perf_xlsx.ps1
# Generates a performance benchmark .xlsx from native benchmark CSV files.
# The workbook layout (sheet structure, headers, merged info columns, SLA highlight,
# colors, fonts) is fully built by this script — NO external template is required.
# Uses Excel COM (Microsoft Excel must be installed).
#
# Usage (self-built, no template needed):
#   powershell -ExecutionPolicy Bypass -File build_perf_xlsx.ps1 `
#       -OutputPath <output.xlsx> `
#       -BaseCsv <baseline.csv> `
#       [-TuningCsv <tuning.csv>] `
#       -CardMachine "<H20 4机>" `
#       -ModelName "<Qwen3.8-2.4T-A95B-FP8>" `
#       -SheetBaselineName "<H20 4机+Qwen3.8-2.4T（基线）>" `
#       -SheetTuningName "<...（调优）>"
#
# Optional legacy: -TemplatePath <template.xlsx>. If provided AND exists, the script
# opens that workbook and rebuilds its sheets (preserving its exact headers/page);
# if omitted/missing, the workbook is created from scratch with built-in headers.
#
# Behavior:
#   - If BaseCsv only (baseline mode): output has a single data sheet (baseline).
#   - If BaseCsv + TuningCsv (baseline+tuning mode): output has two data sheets (tuning first, baseline second).
#
# CSV native columns used:
#   scenario_name, input_length, output_length, max_concurrency,
#   request_throughput, output_token_throughput, total_token_throughput,
#   mean_ttft, p90_ttft, mean_tpot, p90_tpot
#
# Output cell mapping (see SKILL.md section "数据对应"):
#   C10=并发, C11=输入长度, C12=输出长度,
#   C13=Mean TTFT (s)=mean_ttft/1000, C14=TTFT P90 (s)=p90_ttft/1000,
#   C15=Mean TPOT (ms)=mean_tpot, C16=TPOT P90 (ms)=p90_tpot,
#   C17=单路输出吞吐=output_token_throughput/并发, C18=总输出吞吐=output_token_throughput,
#   C19=单路 E2E=total_token_throughput/并发, C20=总 E2E=total_token_throughput,
#   C21=QPS=request_throughput
# Tuning-only extra columns: C23=基线总吞吐(tps) = baseline 总E2E at same 并发, C24=提升(%).
#
# SLA highlight: for each scenario, the row with the maximum 并发 such that
#   Mean TPOT(ms) <= SLA_TPOT  AND  Mean TTFT(s) <= SLA_TTFT
# is filled light green (#50D092); if no row meets the SLA, the first row of the
# scenario (the lowest concurrency after sorting) is highlighted.

param(
    [string]$TemplatePath = "",
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [Parameter(Mandatory=$true)][string]$BaseCsv,
    [string]$TuningCsv = "",
    [string]$CardMachine = "",
    [string]$ModelName = "",
    [Parameter(Mandatory=$true)][string]$SheetBaselineName = "",
    [string]$SheetTuningName = "",
    [switch]$SkipTuning = $false
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Get-CsvData {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "CSV not found: $Path"
    }
    # Auto-detect delimiter from the first line (comma / tab / semicolon).
    $allLines = [System.IO.File]::ReadAllLines($Path)
    if ($allLines.Count -eq 0) { throw "CSV is empty: $Path" }
    $firstLine = $allLines[0]
    $delim = ','
    if ($firstLine.Contains("`t")) { $delim = "`t" }
    elseif ($firstLine.Contains(';')) { $delim = ';' }

    # Auto-detect encoding: strict UTF-8 (rejects invalid bytes); fall back to the ANSI
    # code page (GBK on zh-CN) when bytes are not valid UTF-8. GBK CSVs have no BOM, and
    # PS 5.1 Import-Csv -Encoding accepts only enum values (UTF8 / Default / ...), not an
    # Encoding object, so we map to the string enum.
    $encUtf8 = New-Object System.Text.UTF8Encoding($false, $true)  # throwOnInvalidBytes
    $encodingEnum = 'Default'
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        [void]$encUtf8.GetString($bytes)
        $encodingEnum = 'UTF8'
    } catch {
        $encodingEnum = 'Default'
    }

    $data = $null
    try {
        $data = Import-Csv -LiteralPath $Path -Encoding $encodingEnum -Delimiter $delim
    } catch {
        $data = Import-Csv -LiteralPath $Path -Delimiter $delim
    }
    if ($null -eq $data -or $data.Count -eq 0) { throw "CSV is empty: $Path" }
    return $data
}

# ---- Scenario mapping (native CSV scenario_name -> canonical name, label, SLA) ----
# `Names` lists every CSV scenario_name that belongs to this block; the first entry is the
# canonical name used to key the block (so baseline/tuning aliases like 复杂任务/通用复杂任务
# share the same C23/C24 comparison). Label/SLA text follows the template; scenarios without
# a predefined SLA get TPOT_SLA=0/TTFT_SLA=0 (no row meets SLA -> lowest concurrency highlighted).
$scenarioCfg = @(
    @{ Names=@("对话","中短对话");                Label="对话(2K/2K) - 中短对话";                                 TPOT_SLA=60;  TTFT_SLA=8  },
    @{ Names=@("通用复杂任务","复杂任务");         Label="通用复杂任务(8K/1K) - 较长输入";                         TPOT_SLA=60;  TTFT_SLA=12 },
    @{ Names=@("合同分析");                       Label="合同分析(16K/4K)  - 长输入，中等输出";                   TPOT_SLA=60;  TTFT_SLA=15 },
    @{ Names=@("Agent应用");                      Label="AI Coding/Agent（64K/1K）- 长输入，90% Prefix Cache命中率"; TPOT_SLA=120; TTFT_SLA=30 },
    @{ Names=@("AI Coding");                      Label="AI Coding/Agent (128K/1K)  - 超长输入，90% Prefix Cache命中率"; TPOT_SLA=120; TTFT_SLA=30 },
    @{ Names=@("特长下行文");                     Label="特长下行文";                                            TPOT_SLA=0;   TTFT_SLA=0  },
    @{ Names=@("特长上下文");                     Label="特长上下文（1M/1K）99% Prefix Cache命中率";                 TPOT_SLA=0;   TTFT_SLA=0  }
)

# SLA text shown in column C8 (matches template)
function Get-SlaText {
    param([string]$CsvName)
    switch ($CsvName) {
        "对话"         { return "TPOT≈50~60ms`nTTFT ≈5~8秒" }
        "通用复杂任务" { return "TPOT≈50~60ms`nTTFT ≈8~12秒" }
        "合同分析"     { return "TPOT≈50~60ms`nTTFT ≈12~15秒" }
        "Agent应用"    { return "TPOT≈60~120ms`nTTFT ≈20~30秒" }
        "AI Coding"    { return "TPOT≈60~120ms`nTTFT ≈20~30秒" }
        "特长下行文"   { return "TPOT≈60~120ms`nTTFT ≈20~30秒" }
        default        { return "" }
    }
}

# Acceleration feature text in C9
function Get-AccelText {
    param([bool]$IsTuning)
    if ($IsTuning) { return "KV稀疏,`n投机推理" }
    return "无"
}

# Process one CSV into an ordered list of scenario blocks.
# Returns array of @{ CsvName; Label; SlaText; Rows = @( @{conc; inlen; outlen; values...} ) }
# CsvName is the CANONICAL name (first Names entry) reused for baseline/tuning C23/C24 keying.
function Build-Blocks {
    param($CsvData)
    $blocks = @()
    foreach ($cfg in $scenarioCfg) {
        $canonical = $cfg.Names[0]
        $rows = @($CsvData | Where-Object { ($cfg.Names -contains $_.scenario_name) })
        if ($rows.Count -eq 0) { continue }
        $ordered = @($rows | Sort-Object { [double]$_.max_concurrency })
        $blk = @{
            CsvName = $canonical
            Label   = $cfg.Label
            SlaText = (Get-SlaText $canonical)
            TPOT    = [double]$cfg.TPOT_SLA
            TTFT    = [double]$cfg.TTFT_SLA
            Rows    = $ordered
        }
        $blocks += $blk
    }
    return $blocks
}

# Transform a csv row into the 11 display values (并发, 输入, 输出, ttft-m, ttft-p90-s, ...)
function Get-OutRow {
    param($r)
    $conc     = [double]$r.max_concurrency
    $outTh    = [double]$r.output_token_throughput
    $totTh    = [double]$r.total_token_throughput
    $singleOut = if ($conc -ne 0) { $outTh / $conc } else { 0 }
    $singleE2e = if ($conc -ne 0) { $totTh / $conc } else { 0 }
    # NOTE: compute divisions into variables BEFORE the array literal, because inline
    # '/' division expressions inside an @(...) literal throw 'op_Division' on Object[].
    $ttftMean = [double]$r.mean_ttft / 1000.0   # C13 Mean TTFT (s)
    $ttftP90  = [double]$r.p90_ttft  / 1000.0   # C14 TTFT P90 (s)
    return @(
        [double]$conc,                   # C10 并发
        [double]$r.input_length,         # C11 输入长度
        [double]$r.output_length,        # C12 输出长度
        $ttftMean,                       # C13 Mean TTFT (s)
        $ttftP90,                        # C14 TTFT P90 (s)
        [double]$r.mean_tpot,            # C15 Mean TPOT (ms)
        [double]$r.p90_tpot,             # C16 TPOT P90 (ms)
        [double]$singleOut,              # C17 单路输出吞吐
        [double]$outTh,                  # C18 总输出吞吐
        [double]$singleE2e,              # C19 单路 E2E 吞吐
        [double]$totTh,                  # C20 总 E2E 吞吐
        [double]$r.request_throughput    # C21 QPS
    )
}

# Determine SLA row index (within block.Rows) to highlight.
#   - If at least one row meets the SLA, pick the LAST meeting row (the HIGHEST concurrency
#     that still passes SLA) -- preserves the original "push to max concurrency" intent.
#   - If NO row meets the SLA (all concurrency levels exceed the SLA), pick the FIRST row
#     (the LOWEST concurrency) so the smallest concurrency is highlighted.
function Get-SlaRowIndex {
    param($block)
    $best = -1
    for ($i = 0; $i -lt $block.Rows.Count; $i++) {
        $r = $block.Rows[$i]
        $tpot = [double]$r.mean_tpot
        $ttft = [double]$r.mean_ttft / 1000.0
        if ($tpot -le $block.TPOT -and $ttft -le $block.TTFT) {
            $best = $i
        }
    }
    if ($best -lt 0) { $best = 0 }
    return $best
}

# Column letters for 1-based column indexes up to X (24). Index 0 is unused.
$script:ColB = @('','A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z')

# Reliable cell accessor: returns a one-cell Range via an address string.
# NOTE: PowerShell 5.1 can mis-bind `Cells.Item($row, <variable-column>)` to the COM
# indexer and throw (cast Double->String / 0x800A03EC) when the column index is a
# variable/expression. Using Range("J5") with a computed address is always reliable.
function Cell {
    param($ws, [int]$row, [int]$col)
    if ($row -lt 1 -or $col -lt 1 -or $col -gt 26) { throw "Cell out of range: row=$row col=$col" }
    return $ws.Range($script:ColB[$col] + $row)
}

# Rebuild the data region of one worksheet from scenario blocks.
function Rebuild-OneSheet {
    param(
        [Parameter(Mandatory=$true)]$ws,
        [Parameter(Mandatory=$true)]$blocks,
        [bool]$IsTuning = $false,
        $baseMap = $null
    )

    $GREEN_SLA = 0x50D092   # (used by Merge-BlockColumns; kept for reference)

    $FONT_DATA = "微软雅黑"
    $FONT_INFO = "等线"
    $FONT_QPS = "等线"

    # Compute needed data rows
    $totalRows = 0
    foreach ($blk in $blocks) { $totalRows += $blk.Rows.Count }

    # Header occupies row 1. Data region starts at row 2.
    $startRow = 2
    $lastWanted = $startRow + $totalRows - 1

    # Determine current extent of data region (rows with content).
    $curLast = $startRow
    for ($r = $startRow; $r -le 5000; $r++) {
        $v = $ws.Cells.Item($r, 10).Value2
        if ($null -ne $v -and [string]$v -ne "") { $curLast = $r } else { break }
    }

    # ---- 1. Unmerge everything in the data region ----
    $areaLastCol = if ($IsTuning) { 24 } else { 22 }
    $areaRows = [Math]::Max($curLast, $lastWanted) + 1
    $area = $ws.Range($ws.Cells.Item($startRow,1), $ws.Cells.Item($areaRows, $areaLastCol))
    if ([bool]$area.MergeCells) {
        # unmerge all individual merged ranges safely from top to bottom
        for ($r = $startRow; $r -le $areaRows; $r++) {
            for ($c = 1; $c -le $areaLastCol; $c++) {
                $cell = Cell $ws $r $c
                if ([bool]$cell.MergeCells) {
                    $ma = $cell.MergeArea
                    if ($ma.Rows.Count -gt 1 -or $ma.Columns.Count -gt 1) {
                        $ma.UnMerge()
                    }
                }
            }
        }
    }

    # ---- 2. Adjust row count ----
    if ($curLast -lt $lastWanted) {
        # need more rows: copy the format of the last existing data row downward
        $fmtSrc = $ws.Rows.Item($curLast)
        for ($r = $curLast + 1; $r -le $lastWanted; $r++) {
            $fmtSrc.Copy() | Out-Null
            $ws.Rows.Item($r).Insert(-4121) | Out-Null  # xlShiftDown
        }
    } elseif ($curLast -gt $lastWanted) {
        # delete surplus rows (copies formats up)
        $excess = $curLast - $lastWanted
        $ws.Rows.Item(($lastWanted + 1).ToString() + ":" + $curLast.ToString()).Delete(-4162) | Out-Null
    }

    # ---- 3. Write data values and apply per-column formatting ----
    # fixed fonts / alignments per column for a normal data row
    $dataFontCols = 7..22   # baseline data cols (C7..C22)
    if ($IsTuning) { $dataFontCols += 23; $dataFontCols += 24 }  # C23,C24
    $infoFontCols = 1..6

    $r = $startRow
    foreach ($blk in $blocks) {
        for ($i = 0; $i -lt $blk.Rows.Count; $i++) {
            $src = $blk.Rows[$i]
            $vals = Get-OutRow -r $src

            # C7 场景 (only first row of block), C8 SLA, C9 accel (only first row of block)
            if ($i -eq 0) {
                (Cell $ws $r 7).Value2 = [string]$blk.Label
                (Cell $ws $r 8).Value2 = [string]$blk.SlaText
                (Cell $ws $r 9).Value2 = [string](Get-AccelText $IsTuning)
            } else {
                (Cell $ws $r 7).Value2 = ""
                (Cell $ws $r 8).Value2 = ""
                (Cell $ws $r 9).Value2 = ""
            }

            # C10..C21  (NOTE: must pass an inline-typed [double] expression to the COM
            # .Value2 setter; assigning a runtime variable throws 'cast Double to String'.)
            for ($k = 0; $k -lt 12; $k++) {
                (Cell $ws $r (10 + $k)).Value2 = [double]$vals[$k]
            }
            # C22 备注
            (Cell $ws $r 22).Value2 = ""

            if ($IsTuning) {
                # C23 baseline total E2E at same concurrency; C24 improvement %
                $key = $blk.CsvName + "|" + [double]$src.max_concurrency
                $baselineE2e = $null
                if ($null -ne $baseMap -and $baseMap.ContainsKey($key)) { $baselineE2e = $baseMap[$key] }
                if ($null -ne $baselineE2e) {
                    (Cell $ws $r 23).Value2 = [double]$baselineE2e
                    $myE2e = [double]$src.total_token_throughput
                    if ([double]$baselineE2e -ne 0) {
                        $pct = (($myE2e - [double]$baselineE2e) / [double]$baselineE2e) * 100.0
                        (Cell $ws $r 24).Value2 = [string]("{0:F2}%" -f $pct)
                    } else {
                        (Cell $ws $r 24).Value2 = ""
                    }
                } else {
                    (Cell $ws $r 23).Value2 = ""
                    (Cell $ws $r 24).Value2 = ""
                }
            }

            # per-column fonts (data cols: Microsoft YaHei 10, centered; C21 QPS special)
            foreach ($c in $infoFontCols) {
                $cell = Cell $ws $r $c
                $cell.Font.Name = $FONT_INFO
                $cell.Font.Size = 11
                $cell.Font.Bold = $false
                $cell.HorizontalAlignment = -4131
                $cell.VerticalAlignment = -4160
                $cell.WrapText = $true
            }
            foreach ($c in $dataFontCols) {
                $cell = Cell $ws $r $c
                if ($c -eq 21) {
                    $cell.Font.Name = $FONT_QPS
                    $cell.Font.Size = 12
                    $cell.Font.Bold = $false
                    $cell.HorizontalAlignment = 1
                    $cell.VerticalAlignment = -4108
                    $cell.WrapText = $false
                } else {
                    $cell.Font.Name = $FONT_DATA
                    $cell.Font.Size = 10
                    $cell.Font.Bold = $false
                    $cell.HorizontalAlignment = -4108
                    $cell.VerticalAlignment = -4108
                    $cell.WrapText = $true
                }
            }

            # enforce row height
            $ws.Rows.Item($r).RowHeight = 15.75

            $r++
        }
    }

    # ---- 4. Re-merge columns and apply SLA fills ----
    Merge-BlockColumns -ws $ws -blocks $blocks -startRow $startRow -lastWanted $lastWanted -IsTuning $IsTuning
}

function Merge-BlockColumns {
    param($ws, $blocks, $startRow, $lastWanted, [bool]$IsTuning)
    $GREEN_SLA = 0x50D092
    $GREEN_INFO = 0x24C734
    $WHITE = 0xFFFFFF

    $lastC = if ($IsTuning) { 24 } else { 22 }

    # info columns A..F merged over whole data region
    $infoEnd = $lastWanted
    for ($c = 1; $c -le 6; $c++) {
        $ws.Range((Cell $ws $startRow $c), (Cell $ws $infoEnd $c)).Merge() | Out-Null
    }
    # place the info-block label text on the top-left of each merged info column.
    # Values come only from user-provided info captured by Capture-InfoText (empty if not given).
    $ws.Cells.Item($startRow, 1).Value2 = [string]$script:InfoA_Text
    $ws.Cells.Item($startRow, 2).Value2 = [string]$script:InfoB_Text
    $ws.Cells.Item($startRow, 3).Value2 = [string]$script:InfoC_Text
    $ws.Cells.Item($startRow, 4).Value2 = [string]$script:InfoD_Text
    $ws.Cells.Item($startRow, 5).Value2 = [string]$script:InfoE_Text
    $ws.Cells.Item($startRow, 6).Value2 = [string]$script:InfoF_Text

    # scenario columns G,H,I merged per block
    $r = $startRow
    foreach ($blk in $blocks) {
        $end = $r + $blk.Rows.Count - 1
        for ($c = 7; $c -le 9; $c++) {
            $ws.Range((Cell $ws $r $c), (Cell $ws $end $c)).Merge() | Out-Null
        }
        # update model name text in row 1 similarly if desired - handled elsewhere
        $r = $end + 1
    }

    # ---- apply fills (SLA rows green, others white) ----
    $r = $startRow
    foreach ($blk in $blocks) {
        $slaIdx = Get-SlaRowIndex -block $blk
        for ($i = 0; $i -lt $blk.Rows.Count; $i++) {
            $isSla = ($i -eq $slaIdx)
            for ($c = 1; $c -le $lastC; $c++) {
                $cell = Cell $ws $r $c
                if ($isSla) {
                    if ($c -le 6)      { $cell.Interior.Color = $GREEN_INFO }
                    elseif ($c -eq 7 -or $c -eq 8 -or $c -eq 9 -or $c -eq 21) { $cell.Interior.Color = $WHITE }
                    else               { $cell.Interior.Color = $GREEN_SLA }
                } else {
                    $cell.Interior.Color = $WHITE
                }
            }
            $r++
        }
    }

    # ---- apply thin black borders over the whole table (header row 1 .. last data row) ----
    # Matches the template: every visible cell in A1:{col}{lastWanted} carries a thin(2) black
    # continuous(1) border on all edges (i.e. full grid lines), not only the outer box.
    $tblRange = $ws.Range((Cell $ws 1 1), (Cell $ws $lastWanted $lastC))
    $tblRange.Borders.LineStyle = 1
    $tblRange.Borders.Weight    = 2
    $tblRange.Borders.Color     = 0
}

# Ensure a worksheet name is <= 31 chars and free of forbidden chars (Excel limit).
function Safe-SheetName {
    param([string]$Name)
    $name = $Name -replace '[:\\/?*\[\]]', ''
    if ($name.Length -gt 31) {
        # truncate in the middle, keeping the tail that holds (基线)/(调优)
        $tailLen = 8
        $headLen = 31 - $tailLen - 3
        $name = $name.Substring(0, $headLen) + "..." + $name.Substring($name.Length - $tailLen)
    }
    return $name
}

# ---------- main ----------
$hasTuning = (-not [string]::IsNullOrWhiteSpace($TuningCsv)) -and (Test-Path -LiteralPath $TuningCsv)
if ([string]::IsNullOrWhiteSpace($SheetBaselineName)) { throw "SheetBaselineName is required" }
if ($hasTuning -and [string]::IsNullOrWhiteSpace($SheetTuningName)) { throw "SheetTuningName is required when TuningCsv is used" }

$baseRaw = Get-CsvData $BaseCsv
$baseBlocks = Build-Blocks $baseRaw
$tuningBlocks = $null
if ($hasTuning) {
    $tunRaw = Get-CsvData $TuningCsv
    $tuningBlocks = Build-Blocks $tunRaw
}

# Baseline blocks: dict scenario -> { conc: C20 } for C23 mapping
$baseByScenario = @{}
foreach ($blk in $baseBlocks) { $baseByScenario[$blk.CsvName] = $blk }
$baseConcToE2e = @{}
foreach ($blk in $baseBlocks) {
    foreach ($rowEnt in $blk.Rows) {
        $baseConcToE2e[$blk.CsvName + "|" + [double]$rowEnt.max_concurrency] = [double]$rowEnt.total_token_throughput
    }
}

# Determine the model-config metadata text (columns A..F). Info values are taken ONLY
# from user-provided params; any column the user did NOT provide is left EMPTY so that
# nothing is pre-filled from a template.
#   A = ModelName (if provided)
#   C = CardMachine (if provided)
#   B, D, E, F = always empty (no user input available)
function Capture-InfoText {
    param([string]$CardMachine, [string]$ModelName)
    $script:InfoA_Text = if (-not [string]::IsNullOrWhiteSpace($ModelName))   { $ModelName }   else { "" }
    $script:InfoB_Text = ""
    $script:InfoC_Text = if (-not [string]::IsNullOrWhiteSpace($CardMachine)) { $CardMachine } else { "" }
    $script:InfoD_Text = ""
    $script:InfoE_Text = ""
    $script:InfoF_Text = ""
}

# Built-in header labels (row 1) mirroring the template workbook exactly.
#   A1..F1 = info column headers; G1..I1 = scenario/SLA/accel block headers;
#   J1..V1 = numeric data headers; W1/X1 = tuning extras.
$HDR_1 = "模型"
$HDR_2 = "模型参数&`n量化"
$HDR_3 = "机型+卡数&`n互联"
$HDR_4 = "硬件环境"
$HDR_5 = "软件环境&`n推理引擎"
$HDR_6 = "并行策略"
$HDR_7  = "场景"
$HDR_8  = "SLA"
$HDR_10 = "并发"
$HDR_11 = "输入长度"
$HDR_12 = "输出长度"
$HDR_13 = "Mean TTFT (s)"
$HDR_14 = "TTFT P90 (s)"
$HDR_15 = "Mean TPOT (ms)"
$HDR_16 = "TPOT P90"
$HDR_17 = "单路输出吞吐 (tps)"
$HDR_18 = "总输出吞吐 (tps)"
$HDR_19 = "单路 E2E 吞吐 (tps)"
$HDR_20 = "总 E2E 吞吐 (tps)"
$HDR_21 = "QPS"
$HDR_22 = "备注"
$HDR_23 = "基线总吞吐 (tps)"
$HDR_24 = "提升 (%)"

# C9 accel header label differs between baseline and tuning (matches template).
$HDR_9_BASE  = "开源加速特性"
$HDR_9_TUNE  = "Wings-infer 加速特性"

# Write the standard header row (row 1) and column widths for a self-built sheet.
function Build-SheetHeader {
    param($ws, [bool]$IsTuning)
    $r = 1
    (Cell $ws $r 1).Value2  = [string]$HDR_1
    (Cell $ws $r 2).Value2  = [string]$HDR_2
    (Cell $ws $r 3).Value2  = [string]$HDR_3
    (Cell $ws $r 4).Value2  = [string]$HDR_4
    (Cell $ws $r 5).Value2  = [string]$HDR_5
    (Cell $ws $r 6).Value2  = [string]$HDR_6
    (Cell $ws $r 7).Value2  = [string]$HDR_7
    (Cell $ws $r 8).Value2  = [string]$HDR_8
    if ($IsTuning) { (Cell $ws $r 9).Value2 = [string]$HDR_9_TUNE }
    else           { (Cell $ws $r 9).Value2 = [string]$HDR_9_BASE }
    (Cell $ws $r 10).Value2 = [string]$HDR_10
    (Cell $ws $r 11).Value2 = [string]$HDR_11
    (Cell $ws $r 12).Value2 = [string]$HDR_12
    (Cell $ws $r 13).Value2 = [string]$HDR_13
    (Cell $ws $r 14).Value2 = [string]$HDR_14
    (Cell $ws $r 15).Value2 = [string]$HDR_15
    (Cell $ws $r 16).Value2 = [string]$HDR_16
    (Cell $ws $r 17).Value2 = [string]$HDR_17
    (Cell $ws $r 18).Value2 = [string]$HDR_18
    (Cell $ws $r 19).Value2 = [string]$HDR_19
    (Cell $ws $r 20).Value2 = [string]$HDR_20
    (Cell $ws $r 21).Value2 = [string]$HDR_21
    (Cell $ws $r 22).Value2 = [string]$HDR_22
    if ($IsTuning) {
        (Cell $ws $r 23).Value2 = [string]$HDR_23
        (Cell $ws $r 24).Value2 = [string]$HDR_24
    }
    # header styling (only up to tuning columns; baseline stops at V=22, tuning at X=24)
    $hdrLastCol = if ($IsTuning) { 24 } else { 22 }
    for ($c = 1; $c -le $hdrLastCol; $c++) {
        $cell = Cell $ws $r $c
        $cell.Font.Name = "微软雅黑"
        $cell.Font.Size = 10
        $cell.Font.Bold = $true
        $cell.HorizontalAlignment = -4108
        $cell.VerticalAlignment = -4108
        $cell.WrapText = $true
        $cell.Interior.Color = 0xD9E1F2
    }
    $ws.Rows.Item($r).RowHeight = 32
    # column widths (rough but readable defaults); tuning-only cols skipped for baseline
    $widths = @{1=12;2=14;3=20;4=12;5=20;6=12;7=34;8=22;9=18;10=10;11=12;12=12;13=14;14=14;15=14;16=14;17=16;18=14;19=16;20=14;21=10;22=10}
    if ($IsTuning) { $widths[23] = 16; $widths[24] = 12 }
    foreach ($k in $widths.Keys) {
        if (-not $IsTuning -and ($k -eq 23 -or $k -eq 24)) { continue }
        try { $ws.Columns.Item($k).ColumnWidth = [double]$widths[$k] } catch { }
    }
}

# Build a self-created "说明" (README) worksheet with a short description.
function Build-ReadmeSheet {
    param($wb, [string]$BaselineName, [string]$TuningName, [bool]$HasTuning)
    $sheet = $wb.Worksheets.Item(1)
    $sheet.Name = "说明"
    $lines = @(
        "性能 Benchmark 汇总报告",
        "",
        "本工作簿由 perf-benchmark skill 依据原生 benchmark CSV 自动生成。",
        "",
        "工作表：",
        ("  - " + $BaselineName + " ：基线性能数据")
    )
    if ($HasTuning) { $lines += ("  - " + $TuningName + " ：调优（加速特性）性能数据，C23/C24 为相对基线的提升") }
    $lines += @(
        "",
        "数据列说明：",
        "  C10 并发 | C11 输入长度 | C12 输出长度 | C13 TTFT均值(s) | C14 TTFT P90(s)",
        "  C15 TPOT均值(ms) | C16 TPOT P90(ms) | C17 单路输出吞吐(tps) | C18 总输出吞吐(tps)",
        "  C19 单路E2E吞吐(tps) | C20 总E2E吞吐(tps) | C21 QPS | C22 备注",
        "",
        "SLA 高亮：每个场景中满足 SLA 的最大并发行以浅绿标注；无满足行则标注该场景第一行（最低并发）。"
    )
    $row = 1
    foreach ($txt in $lines) {
        $cell = $sheet.Cells.Item($row, 1)
        $cell.Value2 = [string]$txt
        $cell.Font.Name = "微软雅黑"
        if ($row -eq 1) { $cell.Font.Size = 14; $cell.Font.Bold = $true } else { $cell.Font.Size = 11 }
        $row++
    }
    try { $sheet.Columns.Item(1).ColumnWidth = 110 } catch { }
}

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
try {
    Capture-InfoText -CardMachine $CardMachine -ModelName $ModelName
    $newPath = $OutputPath

    $templateAvailable = (-not [string]::IsNullOrWhiteSpace($TemplatePath)) -and (Test-Path -LiteralPath $TemplatePath)
    if ($templateAvailable) {
        # ---- template mode: open the template and rebuild its sheets (preserve exact layout) ----
        $wb = $excel.Workbooks.Open($TemplatePath)
        $sheetB = $wb.Worksheets.Item("910C单机+DSV4-Flash-0731-w8a8(基线)")
        $sheetB.Name = (Safe-SheetName $SheetBaselineName)
        Rebuild-OneSheet -ws $sheetB -blocks $baseBlocks -isTuning $false

        if ($hasTuning -and -not $SkipTuning) {
            $sheetT = $wb.Worksheets.Item("910C单机+DSV4-Flash-0731-w8a8(调优)")
            $sheetT.Name = (Safe-SheetName $SheetTuningName)
            Rebuild-OneSheet -ws $sheetT -blocks $tuningBlocks -isTuning $true -baseMap $baseConcToE2e
            $beforeArg = [System.Reflection.Missing]::Value
            $afterArg  = $wb.Worksheets.Item((Safe-SheetName $SheetTuningName))
            $wb.Worksheets.Item((Safe-SheetName $SheetBaselineName)).Move($beforeArg, $afterArg) | Out-Null
        } else {
            $wb.Worksheets.Item("说明").Activate() | Out-Null
            $wb.Worksheets.Item("910C单机+DSV4-Flash-0731-w8a8(调优)").Delete() | Out-Null
        }
    } else {
        # ---- self-built mode: no template, create the workbook from scratch ----
        $wb = $excel.Workbooks.Add()
        # sheet 1 becomes 说明
        Build-ReadmeSheet -wb $wb -BaselineName $SheetBaselineName -TuningName $SheetTuningName -HasTuning ($hasTuning -and -not $SkipTuning)

        $sheetB = $wb.Worksheets.Add([System.Reflection.Missing]::Value, $wb.Worksheets.Item($wb.Worksheets.Count))
        $sheetB.Name = (Safe-SheetName $SheetBaselineName)
        Build-SheetHeader -ws $sheetB -IsTuning $false
        Rebuild-OneSheet -ws $sheetB -blocks $baseBlocks -isTuning $false

        if ($hasTuning -and -not $SkipTuning) {
            $sheetT = $wb.Worksheets.Add([System.Reflection.Missing]::Value, $wb.Worksheets.Item($wb.Worksheets.Count))
            $sheetT.Name = (Safe-SheetName $SheetTuningName)
            Build-SheetHeader -ws $sheetT -IsTuning $true
            Rebuild-OneSheet -ws $sheetT -blocks $tuningBlocks -isTuning $true -baseMap $baseConcToE2e
            # order: 说明, tuning, baseline  → move baseline AFTER tuning
            $beforeArg = [System.Reflection.Missing]::Value
            $afterArg  = $wb.Worksheets.Item((Safe-SheetName $SheetTuningName))
            $wb.Worksheets.Item((Safe-SheetName $SheetBaselineName)).Move($beforeArg, $afterArg) | Out-Null
        }
    }

    # Save as new file (xlsx format 51)
    $wb.SaveAs($newPath, 51)
    $wb.Close($false)
    Write-Output "OK: $newPath"
} finally {
    $excel.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
    # Release RCWs promptly so the EXCEL.EXE helper process can terminate
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
    [GC]::Collect()
}
