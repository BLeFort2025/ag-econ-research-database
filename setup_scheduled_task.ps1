<#
.SYNOPSIS
    Register a Windows Task Scheduler task to run the Ag Econ Research Database
    monthly harvest on the 1st Tuesday of each month at 9:00 AM EST.

.DESCRIPTION
    This script creates a scheduled task called "AgEconResearchDB_MonthlyHarvest"
    that runs scheduled_harvest.py using the current Python environment.

    Run this script ONCE as Administrator to register the task.
    To unregister: Unregister-ScheduledTask -TaskName "AgEconResearchDB_MonthlyHarvest"

.NOTES
    Requires: Run as Administrator (for task registration)
    Requires: Python accessible from PATH or specify full path below
#>

# ── Configuration ──────────────────────────────────────────────────────
$TaskName  = "AgEconResearchDB_MonthlyHarvest"
$TaskDesc  = "Monthly harvest of agricultural economics research papers (OpenAlex, AgEcon Search, Grey Literature, PDFs). Runs on the 1st Tuesday of each month at 9:00 AM EST."

# Project directory (where scheduled_harvest.py lives)
$ProjectDir = "c:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Ben Desktop Files\Economic Analyst Position\Economic papers\Ag Economic Research Database"
$ScriptPath = Join-Path $ProjectDir "scheduled_harvest.py"

# Find Python executable
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonExe) {
    Write-Error "Python not found in PATH. Please specify the full path to python.exe."
    exit 1
}

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  Ag Econ Research DB — Scheduled Task Installer" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Task Name:   $TaskName"
Write-Host "  Schedule:    1st Tuesday of each month, 9:00 AM EST"
Write-Host "  Python:      $PythonExe"
Write-Host "  Script:      $ScriptPath"
Write-Host "  Working Dir: $ProjectDir"
Write-Host ""

# ── Check if task already exists ──
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "  [!] Task '$TaskName' already exists. Removing old task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# ── Build the Trigger ──
# "First Tuesday of each month at 09:00 EST"
# Windows Task Scheduler supports monthly + day-of-week via XML.
# We use a Monthly trigger with WeeksOfMonth=First, DaysOfWeek=Tuesday.

$triggerXml = @"
<CalendarTrigger xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <StartBoundary>2026-04-01T09:00:00-05:00</StartBoundary>
  <Enabled>true</Enabled>
  <ScheduleByMonth>
    <Months>
      <January /><February /><March /><April />
      <May /><June /><July /><August />
      <September /><October /><November /><December />
    </Months>
  </ScheduleByMonth>
</CalendarTrigger>
"@

# Since PowerShell's New-ScheduledTaskTrigger doesn't natively support
# "first Tuesday of month", we build the full task XML:
$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>$TaskDesc</Description>
    <Author>$env:USERNAME</Author>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-05-06T09:00:00-05:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByMonthDayOfWeek>
        <Weeks><Week>1</Week></Weeks>
        <DaysOfWeek><Tuesday /></DaysOfWeek>
        <Months>
          <January /><February /><March /><April />
          <May /><June /><July /><August />
          <September /><October /><November /><December />
        </Months>
      </ScheduleByMonthDayOfWeek>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$PythonExe</Command>
      <Arguments>"$ScriptPath"</Arguments>
      <WorkingDirectory>$ProjectDir</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

# ── Register the Task ──
try {
    Register-ScheduledTask -TaskName $TaskName -Xml $taskXml -Force | Out-Null
    Write-Host "  [✓] Task '$TaskName' registered successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Key Settings:" -ForegroundColor Gray
    Write-Host "    • Runs even if laptop is on battery" -ForegroundColor Gray
    Write-Host "    • Catches up if machine was off on schedule day" -ForegroundColor Gray
    Write-Host "    • Requires network connection" -ForegroundColor Gray
    Write-Host "    • Max runtime: 4 hours" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  To test now:   schtasks /Run /TN `"$TaskName`"" -ForegroundColor Yellow
    Write-Host "  To view:       Get-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor Yellow
    Write-Host "  To remove:     Unregister-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor Yellow
    Write-Host ""
}
catch {
    Write-Error "Failed to register task: $_"
    Write-Host ""
    Write-Host "  [!] If you see 'Access denied', run this script as Administrator:" -ForegroundColor Red
    Write-Host "      Right-click PowerShell → Run as Administrator → re-run this script" -ForegroundColor Red
    exit 1
}
