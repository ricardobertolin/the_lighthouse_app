# Run this once to register the daily Task Scheduler job.
# After that, just leave the PC running — the digest publishes itself at 10 AM.
# If the PC was off at 10 AM, the task runs as soon as it wakes up (StartWhenAvailable).

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ScriptPath  = "$ProjectRoot\lighthouse-daily.ps1"

$action = New-ScheduledTaskAction `
    -Execute  "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`""

$trigger = New-ScheduledTaskTrigger -Daily -At "10:00AM"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId    $env:USERNAME `
    -LogonType Interactive `
    -RunLevel  Limited

Register-ScheduledTask `
    -TaskName  "The Lighthouse" `
    -Action    $action `
    -Trigger   $trigger `
    -Settings  $settings `
    -Principal $principal `
    -Force

Write-Host ""
Write-Host "Task registered. The Lighthouse will run daily at 10:00 AM."
Write-Host "If the PC is off at 10 AM it will run on next wake-up."
Write-Host ""
Write-Host "To run manually at any time:"
Write-Host "  .\lighthouse-daily.ps1"
Write-Host ""
Write-Host "To check or remove the task:"
Write-Host "  Get-ScheduledTask -TaskName 'The Lighthouse'"
Write-Host "  Unregister-ScheduledTask -TaskName 'The Lighthouse'"
