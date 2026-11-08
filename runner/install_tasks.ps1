# Creates the Windows scheduled tasks for one agent. Read it, edit $plan, then run it yourself:
#   powershell -ExecutionPolicy Bypass -File install_tasks.ps1 -AgentDir "C:\agents\my-agent"
# Task names are prefixed with the folder name, so two agents do not overwrite each other.
# Remove later with: Unregister-ScheduledTask -TaskName "<name>" -Confirm:$false
param([Parameter(Mandatory=$true)][string]$AgentDir)
$ErrorActionPreference = "Stop"
$AgentDir = (Resolve-Path $AgentDir).Path
$vbs = Join-Path $AgentDir "runner\run_agent.vbs"
if (-not (Test-Path $vbs)) { throw "Not found: $vbs" }
New-Item -ItemType Directory -Force (Join-Path $AgentDir "logs") | Out-Null
$prefix = Split-Path $AgentDir -Leaf
$plan = @(
  @{ Mode = "daily"; Time = "09:30" },
  @{ Mode = "learn"; Time = "20:30" }
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
foreach ($t in $plan) {
  $name = "$prefix-$($t.Mode)"
  $action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbs`" $($t.Mode)"
  $trigger = New-ScheduledTaskTrigger -Daily -At $t.Time
  Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
  Write-Output "$name registered: daily at $($t.Time), mode $($t.Mode)"
}
