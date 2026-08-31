# This script automatically updates the Ag Econ Research Database
# It is designed to be run by the Windows Task Scheduler

# Set the working directory to the location of this script
$ScriptDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition
Set-Location -Path $ScriptDir

# Ensure text output is in UTF-8 to prevent encoding crashes
$env:PYTHONIOENCODING = "utf-8"

# Run the full pipeline
Write-Output "[$(Get-Date)] Starting automated database update..."
python pipeline.py full >> automated_update.log 2>&1
Write-Output "[$(Get-Date)] Update complete."
