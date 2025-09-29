param(
    [string]$RequirementsPath = (Join-Path $PSScriptRoot '..' 'requirements.txt'),
    [switch]$VerbosePip,
    [switch]$ContinueOnError
)

if (-not (Test-Path $RequirementsPath)) {
    Write-Error "Girdi dosyası bulunamadı: $RequirementsPath"
    exit 1
}

$rawLines = Get-Content $RequirementsPath | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
$dependencies = @()
foreach ($line in $rawLines) {
    $trimmed = $line.Trim()
    if (-not $trimmed.StartsWith('#')) {
        $dependencies += $trimmed
    }
}

if ($dependencies.Count -eq 0) {
    Write-Warning 'requirements.txt dosyasında işlenecek bağımlılık bulunamadı.'
    return
}

$python = Get-Command py -ErrorAction SilentlyContinue
if ($python) {
    $pythonExe = 'py'
    $pythonArgs = @('-3.11')
} else {
    $pythonExe = 'python'
    $pythonArgs = @()
}

Write-Host "Toplam $($dependencies.Count) bağımlılık kontrol edilecek." -ForegroundColor Cyan
Write-Host 'Her bağımlılık ayrı ayrı yüklenerek hangi paketin hata verdiği tespit edilmeye çalışılacak.' -ForegroundColor Cyan
Write-Host ''

$failures = @()
for ($i = 0; $i -lt $dependencies.Count; $i++) {
    $package = $dependencies[$i]
    $header = "[$($i + 1)/$($dependencies.Count)] $package"
    Write-Host $header -ForegroundColor Yellow

    $args = $pythonArgs + @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', $package)
    if ($VerbosePip) {
        $args += '--verbose'
    }

    & $pythonExe @args
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 0) {
        Write-Host '  -> Başarılı' -ForegroundColor Green
    } else {
        Write-Host "  -> Hata (çıkış kodu $exitCode)" -ForegroundColor Red
        $failures += [PSCustomObject]@{ Paket = $package; Kod = $exitCode }
        if (-not $ContinueOnError) {
            break
        }
    }

    Write-Host ''
}

if ($failures.Count -eq 0) {
    Write-Host 'Tüm bağımlılıklar sorunsuz işlendi.' -ForegroundColor Green
} else {
    Write-Host 'Hata veren bağımlılıklar:' -ForegroundColor Red
    foreach ($failure in $failures) {
        Write-Host "  - $($failure.Paket) (çıkış kodu $($failure.Kod))" -ForegroundColor Red
    }
    Write-Host ''
    Write-Host 'Detaylı günlük için hata veren paketin hemen üstündeki pip çıktısına bakabilirsiniz.'
}
