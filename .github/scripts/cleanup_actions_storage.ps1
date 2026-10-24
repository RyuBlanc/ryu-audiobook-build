$ErrorActionPreference = 'Stop'

$repository = [string]$env:REPOSITORY
$currentRunId = [string]$env:CURRENT_RUN_ID
$currentWorkflowName = [string]$env:CURRENT_WORKFLOW_NAME
$pruneCurrentWorkflowToCurrent = ([string]$env:PRUNE_CURRENT_WORKFLOW_TO_CURRENT -eq 'true')
if ([string]::IsNullOrWhiteSpace($repository)) { throw 'REPOSITORY is required for Actions storage cleanup.' }
if ([string]::IsNullOrWhiteSpace($env:GH_TOKEN)) { throw 'GH_TOKEN is required for Actions storage cleanup.' }

Write-Host "Enumerating completed GitHub Actions runs for $repository."
$runLines = gh api --paginate -H 'Accept: application/vnd.github+json' "/repos/$repository/actions/runs?per_page=100" --jq '.workflow_runs[] | [.id,.name,.status,.conclusion,.created_at,.head_sha,.head_branch] | @tsv'
if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate GitHub Actions runs; no history was deleted.' }

$allRuns = [System.Collections.Generic.List[object]]::new()
foreach ($line in @($runLines)) {
    if ([string]::IsNullOrWhiteSpace([string]$line)) { continue }
    $parts = ([string]$line).Split([char]9, 7)
    if ($parts.Count -ne 7) { Write-Warning "Skipping malformed run-list row: $line"; continue }
    $allRuns.Add([pscustomobject]@{
        id = [string]$parts[0]
        name = [string]$parts[1]
        status = [string]$parts[2]
        conclusion = [string]$parts[3]
        created_at = [string]$parts[4]
        head_sha = [string]$parts[5]
        head_branch = [string]$parts[6]
    })
}

$prLines = gh api --paginate -H 'Accept: application/vnd.github+json' "/repos/$repository/pulls?state=open&per_page=100" --jq '.[] | [(.head.repo.full_name // ""),(.head.sha // "")] | @tsv'
if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate open pull requests; no history was deleted.' }
$openPrShas = @{}
foreach ($line in @($prLines)) {
    if ([string]::IsNullOrWhiteSpace([string]$line)) { continue }
    $parts = ([string]$line).Split([char]9, 2)
    if ($parts.Count -eq 2 -and $parts[0] -eq $repository -and $parts[1]) {
        $openPrShas[$parts[1]] = $true
    }
}

$keepIds = @{}
if ($currentRunId) { $keepIds[$currentRunId] = $true }
# Preserve the canonical 1.1.1 reference build from the existing release workflow.
$keepIds['39933305387'] = $true

$completedRuns = @($allRuns | Where-Object { $_.status -eq 'completed' })
$groups = @($completedRuns | Group-Object -Property name)
foreach ($group in $groups) {
    $sorted = @($group.Group | Sort-Object -Property created_at -Descending)
    $isCurrentWorkflow = ($group.Name -eq $currentWorkflowName)

    # The Windows build invokes this script after its validated artifacts were uploaded.
    # Retain that current build instead of an older success from the same workflow.
    # Standalone/daily cleanup retains one latest successful run for each workflow.
    if (-not ($isCurrentWorkflow -and $pruneCurrentWorkflowToCurrent)) {
        $latestSuccess = $sorted | Where-Object { $_.conclusion -eq 'success' } | Select-Object -First 1
        if ($latestSuccess) { $keepIds[[string]$latestSuccess.id] = $true }
    }

    # For each open PR, keep only the newest run for that head SHA and workflow.
    foreach ($sha in @($openPrShas.Keys)) {
        $prRun = $sorted | Where-Object { $_.head_sha -eq $sha } | Select-Object -First 1
        if ($prRun) { $keepIds[[string]$prRun.id] = $true }
    }
}

$toDelete = @($completedRuns | Where-Object { -not $keepIds.ContainsKey([string]$_.id) })
Write-Host ("Completed runs found: {0}; protected runs: {1}; prune candidates: {2}." -f $completedRuns.Count, $keepIds.Count, $toDelete.Count)
$deleted = 0
foreach ($run in $toDelete) {
    Write-Host ("Deleting run {0} | {1} | {2} | {3} | {4}" -f $run.id, $run.name, $run.conclusion, $run.head_branch, $run.created_at)
    gh api --method DELETE -H 'Accept: application/vnd.github+json' "/repos/$repository/actions/runs/$($run.id)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "GitHub refused to delete workflow run $($run.id). Earlier successful deletions are retained." }
    $deleted++
}
Write-Host "Actions storage cleanup complete. Deleted $deleted completed workflow run(s), including their logs and any attached artifacts."
