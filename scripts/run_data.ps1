# Windows equivalent of the Makefile data targets.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\run_data.ps1 [data-check|data-rebuild|data-test]
param([ValidateSet("data-check", "data-rebuild", "data-test")][string]$Target = "data-check")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
$py = if ($env:PY) { $env:PY } else { ".venv\Scripts\python.exe" }

function Run([string[]]$cmd) {
    Write-Host ">> $py $($cmd -join ' ')"
    & $py @cmd
    if ($LASTEXITCODE -ne 0) { throw "failed: $($cmd -join ' ') (exit $LASTEXITCODE)" }
}

switch ($Target) {
    "data-check" { Run @("pipelines/check_data.py") }
    "data-rebuild" {
        Run @("pipelines/build_region.py", "--reuse-extract")
        Run @("pipelines/build_catalogue.py")
        Run @("pipelines/freeze_score_params.py")
        Run @("pipelines/tag_homes.py")
        Run @("pipelines/build_feature_availability.py")
        Run @("pipelines/select_demo_homes.py")
        Run @("pipelines/make_monthly_demo.py")
        Run @("pipelines/audit_sales_matches.py")
    }
    "data-test" { Run @("-m", "pytest", "-q", "tests/unit", "tests/data") }
}
