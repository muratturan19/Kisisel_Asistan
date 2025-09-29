param()

$base = [IO.Path]::Combine($env:USERPROFILE, 'MiraData')
$paths = @(
    $base,
    Join-Path $base 'inbox',
    Join-Path $base 'archive',
    Join-Path $base 'archive/by_topic',
    Join-Path $base 'archive/by_type',
    Join-Path $base 'audio',
    Join-Path $base 'transcripts',
    Join-Path $base 'summaries',
    Join-Path $base 'db',
    Join-Path $base 'logs'
)

foreach ($path in $paths) {
    if (-not (Test-Path $path)) {
        New-Item -Path $path -ItemType Directory | Out-Null
    }
}

# Check Tesseract availability
$tesseract = Get-Command tesseract -ErrorAction SilentlyContinue
if (-not $tesseract) {
    Write-Warning 'Tesseract OCR bulunamadı. OCR özellikleri sınırlı olacaktır.'
}
