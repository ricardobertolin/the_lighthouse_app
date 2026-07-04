$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Python      = (Get-Command python -ErrorAction SilentlyContinue).Source
$LogFile     = "$ProjectRoot\lighthouse.log"
$Owner       = "ricardobertolin"
$Repo        = "the_lighthouse_app"

function Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

# Polls GitHub Pages deployment status after a push.
# Returns "success", "failed", or "timeout".
function Wait-PagesDeployment {
    param([int]$MaxWaitSec = 180, [int]$PollSec = 20)

    $headers  = @{ "User-Agent" = "lighthouse-daily" }
    $depsUrl  = "https://api.github.com/repos/$Owner/$Repo/deployments?environment=github-pages&per_page=1"
    $deadline = (Get-Date).AddSeconds($MaxWaitSec)

    Log "Waiting for GitHub Pages deployment (up to ${MaxWaitSec}s)..."
    Start-Sleep -Seconds 25   # give GitHub time to register the push

    while ((Get-Date) -lt $deadline) {
        try {
            $deps = Invoke-RestMethod -Uri $depsUrl -Headers $headers -TimeoutSec 10
            if ($deps.Count -gt 0) {
                $statusUrl = "https://api.github.com/repos/$Owner/$Repo/deployments/$($deps[0].id)/statuses?per_page=1"
                $statuses  = Invoke-RestMethod -Uri $statusUrl -Headers $headers -TimeoutSec 10
                if ($statuses.Count -gt 0) {
                    $state = $statuses[0].state
                    Log "Pages status: $state"
                    if ($state -eq "success")                              { return "success" }
                    if ($state -in @("failure","error","inactive"))        { return "failed"  }
                }
            }
        } catch {
            Log "API poll error: $_"
        }
        Start-Sleep -Seconds $PollSec
    }
    return "timeout"
}

# ── Main ─────────────────────────────────────────────────────────────────────

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
Log "Committing and pushing..."
git add index.html
git commit -m "digest: $date"
git push

if ($LASTEXITCODE -ne 0) {
    Log "ERROR: git push failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

# ── Check Pages deployment, retry once if it fails ───────────────────────────

$result = Wait-PagesDeployment -MaxWaitSec 180 -PollSec 20

if ($result -eq "success") {
    Log "=== Done. Digest is live. ==="
    exit 0
}

Log "Deployment $result — retrying push to trigger a new deployment..."
git commit --allow-empty -m "retry deploy: $date"
git push

if ($LASTEXITCODE -ne 0) {
    Log "ERROR: retry push failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

$result2 = Wait-PagesDeployment -MaxWaitSec 180 -PollSec 20

if ($result2 -eq "success") {
    Log "=== Done (after retry). Digest is live. ==="
    exit 0
} else {
    Log "WARNING: deployment still $result2 after retry. Check GitHub Pages manually."
    exit 1
}
