# Requires Windows PowerShell 5.1 and Microsoft Excel; edits an independent copy only.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$WorkbookPath,
  [Parameter(Mandatory=$true)][string]$PresentationPath,
  [Parameter(Mandatory=$true)][string]$OutputPath
)
$ErrorActionPreference='Stop'
$inputFile=[IO.Path]::GetFullPath($WorkbookPath)
$jsonFile=[IO.Path]::GetFullPath($PresentationPath)
$outputFile=[IO.Path]::GetFullPath($OutputPath)
if($inputFile.Equals($outputFile,[StringComparison]::OrdinalIgnoreCase)){throw 'Input and output paths must be distinct.'}
if(-not (Test-Path -LiteralPath $inputFile -PathType Leaf)){throw 'Input workbook not found.'}
if(-not (Test-Path -LiteralPath $jsonFile -PathType Leaf)){throw 'Presentation JSON not found.'}
if([IO.Path]::GetExtension($inputFile).ToLowerInvariant() -ne '.xlsx' -or [IO.Path]::GetExtension($outputFile).ToLowerInvariant() -ne '.xlsx'){throw 'Input and output must be .xlsx files.'}
if(Test-Path -LiteralPath $outputFile){throw 'Output already exists; refusing overwrite.'}
$outputDir=[IO.Path]::GetDirectoryName($outputFile)
if(-not (Test-Path -LiteralPath $outputDir -PathType Container)){throw 'Output directory does not exist.'}
foreach($path in @($inputFile,$outputFile)){
 $lock=Join-Path ([IO.Path]::GetDirectoryName($path)) ('~$'+[IO.Path]::GetFileName($path))
 if(Test-Path -LiteralPath $lock){throw "Workbook lock present: $lock"}
}
try{$probe=[IO.File]::Open($inputFile,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None);$probe.Dispose()}catch{throw 'Input workbook is locked or open.'}
function Get-Sha256([string]$path){
 $stream=[IO.File]::Open($path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 $sha=[Security.Cryptography.SHA256]::Create()
 try{return ([BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','').ToLowerInvariant())}finally{$sha.Dispose();$stream.Dispose()}
}
$sourceHash=Get-Sha256 $inputFile
$jsonHash=Get-Sha256 $jsonFile
$config=Get-Content -LiteralPath $jsonFile -Encoding UTF8 -Raw | ConvertFrom-Json
function Has($o,[string]$name){return ($null -ne $o.PSObject.Properties[$name])}
function Check-Keys($o,[string[]]$allowed,[string]$label){
 if($null -eq $o -or $o -is [string] -or $o -is [array] -or $o -isnot [pscustomobject]){throw "$label must be an object."}
 foreach($prop in $o.PSObject.Properties){if($prop.Name -notin $allowed){throw "Unexpected $label property: $($prop.Name)"}}
}
function Text($o,[string]$key,[string]$label){
 $v=$o.$key
 if($null -eq $v -or $v -isnot [string] -or $v.Length -gt 32767){throw "$label must be text of at most 32767 characters."}
 if($v -match '-----BEGIN [A-Z ]*PRIVATE KEY-----'){throw "Sensitive credential pattern in $label."}
 $placeholder='^(?:<(?:(?:YOUR_)?(?:HF_|API_|ACCESS_)?(?:TOKEN|KEY|SECRET|PASSWORD)|REDACTED|MASKED|PLACEHOLDER|REPLACE_ME)>|\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*|\$env:[A-Za-z_][A-Za-z0-9_]*|\*{3,}|\[REDACTED\]|REDACTED|MASKED|)$'
 $assignPattern='(?i)\b(?:[A-Za-z_][A-Za-z0-9_]*_(?:TOKEN|PASSWORD|PASSWD|API_KEY|SECRET)|TOKEN|PASSWORD|PASSWD|API_KEY|SECRET)\s*[:=]\s*("[^"\r\n]*"|''[^''\r\n]*''|[^\s;]+)'
 $flagPattern='(?i)--(?:[A-Za-z0-9_-]*token|api[-_]?key|password|passwd|secret)(?:=|\s+)("[^"\r\n]*"|''[^''\r\n]*''|[^\s;]+)'
 $bearerPattern='(?i)\bauthorization\s*:\s*bearer\s+("[^"\r\n]*"|''[^''\r\n]*''|[^\s;]+)'
 foreach($pattern in @($assignPattern,$flagPattern,$bearerPattern)){
  foreach($match in [regex]::Matches($v,$pattern)){
   $candidate=$match.Groups[1].Value.Trim();if($candidate.Length -ge 2 -and (($candidate[0] -eq '"' -and $candidate[$candidate.Length-1] -eq '"') -or ($candidate[0] -eq "'" -and $candidate[$candidate.Length-1] -eq "'"))){$candidate=$candidate.Substring(1,$candidate.Length-2)}
   if($candidate -notmatch $placeholder){throw "Sensitive credential pattern in $label."}
  }
 }
 return $v
}
function Limit($v,[string]$label){
 if($v -is [string] -or $v -is [bool] -or $null -eq $v){throw "$label must be a positive number."}
 try{$d=[double]$v}catch{throw "$label must be a positive number."}
 if([double]::IsNaN($d) -or [double]::IsInfinity($d) -or $d -le 0){throw "$label must be a positive finite number."}
 return $d
}
Check-Keys $config @('sheets') 'root'
if(-not (Has $config 'sheets') -or $config.sheets -isnot [array] -or $config.sheets.Count -eq 0){throw 'sheets must be a nonempty array.'}
$sheetSeen=@{}
foreach($spec in $config.sheets){
 Check-Keys $spec @('sheet','hardware_text','software_text','parallelism_text','software_column_width','data_row_height','scenarios') 'sheet'
 if(-not (Has $spec 'sheet')){throw 'sheet name required.'};$name=Text $spec 'sheet' 'sheet'
 if([string]::IsNullOrWhiteSpace($name) -or $sheetSeen.ContainsKey($name)){throw 'Sheet names must be nonempty and unique.'};$sheetSeen[$name]=$true
 foreach($key in @('hardware_text','software_text','parallelism_text')){if(Has $spec $key){[void](Text $spec $key "$name.$key")}}
 if(Has $spec 'software_column_width'){$v=Limit $spec.software_column_width "$name.software_column_width";if($v -gt 255){throw 'software_column_width exceeds Excel limit 255.'}}
 if(Has $spec 'data_row_height'){$v=Limit $spec.data_row_height "$name.data_row_height";if($v -gt 409){throw 'data_row_height exceeds Excel limit 409.'}}
 if(Has $spec 'scenarios'){
  if($spec.scenarios -isnot [array]){throw "$name.scenarios must be an array."};$scenarioSeen=@{}
  foreach($scenario in $spec.scenarios){
   Check-Keys $scenario @('name','display_name','sla_text','feature_text','tpot_limit_ms','ttft_limit_s','eligible_concurrency','sla_limits_unchanged') 'scenario'
   if(-not (Has $scenario 'name')){throw 'Scenario name required.'};$scenarioName=Text $scenario 'name' 'scenario.name'
   if([string]::IsNullOrWhiteSpace($scenarioName) -or $scenarioSeen.ContainsKey($scenarioName)){throw "Scenario names in $name must be nonempty and unique."};$scenarioSeen[$scenarioName]=$true
   foreach($key in @('display_name','sla_text','feature_text')){if(Has $scenario $key){[void](Text $scenario $key "$scenarioName.$key")}}
   $hasTpot=Has $scenario 'tpot_limit_ms';$hasTtft=Has $scenario 'ttft_limit_s'
   if((Has $scenario 'sla_limits_unchanged') -and $scenario.sla_limits_unchanged -isnot [bool]){throw "sla_limits_unchanged must be a Boolean for $scenarioName."}
   if($hasTpot -ne $hasTtft){throw "Both SLA limits are required for $scenarioName."}
   $hasEligible=Has $scenario 'eligible_concurrency'
   if($hasEligible -and -not $hasTpot){throw "eligible_concurrency requires both SLA limits for $scenarioName."}
   if($hasTpot){
    [void](Limit $scenario.tpot_limit_ms "$scenarioName.tpot_limit_ms");[void](Limit $scenario.ttft_limit_s "$scenarioName.ttft_limit_s")
    if(-not $hasEligible -or $scenario.eligible_concurrency -isnot [array]){throw "An explicit eligible_concurrency array is required for $scenarioName."}
    $eligibleSeen=@{}
    foreach($candidate in $scenario.eligible_concurrency){
     $n=Limit $candidate "$scenarioName.eligible_concurrency"
     if($n -ne [Math]::Floor($n)){throw "Eligible concurrency must be an integer for $scenarioName."}
     $k=$n.ToString('R',[Globalization.CultureInfo]::InvariantCulture)
     if($eligibleSeen.ContainsKey($k)){throw "Duplicate eligible concurrency for $scenarioName."};$eligibleSeen[$k]=$true
    }
   }
  }
 }
}
$stage=Join-Path $outputDir ('.presentation-'+[Guid]::NewGuid().ToString('N')+'.xlsx')
$beforeIds=@(Get-Process EXCEL -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class PresentationExcelPid { [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid); }'
$excel=$null;$src=$null;$dst=$null;$pidOwned=0;$owned=$false;$ready=$false
function Release($x){if($null -ne $x){[void][Runtime.InteropServices.Marshal]::ReleaseComObject($x)}}
function Cell($ws,[int]$row,[int]$col){return $ws.Range(([char](64+$col)).ToString()+$row)}
function Canonical-Text([string]$value){return ([regex]::Replace($value.Trim(),'\s+',' ')).ToLowerInvariant()}
function Header-Key([string]$value){return ([regex]::Replace($value,'\s+','')).Replace('（','(').Replace('）',')').ToLowerInvariant()}
function Check-SlaHeaders($ws){
 $accepted=@{
  7=@('场景','场景名称','scenario','scenarioname');10=@('并发','并发数','maxconcurrency','concurrency')
  13=@('meanttft(s)','meanttft(秒)','平均ttft(s)','平均ttft(秒)','ttft均值(s)','ttft均值(秒)')
  15=@('meantpot(ms)','meantpot(毫秒)','平均tpot(ms)','平均tpot(毫秒)','tpot均值(ms)','tpot均值(毫秒)')
 }
 foreach($col in 7,10,13,15){$c=Cell $ws 1 $col;try{$v=Header-Key ([string]$c.Value2)}finally{Release $c};if($v -notin $accepted[$col]){throw "SLA recalculation requires recognized G/J/M/O headers with TTFT in seconds and TPOT in milliseconds; invalid column $col."}}
}
function Set-Text($cell,[string]$value){
 $cell.NumberFormat='@';if($value.Contains("`n")){$cell.WrapText=$true};$cell.Value2=$value
}
function Is-Number($v){return ($null -ne $v -and $v -isnot [string] -and $v -isnot [bool] -and $v -is [ValueType])}
function Same($a,$b){
 if($null -eq $a -or $null -eq $b){return ($null -eq $a -and $null -eq $b)}
 if((Is-Number $a) -and (Is-Number $b)){return [Math]::Abs([double]$a-[double]$b) -le [Math]::Max(1e-10,[Math]::Abs([double]$a)*1e-10)}
 return ([string]$a -ceq [string]$b)
}
function Signature($ws,[int]$row,[int]$col){
 $cell=Cell $ws $row $col;$inside=$null;$font=$null;$merge=$null;$borders=$null
 try{
  $inside=$cell.Interior;$font=$cell.Font;$merge=$cell.MergeArea;$borders=$merge.Borders
  $edge=@();foreach($n in 7,8,9,10){$edgeCell=$borders.Item($n);try{$edge+=([string]$edgeCell.LineStyle+':'+[string]$edgeCell.Weight+':'+[string]$edgeCell.Color)}finally{Release $edgeCell}}
  return @{Value=$cell.Value2;Formula=[string]$cell.Formula;NumberFormat=[string]$cell.NumberFormat;Color=[string]$inside.Color;Pattern=[string]$inside.Pattern;FontName=[string]$font.Name;FontSize=[string]$font.Size;FontBold=[string]$font.Bold;FontColor=[string]$font.Color;Borders=($edge -join '|');Merge=[string]$merge.Address();Wrap=[string]$cell.WrapText;HAlign=[string]$cell.HorizontalAlignment;VAlign=[string]$cell.VerticalAlignment}
 }finally{Release $borders;Release $merge;Release $font;Release $inside;Release $cell}
}
$expected=@{};$allowedTextFormat=@{};$allowedFill=@{};$layout=@{};$summary=New-Object System.Collections.Generic.List[string]
try{
 $excel=New-Object -ComObject Excel.Application
 [uint32]$pidNew=0;[void][PresentationExcelPid]::GetWindowThreadProcessId([IntPtr]$excel.Hwnd,[ref]$pidNew)
 if($pidNew -eq 0 -or $pidNew -in $beforeIds){throw 'Could not create a private Excel instance.'}
 $pidOwned=[int]$pidNew;$owned=$true;$excel.Visible=$false;$excel.DisplayAlerts=$false
 Write-Output ('OWNED_EXCEL_PID='+$pidOwned)
 $src=$excel.Workbooks.Open($inputFile,0,$true)
 $src.SaveCopyAs($stage)
 $dst=$excel.Workbooks.Open($stage,0,$false)
 $comparison=$false
 for($wi=1;$wi -le $src.Worksheets.Count;$wi++){
  $w=$src.Worksheets.Item($wi);$u=$w.UsedRange
  try{if($w.Name -ne '说明' -and ([int]$u.Column+[int]$u.Columns.Count-1) -ge 24){$comparison=$true}}finally{Release $u;Release $w}
 }
 foreach($spec in $config.sheets){
  $ws=$null
  try{
   try{$ws=$dst.Worksheets.Item([string]$spec.sheet)}catch{throw "Worksheet not found: $($spec.sheet)"}
   $u=$ws.UsedRange
   try{$lastRow=[int]$u.Row+[int]$u.Rows.Count-1;$lastCol=[int]$u.Column+[int]$u.Columns.Count-1}finally{Release $u}
   if($lastRow -lt 2 -or $lastRow -gt 1000 -or $lastCol -lt 22 -or $lastCol -gt 26){throw "Unexpected data table dimensions for $($spec.sheet)."}
   if(Has $spec 'scenarios'){foreach($scenario in $spec.scenarios){if(Has $scenario 'tpot_limit_ms'){Check-SlaHeaders $ws;break}}}
   $layout[[string]$spec.sheet]=@{LastRow=$lastRow;Width=$null;Height=$null}
   if(Has $spec 'software_column_width'){$column=$ws.Columns.Item(5);try{$column.ColumnWidth=[double]$spec.software_column_width;$layout[[string]$spec.sheet].Width=[double]$column.ColumnWidth}finally{Release $column}}
   if(Has $spec 'data_row_height'){
    for($rr=2;$rr -le $lastRow;$rr++){$rowRange=$ws.Rows.Item($rr);try{$rowRange.RowHeight=[double]$spec.data_row_height}finally{Release $rowRange}}
    $layout[[string]$spec.sheet].Height=[double]$spec.data_row_height
   }
   foreach($entry in @(@('hardware_text',4),@('software_text',5),@('parallelism_text',6))){
    $key=[string]$entry[0];$col=[int]$entry[1]
    if(Has $spec $key){$cell=Cell $ws 2 $col;$area=$null;try{
      $area=$cell.MergeArea;if([int]$area.Row -ne 2 -or [int]$area.Columns.Count -ne 1){throw "$key is not at the top of a single-column merge area."}
      $value=[string]$spec.$key
      for($mergeRow=[int]$area.Row;$mergeRow -lt ([int]$area.Row+[int]$area.Rows.Count);$mergeRow++){$allowedTextFormat["$($spec.sheet)|$mergeRow|$col"]=$value.Contains("`n")}
      Set-Text $cell $value;$expected["$($spec.sheet)|2|$col"]=$value
     }finally{Release $area;Release $cell}}
   }
   if((Has $spec 'software_text') -and ([string]$spec.software_text).Contains("`n")){
    $textCell=Cell $ws 2 5;$area=$null;$font=$null;$column=$null
    try{
     $area=$textCell.MergeArea;$font=$textCell.Font;$column=$ws.Columns.Item(5)
     $available=0.0;for($rr=[int]$area.Row;$rr -lt ([int]$area.Row+[int]$area.Rows.Count);$rr++){$rrObj=$ws.Rows.Item($rr);try{$available+=[double]$rrObj.RowHeight}finally{Release $rrObj}}
     $chars=[Math]::Max(1.0,[double]$column.ColumnWidth);$visualLines=0
     foreach($line in ([string]$spec.software_text -split "`n",0,'SimpleMatch')){
      $units=0.0;foreach($ch in $line.ToCharArray()){if([int]$ch -gt 127){$units+=2}else{$units+=1}}
      $visualLines += [Math]::Max(1,[Math]::Ceiling($units/$chars))
     }
     $estimated=[double]$font.Size * 1.25 * $visualLines + 4
     if($available -lt $estimated){throw "Multiline software text may be clipped: estimated $estimated points, available $available. Explicitly provide suitable software_column_width and data_row_height."}
    }finally{Release $column;Release $font;Release $area;Release $textCell}
   }
   $blocks=@{};$row=2
   while($row -le $lastRow){
    $cell=Cell $ws $row 7;$area=$null
    try{$area=$cell.MergeArea;$start=[int]$area.Row;$end=$start+[int]$area.Rows.Count-1;$label=[string]$cell.Value2}finally{Release $area;Release $cell}
    if($start -ne $row -or $end -gt $lastRow -or [string]::IsNullOrWhiteSpace($label) -or $blocks.ContainsKey($label)){throw "Scenario blocks are ambiguous at $($spec.sheet) row $row."}
    $blocks[$label]=@{Start=$row;End=$end};$row=$end+1
   }
   if(Has $spec 'scenarios'){
    $renameMap=@{}
    foreach($scenario in $spec.scenarios){
     $name=[string]$scenario.name
     if(-not $blocks.ContainsKey($name)){throw "Scenario not found: $($spec.sheet) / $name"}
     if((Has $scenario 'display_name') -and $comparison){throw 'Renaming scenarios in a comparison workbook is not supported; preserve baseline/tuning matching.'}
     if(Has $scenario 'display_name'){$renameMap[$name]=[string]$scenario.display_name}
    }
    $finalNames=@{}
    foreach($original in $blocks.Keys){
     $final=[string]$original;if($renameMap.ContainsKey($original)){$final=$renameMap[$original]}
     $key=Canonical-Text $final
     if([string]::IsNullOrWhiteSpace($key) -or $finalNames.ContainsKey($key)){throw 'Final scenario names conflict after whitespace and case normalization.'};$finalNames[$key]=$true
    }
    foreach($scenario in $spec.scenarios){
     $name=[string]$scenario.name
     if(-not $blocks.ContainsKey($name)){throw "Scenario not found: $($spec.sheet) / $name"}
     $start=[int]$blocks[$name].Start;$end=[int]$blocks[$name].End
     if((Has $scenario 'display_name') -and $comparison){throw 'Renaming scenarios in a comparison workbook is not supported; preserve baseline/tuning matching.'}
     foreach($entry in @(@('display_name',7),@('sla_text',8),@('feature_text',9))){
      $key=[string]$entry[0];$col=[int]$entry[1]
      if(Has $scenario $key){
       $cell=Cell $ws $start $col;$area=$null
       try{
        $area=$cell.MergeArea;if([int]$area.Row -ne $start -or ([int]$area.Row+[int]$area.Rows.Count-1) -ne $end -or [int]$area.Columns.Count -ne 1){throw "Scenario merge boundaries differ: $($spec.sheet) / $name / $key"}
        $value=[string]$scenario.$key
        if($key -eq 'sla_text' -and -not (Has $scenario 'tpot_limit_ms') -and [string]$cell.Value2 -cne $value){
         if(-not (Has $scenario 'sla_limits_unchanged') -or $scenario.sla_limits_unchanged -ne $true){throw "Changing SLA display requires explicit sla_limits_unchanged=true or both verified limits and eligible_concurrency for $name."}
        }
        for($mergeRow=$start;$mergeRow -le $end;$mergeRow++){$allowedTextFormat["$($spec.sheet)|$mergeRow|$col"]=$value.Contains("`n")}
        Set-Text $cell $value;$expected["$($spec.sheet)|$start|$col"]=$value
       }finally{Release $area;Release $cell}
      }
     }
     if(Has $scenario 'tpot_limit_ms'){
      $tpot=Limit $scenario.tpot_limit_ms 'tpot_limit_ms';$ttft=Limit $scenario.ttft_limit_s 'ttft_limit_s'
      $bestRow=0;$bestConcurrency=[double]::NegativeInfinity;$greenRows=@{};$greenCols=@{};$concurrencySeen=@{};$eligibleSet=@{}
      foreach($n in $scenario.eligible_concurrency){$k=([double]$n).ToString('R',[Globalization.CultureInfo]::InvariantCulture);$eligibleSet[$k]=$true}
      for($r=$start;$r -le $end;$r++){
       $j=Cell $ws $r 10;$m=Cell $ws $r 13;$o=Cell $ws $r 15
       try{
        $concurrency=$j.Value2;$meanTtft=$m.Value2;$meanTpot=$o.Value2
        if(-not (Is-Number $concurrency) -or -not (Is-Number $meanTtft) -or -not (Is-Number $meanTpot) -or [double]$concurrency -le 0){throw "Non-numeric SLA input at $($spec.sheet) row $r."}
        foreach($v in @($concurrency,$meanTtft,$meanTpot)){if([double]::IsNaN([double]$v) -or [double]::IsInfinity([double]$v) -or [double]$v -lt 0){throw "Invalid SLA input at $($spec.sheet) row $r."}}
        if([double]$concurrency -ne [Math]::Floor([double]$concurrency)){throw "Concurrency must be an integer at $($spec.sheet) row $r."}
        $concurrencyKey=([double]$concurrency).ToString('R',[Globalization.CultureInfo]::InvariantCulture)
        if($concurrencySeen.ContainsKey($concurrencyKey)){throw "Duplicate concurrency in scenario ${name}: $concurrencyKey"};$concurrencySeen[$concurrencyKey]=$true
        if($eligibleSet.ContainsKey($concurrencyKey) -and [double]$meanTtft -le $ttft -and [double]$meanTpot -le $tpot -and [double]$concurrency -gt $bestConcurrency){$bestRow=$r;$bestConcurrency=[double]$concurrency}
       }finally{Release $j;Release $m;Release $o}
       for($c=10;$c -le 20;$c++){
        $cell=Cell $ws $r $c;$inside=$null
        try{$inside=$cell.Interior;if([int]$inside.Color -eq 0x50D092){$greenRows[$r]=$true;$greenCols[$c]=$true}}finally{Release $inside;Release $cell}
       }
      }
      foreach($eligibleKey in $eligibleSet.Keys){if(-not $concurrencySeen.ContainsKey($eligibleKey)){throw "Eligible concurrency is not present in scenario $name."}}
      if($greenRows.Count -gt 1){throw "Multiple prior SLA highlight rows in $name; refusing to infer."}
      if($greenRows.Count -eq 1 -and $greenCols.Count -ne 11){throw "Incomplete J:T SLA highlight in $name; refusing to infer."}
      for($outsideRow=$start;$outsideRow -le $end;$outsideRow++){
       for($c=21;$c -le [Math]::Min(24,$lastCol);$c++){$cell=Cell $ws $outsideRow $c;$inside=$null;try{$inside=$cell.Interior;if([int]$inside.Color -eq 0x50D092){throw "Scenario has standard green outside J:T in $name; refusing to infer its meaning."}}finally{Release $inside;Release $cell}}
      }
      if($greenCols.Count -eq 0){foreach($c in 10..20){$greenCols[$c]=$true}}
      if($bestRow -gt 0){
       foreach($c in @($greenCols.Keys)){$cell=Cell $ws $bestRow ([int]$c);$inside=$null
        try{$inside=$cell.Interior;$color=[int]$inside.Color;$pattern=[int]$inside.Pattern;if($color -ne 0xFFFFFF -and $color -ne 0x50D092 -and $pattern -ne -4142){throw "Refusing to overwrite a custom cell fill: $($spec.sheet) row $bestRow column $c"}}finally{Release $inside;Release $cell}
       }
      }
      foreach($r in @($greenRows.Keys)){
       foreach($c in @($greenCols.Keys)){
        $cell=Cell $ws ([int]$r) ([int]$c);$inside=$null
        try{$inside=$cell.Interior;if([int]$inside.Color -eq 0x50D092){$inside.Color=0xFFFFFF;$allowedFill["$($spec.sheet)|$r|$c"]=0xFFFFFF}}finally{Release $inside;Release $cell}
       }
      }
      if($bestRow -gt 0){
       foreach($c in @($greenCols.Keys)){$cell=Cell $ws $bestRow ([int]$c);$inside=$null;try{$inside=$cell.Interior;$inside.Color=0x50D092;$allowedFill["$($spec.sheet)|$bestRow|$c"]=0x50D092}finally{Release $inside;Release $cell}}
      }
      $summary.Add("SLA_RESULT=$($spec.sheet)|$name|row=$bestRow|concurrency=$(if($bestRow -gt 0){$bestConcurrency}else{'none'})")
     }
    }
   }
  }finally{Release $ws}
 }
 $dst.Save();$dst.Close($false);Release $dst;$dst=$null
 $dst=$excel.Workbooks.Open($stage,0,$true)
 if($dst.Worksheets.Count -ne $src.Worksheets.Count){throw 'Sheet count changed.'}
 $checked=0
 for($i=1;$i -le $src.Worksheets.Count;$i++){
  $sw=$src.Worksheets.Item($i);$dw=$dst.Worksheets.Item($i);$su=$null;$du=$null
  try{
   if($sw.Name -ne $dw.Name){throw 'Sheet order changed.'};$su=$sw.UsedRange;$du=$dw.UsedRange
   if($su.Address() -ne $du.Address()){throw "Used range changed: $($sw.Name)"}
   $nr=[int]$su.Row+[int]$su.Rows.Count-1;$nc=[int]$su.Column+[int]$su.Columns.Count-1
   if($nr -gt 1000 -or $nc -gt 26){throw "Used range too large: $($sw.Name)"}
   for($c=1;$c -le $nc;$c++){
    $sc=$sw.Columns.Item($c);$dc=$dw.Columns.Item($c)
    try{$expectedWidth=[double]$sc.ColumnWidth;if($c -eq 5 -and $layout.ContainsKey([string]$sw.Name) -and $null -ne $layout[[string]$sw.Name].Width){$expectedWidth=[double]$layout[[string]$sw.Name].Width};if([Math]::Abs([double]$dc.ColumnWidth-$expectedWidth) -gt 0.01){throw "Column width mismatch: $($sw.Name) / $c"}}finally{Release $dc;Release $sc}
   }
   for($r=1;$r -le $nr;$r++){
    $sr=$sw.Rows.Item($r);$dr=$dw.Rows.Item($r)
    try{$expectedHeight=[double]$sr.RowHeight;if($r -ge 2 -and $layout.ContainsKey([string]$sw.Name) -and $null -ne $layout[[string]$sw.Name].Height){$expectedHeight=[double]$layout[[string]$sw.Name].Height};if([Math]::Abs([double]$dr.RowHeight-$expectedHeight) -gt 0.75){throw "Row height mismatch: $($sw.Name) / $r"}}finally{Release $dr;Release $sr}
   }
   for($r=1;$r -le $nr;$r++){for($c=1;$c -le $nc;$c++){
    $a=Signature $sw $r $c;$b=Signature $dw $r $c;$id="$($sw.Name)|$r|$c"
    foreach($field in @('FontName','FontSize','FontBold','FontColor','Borders','Merge','HAlign','VAlign')){if($a[$field] -cne $b[$field]){throw "Formatting changed unexpectedly: $id / $field"}}
    if($allowedTextFormat.ContainsKey($id) -and $allowedTextFormat[$id]){if($b.Wrap -cne 'True'){throw "Multiline cell does not wrap: $id"}} elseif($a.Wrap -cne $b.Wrap){throw "Wrap changed unexpectedly: $id"}
    if($allowedFill.ContainsKey($id)){if([int]$b.Color -ne [int]$allowedFill[$id]){throw "Highlight readback mismatch: $id"}} else {foreach($field in @('Color','Pattern')){if($a[$field] -cne $b[$field]){throw "Fill changed unexpectedly: $id / $field"}}}
    if($expected.ContainsKey($id)){
     if([string]$b.Value -cne [string]$expected[$id]){throw "Requested text mismatch: $id"}
     $cell=Cell $dw $r $c;try{if($cell.HasFormula -eq $true){throw "Requested text became an Excel formula: $id"}}finally{Release $cell}
    } else {
     if(-not (Same $a.Value $b.Value) -or $a.Formula -cne $b.Formula){throw "Unexpected cell content change: $id"}
     if(-not $allowedTextFormat.ContainsKey($id) -and $a.NumberFormat -cne $b.NumberFormat){throw "Unexpected number format change: $id"}
    }
    $checked++
   }}
  }finally{Release $du;Release $su;Release $dw;Release $sw}
 }
 $dst.Close($false);Release $dst;$dst=$null;$src.Close($false);Release $src;$src=$null
 if((Get-Sha256 $inputFile) -ne $sourceHash){throw 'Source workbook changed while processing.'}
 $ready=$true
}finally{
 $cleanupComplete=$false
 try{
  if($null -ne $dst){try{$dst.Close($false)}catch{};Release $dst}
  if($null -ne $src){try{$src.Close($false)}catch{};Release $src}
  if($null -ne $excel){if($owned){$excel.Quit()};Release $excel}
  [GC]::Collect();[GC]::WaitForPendingFinalizers();[GC]::Collect()
  if($owned){
   for($i=0;$i -lt 15 -and (Get-Process -Id $pidOwned -ErrorAction SilentlyContinue);$i++){Start-Sleep -Milliseconds 500}
   if(Get-Process -Id $pidOwned -ErrorAction SilentlyContinue){
    $proc=Get-Process -Id $pidOwned;$identity=Get-CimInstance Win32_Process -Filter ('ProcessId='+$pidOwned)
    if($proc.ProcessName -ne 'EXCEL' -or $proc.MainWindowHandle -ne 0 -or $identity.CommandLine -notmatch '/automation -Embedding'){throw 'Owned Excel process could not be safely cleaned.'}
    Stop-Process -Id $pidOwned -ErrorAction Stop;Write-Output ('CLEANED_OWNED_EXCEL_PID='+$pidOwned)
   }
  }
  $cleanupComplete=$true
 }finally{
  if(( -not $ready -or -not $cleanupComplete) -and [IO.File]::Exists($stage)){
   try{[IO.File]::Delete($stage)}catch{throw "Failed to remove this run's temporary workbook: $stage"}
  }
 }
}
try{
 if(-not $ready){throw 'Presentation validation incomplete.'}
 if(Test-Path -LiteralPath $outputFile){throw 'Output appeared during processing; refusing overwrite.'}
 [IO.File]::Move($stage,$outputFile)
}finally{
 if([IO.File]::Exists($stage)){try{[IO.File]::Delete($stage)}catch{throw "Failed to remove this run's temporary workbook: $stage"}}
}
$summary | ForEach-Object {Write-Output $_}
Write-Output ('CHECKED_CELLS='+$checked)
Write-Output ('SOURCE_SHA256='+$sourceHash)
Write-Output ('PRESENTATION_SHA256='+$jsonHash)
Write-Output ('OUTPUT='+$outputFile)
Write-Output ('OUTPUT_SHA256='+(Get-Sha256 $outputFile))
Write-Output 'PRESENTATION_VALIDATION=PASS'
