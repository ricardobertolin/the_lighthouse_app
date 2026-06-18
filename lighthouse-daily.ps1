$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Python      = (Get-Command python -ErrorAction SilentlyContinue).Source
$LogFile     = "$ProjectRoot\lighthouse.log"

function Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

Set-Location $ProjectRoot
Log "=== Starting The Lighthouse ==="

if (-not $Python) {
    Log "ERROR: python not found in PATH."
    exit 1
}

Log "Running digest pipeline..."
& $Python -m digest --no-browser 2>&1 | ForEach-Object {
    Add-Content -Path $LogFile -Value "[$(Get-Date -Format 'HH:mm:ss')] $_"
    Write-Host $_
}
if ($LASTEXITCODE -ne 0) {
    Log "ERROR: digest failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

$date = Get-Date -Format 'yyyy-MM-dd'
Log "Committing and pushing docs/index.html..."
git add index.html
git commit -m "digest: $date"
git push

if ($LASTEXITCODE -ne 0) {
    Log "ERROR: git push failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Log "=== Done. Digest is live. ==="
