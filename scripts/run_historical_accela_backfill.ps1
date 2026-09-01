[CmdletBinding()]
param(
    [string]$FromMonth = "2020-01",
    [string]$ToMonth = "2025-07",
    [switch]$ResumeInspectionBackfill,
    [string]$InspectionFromMonth = "2025-08",
    [string]$InspectionToMonth = "2026-08",
    [string[]]$InspectionModules = @("Building"),
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function ConvertTo-MonthStart {
    param([Parameter(Mandatory)][string]$Value)

    try {
        return [datetime]::ParseExact(
            "$Value-01",
            "yyyy-MM-dd",
            [Globalization.CultureInfo]::InvariantCulture
        )
    }
    catch {
        throw "Invalid month '$Value'; use YYYY-MM."
    }
}

$datasetStart = [datetime]"2020-01-01"
$fromDate = ConvertTo-MonthStart $FromMonth
$toDate = ConvertTo-MonthStart $ToMonth
if ($fromDate -lt $datasetStart) {
    throw "FromMonth cannot be before the dataset boundary (2020-01)."
}
if ($fromDate -gt $toDate) {
    throw "FromMonth must be on or before ToMonth."
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = (Get-Command python -ErrorAction Stop).Source
$exportArguments = @(
    "scripts/backfill_accela.py",
    "--from-month", $FromMonth,
    "--to-month", $ToMonth
)
$inspectionArguments = @(
    "scripts/backfill_accela_inspections.py",
    "--from-month", $InspectionFromMonth,
    "--to-month", $InspectionToMonth,
    "--modules"
) + $InspectionModules
$finalizeArguments = @(
    "scripts/finalize_accela_inspection_backfill.py",
    "--collector-pid", "$PID",
    "--from-month", $InspectionFromMonth,
    "--to-month", $InspectionToMonth
)

if ($DryRun) {
    [pscustomobject]@{
        DatasetStart = $datasetStart.ToString("yyyy-MM-dd")
        ExportCommand = (@($python) + $exportArguments) -join " "
        ResumeInspectionBackfill = [bool]$ResumeInspectionBackfill
        InspectionCommand = (@($python) + $inspectionArguments) -join " "
        FinalizeCommand = (@($python) + $finalizeArguments) -join " "
    } | ConvertTo-Json
    exit 0
}

Push-Location $repositoryRoot
try {
    & $python @exportArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Historical Accela export backfill exited with code $LASTEXITCODE."
    }

    if ($ResumeInspectionBackfill) {
        & $python @inspectionArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Accela inspection backfill exited with code $LASTEXITCODE."
        }

        & $python @finalizeArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Accela inspection finalization exited with code $LASTEXITCODE."
        }
    }
}
finally {
    Pop-Location
}
