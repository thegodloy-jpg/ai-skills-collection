param(
    [Parameter(Mandatory = $true)]
    [string]$TargetPath,

    [Parameter(Mandatory = $true)]
    [string]$ContentPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Convert-ToSlug {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $stopWords = @(
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
        "into", "is", "of", "on", "or", "that", "the", "to", "with", "while",
        "this", "these", "those", "it", "its", "was", "were", "will"
    )

    $normalized = $Text.ToLowerInvariant()
    $normalized = $normalized -replace "`"", " "
    $normalized = $normalized -replace "'", " "
    $normalized = $normalized -replace "[^a-z0-9]+", " "
    $normalized = $normalized -replace "\s+", " "
    $normalized = $normalized.Trim()

    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return "conversation-context"
    }

    $tokens = @()
    foreach ($token in ($normalized -split " ")) {
        if ($token.Length -lt 2) {
            continue
        }
        if ($stopWords -contains $token) {
            continue
        }
        $tokens += $token
        if ($tokens.Count -ge 8) {
            break
        }
    }

    if ($tokens.Count -eq 0) {
        return "conversation-context"
    }

    $slug = ($tokens -join "-")
    if ($slug.Length -gt 64) {
        $slug = $slug.Substring(0, 64).TrimEnd("-")
    }

    if ([string]::IsNullOrWhiteSpace($slug)) {
        return "conversation-context"
    }

    return $slug
}

function Get-TopicSlugFromContent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ContentText
    )

    $lines = $ContentText -split "(\r?\n)"
    $candidate = ""

    foreach ($rawLine in $lines) {
        $line = $rawLine.Trim()
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        $match = [System.Text.RegularExpressions.Regex]::Match(
            $line,
            "^-?\s*Primary objective\s*:\s*(.+)$",
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
        if ($match.Success) {
            $candidate = $match.Groups[1].Value.Trim()
            break
        }
    }

    if ([string]::IsNullOrWhiteSpace($candidate)) {
        foreach ($rawLine in $lines) {
            $line = $rawLine.Trim()
            if ($line.StartsWith("# ")) {
                $candidate = $line.Substring(2).Trim()
                break
            }
        }
    }

    if ([string]::IsNullOrWhiteSpace($candidate)) {
        foreach ($rawLine in $lines) {
            $line = $rawLine.Trim()
            if (-not [string]::IsNullOrWhiteSpace($line)) {
                $candidate = $line
                break
            }
        }
    }

    return (Convert-ToSlug -Text $candidate)
}

function Get-FinalPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$InputPath,

        [Parameter(Mandatory = $true)]
        [string]$ContentText
    )

    $trimmedInput = $InputPath.Trim()
    if ([string]::IsNullOrWhiteSpace($trimmedInput)) {
        throw "TargetPath cannot be empty."
    }

    # Existing directory, or a trailing slash, means directory mode.
    $hasDirectoryHint = $trimmedInput.EndsWith("\") -or $trimmedInput.EndsWith("/")

    # Resolve to absolute path early so downstream output is deterministic.
    $resolvedInput = [System.IO.Path]::GetFullPath($trimmedInput)
    $isExistingDirectory = Test-Path -LiteralPath $resolvedInput -PathType Container
    if ($isExistingDirectory -or $hasDirectoryHint) {
        $directory = $resolvedInput
        if (-not (Test-Path -LiteralPath $directory)) {
            New-Item -ItemType Directory -Path $directory -Force | Out-Null
        }

        $topicSlug = Get-TopicSlugFromContent -ContentText $ContentText
        $baseName = "ctx_{0}_{1}" -f $topicSlug, (Get-Date -Format "yyyyMMdd-HHmmss")
        $candidate = Join-Path $directory ($baseName + ".md")
        $counter = 1
        while (Test-Path -LiteralPath $candidate) {
            $candidate = Join-Path $directory ("{0}_{1}.md" -f $baseName, $counter)
            $counter++
        }
        return $candidate
    }

    $directory = [System.IO.Path]::GetDirectoryName($resolvedInput)
    if (-not $directory) {
        $directory = (Get-Location).Path
    }

    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    $fileName = [System.IO.Path]::GetFileNameWithoutExtension($resolvedInput)
    $extension = [System.IO.Path]::GetExtension($resolvedInput)
    if ([string]::IsNullOrWhiteSpace($extension)) {
        $extension = ".md"
    }

    $candidate = Join-Path $directory ($fileName + $extension)
    if (-not (Test-Path -LiteralPath $candidate)) {
        return $candidate
    }

    # Existing file -> append timestamp to preserve history.
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    return (Join-Path $directory ("{0}_{1}{2}" -f $fileName, $timestamp, $extension))
}

if (-not (Test-Path -LiteralPath $ContentPath)) {
    throw "ContentPath does not exist: $ContentPath"
}

$content = Get-Content -LiteralPath $ContentPath -Raw -Encoding UTF8
$finalPath = Get-FinalPath -InputPath $TargetPath -ContentText $content
Set-Content -LiteralPath $finalPath -Value $content -Encoding UTF8

$absoluteFinal = [System.IO.Path]::GetFullPath($finalPath)
Write-Output ("Context saved: {0}" -f $absoluteFinal)
