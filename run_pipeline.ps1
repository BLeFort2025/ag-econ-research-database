# ==============================================================================
# Agricultural Economics Research Database — Automated Pipeline Runner
# Runs: OpenAlex + AgEcon Search + Grey Literature + PDF Downloader + PyMuPDF Extraction + ChromaDB Indexing
# ==============================================================================

$ErrorActionPreference = "Continue"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  STARTING AG ECON RESEARCH INGESTION & DEEP TEXT PIPELINE" -ForegroundColor Green
Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
Write-Host "======================================================================" -ForegroundColor Green

python -X utf8 scheduled_harvest.py

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  PIPELINE EXECUTION COMPLETE" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
