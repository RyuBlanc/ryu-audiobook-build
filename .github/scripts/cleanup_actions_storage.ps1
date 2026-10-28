$ErrorActionPreference = 'Stop'
Write-Host 'This legacy cleanup helper is intentionally non-destructive.'
Write-Host 'It must not delete workflow runs, logs, or test-evidence artifacts.'
Write-Host 'Superseded installer/portable artifacts are pruned only by .github/workflows/actions-storage-cleanup.yml after a successful [artifact-checkpoint] package set has been uploaded.'
exit 0
