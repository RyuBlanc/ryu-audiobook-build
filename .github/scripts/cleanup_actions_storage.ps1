$ErrorActionPreference = 'Stop'
Write-Host 'Automatic Actions run/artifact deletion is disabled pending Version 1.2.0 acceptance.'
Write-Host 'Preserve per-substage tests, full-suite logs, failed-run diagnostics, checkpoint installers, portable builds and SHA-256 manifests.'
Write-Host 'Do not enable pruning without explicit user approval after release acceptance.'
exit 0
