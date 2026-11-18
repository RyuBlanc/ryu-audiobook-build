[CmdletBinding()]
param(
    [ValidateSet('PC-A', 'PC-B', 'CI')]
    [string]$Role = 'CI',
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [string]$ApplicationExePath,
    [string]$InstallerExePath,
    [string]$CoreInstallerExePath,
    [string]$PortableArchivePath,
    [string]$BundlePath,
    [string[]]$ProfileAssetPaths = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:CaptureErrors = New-Object 'System.Collections.Generic.List[string]'
$script:CaptureWarnings = New-Object 'System.Collections.Generic.List[string]'

$baseline = [ordered]@{
    build_number = 3470
    source_commit = 'fc3a0f8e1d64790b1a61024f8d883653b2dad51c'
    application_exe_sha256 = '29e733e73c1d19b21aa89e512fd4b7ff5f7160b2d492b791c224d0ebdbee699c'
    html_installer_exe_sha256 = 'd759411795704cbbc69539616c81797b23bd5313e80b5474a13461bd053f5512'
    core_installer_exe_sha256 = '0af7f21d1d379ed65e7d9aa166e2ccbb72c85aa85ecfec136bb5369f5dd77110'
}

function Get-FileEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$Kind,
        [Parameter(Mandatory = $true)][string]$CandidatePath,
        [string]$ExpectedSha256
    )
    $record = [ordered]@{
        kind = $Kind
        supplied = $true
        exists = $false
        size_bytes = $null
        sha256 = $null
        expected_sha256 = $ExpectedSha256
        matches_expected = $null
        status = 'not_found'
        error_type = $null
    }
    try {
        if (-not (Test-Path -LiteralPath $CandidatePath -PathType Leaf)) {
            $script:CaptureErrors.Add("$Kind was supplied but the file could not be found.")
            return [pscustomobject]$record
        }
        $item = Get-Item -LiteralPath $CandidatePath -ErrorAction Stop
        $stream = $null
        $sha256 = $null
        try {
            $stream = [System.IO.File]::OpenRead($item.FullName)
            $sha256 = [System.Security.Cryptography.SHA256]::Create()
            $digest = $sha256.ComputeHash($stream)
            $hash = ([System.BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
        } finally {
            if ($null -ne $stream) {
                $stream.Dispose()
            }
            if ($null -ne $sha256) {
                $sha256.Dispose()
            }
        }
        $record['exists'] = $true
        $record['size_bytes'] = [long]$item.Length
        $record['sha256'] = $hash
        $record['status'] = 'hashed'
        if (-not [string]::IsNullOrWhiteSpace($ExpectedSha256)) {
            $record['matches_expected'] = ($hash -eq $ExpectedSha256.ToLowerInvariant())
            if ($record.matches_expected) {
                $record['status'] = 'hash_match'
            } else {
                $record['status'] = 'hash_mismatch'
                $script:CaptureErrors.Add("$Kind does not match the pinned Build #3470 SHA-256.")
            }
        }
    } catch {
        $record['status'] = 'read_error'
        $record['error_type'] = $_.Exception.GetType().FullName
        $script:CaptureErrors.Add("$Kind could not be read ($($_.Exception.GetType().FullName)).")
    }
    return [pscustomobject]$record
}

function Get-CimRows {
    param([Parameter(Mandatory = $true)][string]$ClassName)
    try {
        return @(Get-CimInstance -ClassName $ClassName -ErrorAction Stop)
    } catch {
        $script:CaptureWarnings.Add("$ClassName metadata is unavailable.")
        return @()
    }
}

$osRows = @(Get-CimRows -ClassName 'Win32_OperatingSystem')
$osInfo = $null
if ($osRows.Count -gt 0) {
    $os = $osRows[0]
    $osInfo = [ordered]@{
        caption = [string]$os.Caption
        version = [string]$os.Version
        build_number = [string]$os.BuildNumber
        architecture = [string]$os.OSArchitecture
    }
}

$cpuInfo = @(
    foreach ($cpu in (Get-CimRows -ClassName 'Win32_Processor')) {
        [ordered]@{
            model = [string]$cpu.Name
            physical_cores = $cpu.NumberOfCores
            logical_processors = $cpu.NumberOfLogicalProcessors
        }
    }
)
$gpuInfo = @(
    foreach ($gpu in (Get-CimRows -ClassName 'Win32_VideoController')) {
        [ordered]@{
            model = [string]$gpu.Name
            driver_version = [string]$gpu.DriverVersion
            os_reported_adapter_ram_bytes = $gpu.AdapterRAM
            current_mode = [string]$gpu.VideoModeDescription
        }
    }
)

$memoryGiB = $null
$computerRows = @(Get-CimRows -ClassName 'Win32_ComputerSystem')
if ($computerRows.Count -gt 0 -and $null -ne $computerRows[0].TotalPhysicalMemory) {
    $memoryGiB = [math]::Round(([double]$computerRows[0].TotalPhysicalMemory / 1GB), 2)
}

$systemDriveFreeGiB = $null
try {
    $driveId = [string]$env:SystemDrive
    if (-not [string]::IsNullOrWhiteSpace($driveId)) {
        $driveRows = @(Get-CimInstance -ClassName 'Win32_LogicalDisk' -Filter "DeviceID='$driveId'" -ErrorAction Stop)
        if ($driveRows.Count -gt 0 -and $null -ne $driveRows[0].FreeSpace) {
            $systemDriveFreeGiB = [math]::Round(([double]$driveRows[0].FreeSpace / 1GB), 2)
        }
    }
} catch {
    $script:CaptureWarnings.Add('System-volume free-space metadata is unavailable.')
}

$displayInfo = @()
$displayCaptureAvailable = $false
try {
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
    $displayInfo = @(
        foreach ($screen in [System.Windows.Forms.Screen]::AllScreens) {
            [ordered]@{
                width_px = [int]$screen.Bounds.Width
                height_px = [int]$screen.Bounds.Height
                primary = [bool]$screen.Primary
            }
        }
    )
    $displayCaptureAvailable = $true
} catch {
    $script:CaptureWarnings.Add('Display geometry could not be read in this session.')
}

$nvidiaSmiAvailable = $false
$nvidiaSmiSummary = @()
$nvidiaCommand = Get-Command -Name 'nvidia-smi' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($null -ne $nvidiaCommand) {
    $nvidiaSmiAvailable = $true
    try {
        $summaryText = (& $nvidiaCommand.Source --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($summaryText)) {
            $nvidiaSmiSummary = @($summaryText -split "\r?\n")
        } else {
            $script:CaptureWarnings.Add('nvidia-smi was present but did not return a usable summary.')
        }
    } catch {
        $script:CaptureWarnings.Add('nvidia-smi summary could not be collected.')
    }
}
$rocmSmiAvailable = ($null -ne (Get-Command -Name 'rocm-smi' -ErrorAction SilentlyContinue))
$xpuSmiAvailable = ($null -ne (Get-Command -Name 'xpu-smi' -ErrorAction SilentlyContinue))

$fileEvidence = New-Object 'System.Collections.Generic.List[object]'
if (-not [string]::IsNullOrWhiteSpace($ApplicationExePath)) {
    $fileEvidence.Add((Get-FileEvidence -Kind 'application_exe' -CandidatePath $ApplicationExePath -ExpectedSha256 $baseline.application_exe_sha256))
}
if (-not [string]::IsNullOrWhiteSpace($InstallerExePath)) {
    $fileEvidence.Add((Get-FileEvidence -Kind 'html_installer_exe' -CandidatePath $InstallerExePath -ExpectedSha256 $baseline.html_installer_exe_sha256))
}
if (-not [string]::IsNullOrWhiteSpace($CoreInstallerExePath)) {
    $fileEvidence.Add((Get-FileEvidence -Kind 'core_installer_exe' -CandidatePath $CoreInstallerExePath -ExpectedSha256 $baseline.core_installer_exe_sha256))
}
if (-not [string]::IsNullOrWhiteSpace($PortableArchivePath)) {
    $fileEvidence.Add((Get-FileEvidence -Kind 'portable_archive' -CandidatePath $PortableArchivePath))
}
if (-not [string]::IsNullOrWhiteSpace($BundlePath)) {
    $fileEvidence.Add((Get-FileEvidence -Kind 'voice_bundle' -CandidatePath $BundlePath))
}
foreach ($assetPath in $ProfileAssetPaths) {
    if (-not [string]::IsNullOrWhiteSpace($assetPath)) {
        $fileEvidence.Add((Get-FileEvidence -Kind 'profile_owned_audio_asset' -CandidatePath $assetPath))
    }
}

$report = [ordered]@{
    schema_version = 1
    capture_tool_version = '1.0.0'
    captured_utc = [datetime]::UtcNow.ToString('o')
    role = $Role
    accepted_application_baseline = $baseline
    hardware = [ordered]@{
        operating_system = $osInfo
        cpu = $cpuInfo
        installed_memory_gib = $memoryGiB
        gpus = $gpuInfo
        system_volume_free_gib = $systemDriveFreeGiB
        displays = [ordered]@{
            capture_available = $displayCaptureAvailable
            count = $displayInfo.Count
            geometry = $displayInfo
        }
        diagnostic_tools = [ordered]@{
            nvidia_smi_available = $nvidiaSmiAvailable
            nvidia_smi_summary = $nvidiaSmiSummary
            rocm_smi_available = $rocmSmiAvailable
            xpu_smi_available = $xpuSmiAvailable
        }
    }
    evidence_files = @($fileEvidence.ToArray())
    limitations = [ordered]@{
        hardware_discovery_is_inference_evidence = $false
        resolved_qwen_backend = 'NOT_CAPTURED_BY_THIS_TOOL'
        model_runtime_versions = 'Record from application/runtime diagnostics during the physical test.'
        audio_content_included = $false
        file_names_and_paths_included = $false
    }
    privacy = [ordered]@{
        machine_identity_included = $false
        user_account_names_included = $false
        serial_numbers_included = $false
        network_identifiers_included = $false
        absolute_paths_included = $false
        voice_audio_contents_included = $false
        only_file_sizes_and_sha256_for_supplied_files = $true
    }
    warnings = @($script:CaptureWarnings.ToArray())
    errors = @($script:CaptureErrors.ToArray())
    result = if ($script:CaptureErrors.Count -eq 0) { 'CAPTURED' } else { 'NEEDS_ATTENTION' }
}

try {
    $destination = [System.IO.Path]::GetFullPath($OutputPath)
    $parent = [System.IO.Path]::GetDirectoryName($destination)
    if (-not [string]::IsNullOrWhiteSpace($parent) -and -not (Test-Path -LiteralPath $parent -PathType Container)) {
        [void][System.IO.Directory]::CreateDirectory($parent)
    }
    $json = $report | ConvertTo-Json -Depth 9
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($destination, $json, $utf8NoBom)
} catch {
    Write-Error 'The Stage F evidence report could not be written.'
    exit 3
}

Write-Output 'Stage F environment evidence report written. The report excludes machine/user identifiers, file names, paths and audio contents.'
if ($script:CaptureErrors.Count -gt 0) {
    Write-Output 'One or more supplied evidence files require attention; inspect the report errors array.'
    exit 2
}
exit 0
