$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Python      = (Get-Command python -ErrorAction SilentlyContinue).Source
$LogFile     = "$ProjectRoot\lighthouse.log"
$Owner       = 'ricardobertolin'
$Repo        = 'the_lighthouse_app'

function Log($msg) {
    $line = '[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $msg
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

function Get-GhHeaders {
    $h = @{ 'User-Agent' = 'lighthouse-daily'; 'Accept' = 'application/vnd.github+json' }
    # Authenticated calls get 5000 req/hr instead of 60; optional.
    if     ($env:GH_TOKEN)     { $h['Authorization'] = 'Bearer ' + $env:GH_TOKEN }
    elseif ($env:GITHUB_TOKEN) { $h['Authorization'] = 'Bearer ' + $env:GITHUB_TOKEN }
    return $h
}

# Polls the "pages build and deployment" run for a SPECIFIC commit. Matching on
# the sha matters: querying only the newest deployment reports stale successes
# from previous days whenever a build fails before the deploy job runs.
function Wait-PagesDeployment {
    param(
        [Parameter(Mandatory = $true)][string]$Sha,
        [int]$MaxWaitSec = 600,
        [int]$PollSec    = 30
    )

    $headers  = Get-GhHeaders
    $runsUrl  = 'https://api.github.com/repos/' + $Owner + '/' + $Repo + '/actions/runs?head_sha=' + $Sha + '&per_page=5'
    $deadline = (Get-Date).AddSeconds($MaxWaitSec)
    $short    = $Sha.Substring(0, 7)

    Log ('Waiting for Pages build of ' + $short + ' (up to ' + $MaxWaitSec + 's)...')
    Start-Sleep -Seconds 20

    while ((Get-Date) -lt $deadline) {
        try {
            $runs = Invoke-RestMethod -Uri $runsUrl -Headers $headers -TimeoutSec 15
            $run  = $runs.workflow_runs | Where-Object { $_.name -like 'pages build*' } | Select-Object -First 1

            if (-not $run) {
                Log ('  no Pages run for ' + $short + ' yet...')
            }
            elseif ($run.status -ne 'completed') {
                Log ('  build ' + $short + ': ' + $run.status)
            }
            elseif ($run.conclusion -eq 'success') {
                Log ('Pages build SUCCEEDED for ' + $short)
                return 'success'
            }
            else {
                Log ('Pages build ' + $run.conclusion.ToUpper() + ' for ' + $short)
                Log ('  ' + $run.html_url)
                return 'failed'
            }
        } catch {
            Log ('API poll error: ' + $_.Exception.Message)
        }
        Start-Sleep -Seconds $PollSec
    }

    Log ('TIMEOUT waiting for Pages build of ' + $short)
    return 'timeout'
}

# ── Main ──────────────────────────────────────────────────────────────────────

Set-Location $ProjectRoot
Log '=== Starting The Lighthouse ==='

if (-not $Python) {
    Log 'ERROR: python not found in PATH.'
    exit 1
}

Log 'Running digest pipeline...'
& $Python -m digest --no-browser 2>&1 | ForEach-Object {
    Add-Content -Path $LogFile -Value ('[' + (Get-Date -Format 'HH:mm:ss') + '] ' + $_)
    Write-Host $_
}
if ($LASTEXITCODE -ne 0) {
    Log ('ERROR: digest failed with exit code ' + $LASTEXITCODE)
    exit $LASTEXITCODE
}

$date = Get-Date -Format 'yyyy-MM-dd'
Log 'Committing and pushing...'
git add index.html
git commit -m "digest: $date"
git push

if ($LASTEXITCODE -ne 0) {
    Log ('ERROR: git push failed with exit code ' + $LASTEXITCODE)
    exit $LASTEXITCODE
}

# ── Check Pages deployment, retry once if it fails ───────────────────────────

$sha    = (git rev-parse HEAD).Trim()
$result = Wait-PagesDeployment -Sha $sha

if ($result -eq 'success') {
    Log '=== Done. Digest is live. ==='
    exit 0
}

Log ('Deployment ' + $result + ' -- retrying push to trigger a new deployment...')
git commit --allow-empty -m "retry deploy: $date"
git push

if ($LASTEXITCODE -ne 0) {
    Log ('ERROR: retry push failed with exit code ' + $LASTEXITCODE)
    exit $LASTEXITCODE
}

$sha2    = (git rev-parse HEAD).Trim()
$result2 = Wait-PagesDeployment -Sha $sha2

if ($result2 -eq 'success') {
    Log '=== Done (after retry). Digest is live. ==='
    exit 0
} else {
    Log ('ERROR: deployment still ' + $result2 + ' after retry. Digest is NOT live.')
    Log ('  https://github.com/' + $Owner + '/' + $Repo + '/actions')
    exit 1
}
