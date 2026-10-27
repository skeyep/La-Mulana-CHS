param(
    [ValidateSet('Check','Install','Restore')][string]$Action = 'Check',
    [string]$GameDir = '',
    [string]$PackageDir = $PSScriptRoot,
    [string]$UserConfigPath = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
$Utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $Utf8
$OutputEncoding = $Utf8

function Hash-File([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $hash.Dispose(); $stream.Dispose() }
}
function Check-GameProcess {
    $targetExe = [IO.Path]::GetFullPath((Join-Path $GameDir 'LaMulanaWin.exe'))
    foreach ($gameProcess in @(Get-Process -Name LaMulanaWin -ErrorAction SilentlyContinue)) {
        try { $processPath = $gameProcess.Path }
        catch { throw "Cannot determine running La-Mulana path (PID $($gameProcess.Id)); close it before changing files" }
        if ([string]::IsNullOrWhiteSpace($processPath)) { throw "Cannot determine running La-Mulana path (PID $($gameProcess.Id)); close it before changing files" }
        if ([IO.Path]::GetFullPath($processPath).Equals($targetExe, [StringComparison]::OrdinalIgnoreCase)) { throw 'Close La-Mulana in the selected game folder before changing files' }
    }
}
function Read-Json([string]$Path) {
    [IO.File]::ReadAllText($Path, $Utf8) | ConvertFrom-Json
}
function Check-Relative([string]$Relative) {
    if ([string]::IsNullOrWhiteSpace($Relative) -or $Relative.Contains('\') -or $Relative.Contains(':') -or
        $Relative.StartsWith('/') -or @($Relative.Split('/') | Where-Object { $_ -eq '..' -or $_ -eq '.' -or $_ -eq '' }).Count) {
        throw "Invalid relative path: $Relative"
    }
}
function Inside([string]$Root, [string]$Relative) {
    Check-Relative $Relative
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    $target = [IO.Path]::GetFullPath((Join-Path $Root $Relative))
    if (-not $target.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Path leaves selected directory' }
    # Child junctions/symlinks must not redirect a patch write outside the chosen root.
    $probe = $target
    while ($probe.Length -ge $prefix.Length) {
        if (Test-Path -LiteralPath $probe) {
            $item = Get-Item -LiteralPath $probe -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Reparse point below game root: $probe" }
        }
        $probe = [IO.Path]::GetDirectoryName($probe)
    }
    return $target
}
function Select-ChineseLanguage {
    # Match native FindFirstFile order: en/jp occupy 0/1, remaining directories append.
    $codes = New-Object 'Collections.Generic.List[string]'
    $codes.Add('en'); $codes.Add('jp')
    foreach ($directory in [IO.Directory]::EnumerateDirectories((Join-Path $GameDir 'data/language'))) {
        $code = [IO.Path]::GetFileName($directory)
        if ($code -ceq 'en' -or $code -ceq 'jp') { continue }
        if ($codes.Count -ge 8) { break }
        $codes.Add($code)
    }
    $index = $codes.IndexOf('chs')
    if ($index -lt 0) { throw 'CHS language directory is missing from the native language list' }
    $config = $UserConfigPath
    if ([string]::IsNullOrWhiteSpace($config)) {
        $config = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'NIGORO/La-Mulana/config.ini'
    }
    $config = [IO.Path]::GetFullPath($config)
    $text = if ([IO.File]::Exists($config)) { [IO.File]::ReadAllText($config, $Utf8) } else { '' }
    $pattern = '(?m)^Language=[^\r\n]*'
    $replacement = 'Language=' + $index
    if ([regex]::IsMatch($text, $pattern)) { $next = [regex]::Replace($text, $pattern, $replacement) }
    else {
        $newline = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
        $next = $text + $(if ($text.Length -gt 0 -and -not $text.EndsWith("`n")) { $newline } else { '' }) + $replacement + $newline
    }
    if ($next -ne $text) {
        $backup = Inside $StateDir 'config-before-chs.ini'
        if ([IO.File]::Exists($config) -and -not [IO.File]::Exists($backup)) { [IO.File]::Copy($config, $backup) }
        $null = [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($config))
        Write-AtomicBytes $config ($Utf8.GetBytes($next))
    }
    Write-Output ('PASS: startup language set to Simplified Chinese (chs, index ' + $index + ').')
}
function Save-State($State) { Write-AtomicJson $StateFile $State }
function Get-FileProfile($Files) {
    $exe = @($Files | Where-Object { $_.path -eq 'LaMulanaWin.exe' })
    if ($exe.Count -ne 1) { throw 'Missing/duplicate executable target' }
    $profileExe = $exe[0].sha256
    $assistant = $AssistantExeProfiles.ContainsKey($profileExe)
    if ($assistant) { $profileExe = $AssistantExeProfiles[$profileExe] }
    $profile = $null
    if ($profileExe -eq $FormalExe) {
        $profile = [PSCustomObject]@{Targets=@($Allowed);Baselines=@($AllowedBaselines)}
    }
    elseif ($profileExe -eq $SettingsLocaleExe -or $profileExe -eq $TitleFooterExe) {
        $profile = [PSCustomObject]@{Targets=@($Allowed + $TitleTargets);Baselines=@($AllowedBaselines + $TitleBaselineHashes.Keys)}
    }
    elseif ($profileExe -eq $TitleExe) {
        if (@($Files | Where-Object { $SettingsTargets -contains $_.path }).Count) {
            $profile = [PSCustomObject]@{Targets=@($Allowed + $TitleTargets + $SettingsTargets);Baselines=@($AllowedBaselines + $TitleBaselineHashes.Keys + $SettingsTargets)}
        } else {
            $profile = [PSCustomObject]@{Targets=@($Allowed + $TitleTargets);Baselines=@($AllowedBaselines + $TitleBaselineHashes.Keys)}
        }
    }
    if ($null -eq $profile) { throw 'Unsupported patch executable' }
    if (@($Files | Where-Object { $SharedGraphicsTargets -contains $_.path }).Count) {
        $profile.Targets = @($profile.Targets + $SharedGraphicsTargets)
        $profile.Baselines = @($profile.Baselines + $SharedGraphicsTargets)
    }
    if ($assistant) { $profile.Targets = @($profile.Targets + $AssistantTargets) }
    return $profile
}
function Check-Targets($Files) {
    $profile = Get-FileProfile $Files
    $seen = @{}
    foreach ($file in $Files) {
        Check-Relative $file.path
        if ($profile.Targets -notcontains $file.path -or $seen.ContainsKey($file.path)) { throw "Unexpected/duplicate target: $($file.path)" }
        if ($file.sha256 -notmatch '^[0-9a-f]{64}$' -or $file.bytes -lt 1) { throw 'Invalid file digest or size' }
        $expectedOperation = if ($file.path -eq 'LaMulanaWin.exe' -or $ReplacedResources -contains $file.path) { 'replace' } else { 'add' }
        if ($file.operation -ne $expectedOperation) { throw "Unexpected file operation: $($file.path)" }
        $seen[$file.path] = $true
    }
    if ($seen.Count -ne $profile.Targets.Count) { throw 'Incomplete patch file list' }
    return $profile
}
function Check-Package([bool]$Payloads = $true) {
    if ($Manifest.schema -ne 'lm1-chs-offline-package-v1' -or $Manifest.app_id -ne 230700) { throw 'Unsupported patch package' }
    if ($Manifest.original_exe_sha256 -ne $OriginalExe) { throw 'Unexpected supported game version' }
    if ($Manifest.package_id -notmatch '^[0-9a-f]{64}$') { throw 'Invalid package identity' }
    $profile = Check-Targets $Manifest.files
    $baselineSeen = @{}
    foreach ($file in $Manifest.baseline_files) {
        Check-Relative $file.path
        if ($profile.Baselines -notcontains $file.path -or $baselineSeen.ContainsKey($file.path)) { throw 'Unexpected/duplicate baseline path' }
        if ($file.sha256 -notmatch '^[0-9a-f]{64}$' -or $file.bytes -lt 1) { throw 'Invalid baseline digest or size' }
        if ($file.path -eq 'LaMulanaWin.exe' -and $file.sha256 -ne $OriginalExe) { throw 'Wrong executable baseline' }
        if ($TitleBaselineHashes.ContainsKey($file.path) -and $file.sha256 -ne $TitleBaselineHashes[$file.path]) { throw 'Wrong title resource baseline' }
        if ($ReplacedResources -contains $file.path) {
            $original = $ResourceOriginals[$file.path]
            if ($file.sha256 -ne $original.sha256 -or $file.bytes -ne $original.bytes) { throw "Wrong shared resource baseline: $($file.path)" }
        }
        $baselineSeen[$file.path] = $true
    }
    if ($baselineSeen.Count -ne $profile.Baselines.Count) { throw 'Incomplete baseline file list' }
    if (-not $Payloads) { return }
    foreach ($file in $Manifest.files) {
        if ($file.payload -ne ('payload/' + $file.sha256 + '.bin')) { throw 'Invalid payload path' }
        $path = Inside $PackageDir $file.payload
        if (-not [IO.File]::Exists($path) -or (Get-Item -LiteralPath $path).Length -ne $file.bytes -or (Hash-File $path) -ne $file.sha256) {
            throw "Damaged package payload: $($file.path)"
        }
    }
}
function Resource-Backup([string]$Relative) {
    if (-not $ResourceOriginals.ContainsKey($Relative)) { throw 'Unsupported replaced resource' }
    return Inside $StateDir $ResourceOriginals[$Relative].backup
}
function Check-ResourceBackup([string]$Relative) {
    $backup = Resource-Backup $Relative
    $original = $ResourceOriginals[$Relative]
    if (-not [IO.File]::Exists($backup) -or (Get-Item -LiteralPath $backup).Length -ne $original.bytes -or (Hash-File $backup) -ne $original.sha256) { throw "Original resource backup missing or changed: $Relative" }
}
function Save-ResourceBackups($Files) {
    foreach ($file in $Files) {
        if ($ReplacedResources -notcontains $file.path) { continue }
        $backup = Resource-Backup $file.path
        if (-not [IO.File]::Exists($backup)) { Copy-Atomic (Inside $GameDir $file.path) $backup $ResourceOriginals[$file.path].sha256 }
        Check-ResourceBackup $file.path
    }
}
function Check-ModCompatibility {
    # EX Map Port overwrites bank00 and shared map/script data; it has no selectable bank01.
    $anchors = @(
        @('data/mapdata/map00.msd', '3829c4a6718c87da9da20eaccb9c8a8397bf6168e49f3aeaef489b7c81dc684e'),
        @('data/mapdata/script.rcd', 'd09c6e2e6357843080f24040d53a9611b4cfc6366ee78a20c19318a4ae369616')
    )
    foreach ($anchor in $anchors) {
        $path = Inside $GameDir $anchor[0]
        if ([IO.File]::Exists($path) -and (Hash-File $path) -eq $anchor[1]) {
            $instructions = @'
This patch does not support La-Mulana EX Map Port. It replaces the original maps and scripts and cannot be switched off in the graphics settings.
To install this translation, prepare an unmodified Steam game:
1. Close the game. Keep your EX game folder and back up the entire Documents\NIGORO\La-Mulana save and settings folder.
2. Use a full backup made before installing the MOD, or move the EX game folder out of its Steam location and use Steam > Properties > Installed Files > Verify integrity of game files to restore the original files. Verifying the existing folder alone leaves MOD-added files behind.
3. Run Install.cmd to install into the restored original game folder. Keep EX saves separately for your EX copy; start a new game on the restored original maps.
Installation/check stopped. No translation files were written to the game folder.
'@
            throw ($instructions + "`r`nDetected file: " + $anchor[0])
        }
    }
    $graphics = Inside $GameDir 'data/graphics'
    if ([IO.Directory]::Exists($graphics)) {
        $extra = @([IO.Directory]::GetDirectories($graphics) | Where-Object { [IO.Path]::GetFileName($_) -ne '00' -and [IO.File]::Exists((Join-Path $_ '_banner.png')) })
        if ($extra.Count -gt 0) {
            Write-Warning 'An additional graphics pack was detected. This translation supports the original graphics pack. Image text in other graphics packs may remain untranslated. Extra pack files will be kept.'
        }
    }
}
function Check-Baseline([bool]$Installed, $OwnedFiles = @()) {
    foreach ($file in $Manifest.baseline_files) {
        if ($Installed -and $file.path -eq 'LaMulanaWin.exe') { continue }
        if ($Installed -and $ReplacedResources -contains $file.path -and @($OwnedFiles | Where-Object { $_.path -eq $file.path }).Count) {
            Check-ResourceBackup $file.path
            continue
        }
        $path = Inside $GameDir $file.path
        if (-not [IO.File]::Exists($path) -or (Hash-File $path) -ne $file.sha256) { throw "Game version/source differs: $($file.path)" }
    }
}
function Check-State($State) {
    if ($State.schema -ne 'lm1-chs-install-state-v1' -or $State.original_exe_sha256 -ne $OriginalExe) { throw 'Invalid installation receipt' }
    if ($State.status -notin @('installing','installed','restored')) { throw 'Unknown installation state' }
    if ($State.package_id -notmatch '^[0-9a-f]{64}$') { throw 'Invalid receipt package identity' }
    if ($State.stage -notmatch '^stage-[0-9a-f]{32}$') { throw 'Invalid staging directory' }
    $null = Check-Targets $State.files
    foreach ($file in $State.files) { if ($ReplacedResources -contains $file.path) { Check-ResourceBackup $file.path } }
    foreach ($directory in $State.created_directories) {
        if ($AllowedDirectories -notcontains $directory) { throw 'Unexpected created directory in receipt' }
        $null = Inside $GameDir $directory
    }
    $backup = Inside $StateDir 'original-LaMulanaWin.exe'
    if (-not [IO.File]::Exists($backup) -or (Hash-File $backup) -ne $OriginalExe) { throw 'Original executable backup missing or changed' }
    $stage = Inside $StateDir $State.stage
    if ((Test-Path -LiteralPath $stage) -and -not [IO.Directory]::Exists($stage)) { throw 'Staging directory was replaced by a file' }
    for ($i = 0; $i -lt $State.files.Count; $i++) {
        $temp = Inside $stage ('{0:D3}.bin' -f $i)
        if ((Test-Path -LiteralPath $temp) -and -not [IO.File]::Exists($temp)) { throw 'Staging file was replaced by a directory' }
    }
    $null = Inside $StateDir 'restore-exe.tmp'
}
function Check-Installed($State) {
    foreach ($file in $State.files) {
        $path = Inside $GameDir $file.path
        if (-not [IO.File]::Exists($path) -or (Get-Item -LiteralPath $path).Length -ne $file.bytes -or (Hash-File $path) -ne $file.sha256) { throw "Installed patch file changed: $($file.path)" }
    }
}
function Remove-Owned-Stage($State) {
    $stage = Inside $StateDir $State.stage
    for ($i = 0; $i -lt $State.files.Count; $i++) {
        $temp = Inside $stage ('{0:D3}.bin' -f $i)
        if ([IO.File]::Exists($temp)) { [IO.File]::Delete($temp) }
    }
    if ([IO.Directory]::Exists($stage) -and [IO.Directory]::GetFileSystemEntries($stage).Length -eq 0) { [IO.Directory]::Delete($stage, $false) }
}
function Restore-Owned($State) {
    Check-State $State
    # Validate every target before the first restore/delete; retain user-modified files.
    foreach ($file in $State.files) {
        $path = Inside $GameDir $file.path
        if ((Test-Path -LiteralPath $path) -and -not [IO.File]::Exists($path)) { throw "Installed file was replaced by a directory: $($file.path)" }
        if ([IO.File]::Exists($path)) {
            $hash = Hash-File $path
            $isOriginal = ($file.path -eq 'LaMulanaWin.exe' -and $hash -eq $OriginalExe) -or ($ReplacedResources -contains $file.path -and $hash -eq $ResourceOriginals[$file.path].sha256)
            if ($hash -ne $file.sha256 -and -not $isOriginal) {
                throw "File changed after installation; preserve your changes before restoring: $($file.path)"
            }
        }
    }
    $backup = Inside $StateDir 'original-LaMulanaWin.exe'
    $exe = Inside $GameDir 'LaMulanaWin.exe'
    $restoreTemp = Inside $StateDir 'restore-exe.tmp'
    [IO.File]::Copy($backup, $restoreTemp, $true)
    if ([IO.File]::Exists($exe)) { [IO.File]::Replace($restoreTemp, $exe, [NullString]::Value) }
    else { [IO.File]::Move($restoreTemp, $exe) }
    foreach ($file in $State.files) {
        if ($file.path -eq 'LaMulanaWin.exe') { continue }
        $path = Inside $GameDir $file.path
        if ($ReplacedResources -contains $file.path) {
            Copy-Atomic (Resource-Backup $file.path) $path $ResourceOriginals[$file.path].sha256
            continue
        }
        if ([IO.File]::Exists($path)) { [IO.File]::Delete($path) }
    }
    foreach ($relative in @($State.created_directories | Sort-Object { $_.Length } -Descending)) {
        $directory = Inside $GameDir $relative
        if ([IO.Directory]::Exists($directory) -and [IO.Directory]::GetFileSystemEntries($directory).Length -eq 0) {
            [IO.Directory]::Delete($directory, $false)
        }
    }
    if ((Hash-File $exe) -ne $OriginalExe) { throw 'Restored executable hash mismatch' }
    Remove-Owned-Stage $State
    $State.status = 'restored'
    Save-State $State
}

# This fragment is embedded into Patch.ps1; the installed recovery script is self-contained.
function Write-AtomicBytes([string]$Path, [byte[]]$Bytes) {
    $temp = Join-Path ([IO.Path]::GetDirectoryName($Path)) ('write-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        $stream = New-Object IO.FileStream($temp, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $stream.Write($Bytes, 0, $Bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
        # Replace can briefly be denied a delete-sharing handle (Win32 32/33/1175).
        # Retry the same fully flushed temp, never delete/copy over the destination.
        $delays = @(40,80,120,180,260,360,500)
        $presenceCaptured = $false; $digestCaptured = $false
        $expectedPresent = $false; $expectedDigest = $null
        for ($attempt = 0; $attempt -le $delays.Count; $attempt++) {
            try {
                $present = [IO.File]::Exists($Path)
                if (-not $presenceCaptured) { $expectedPresent = $present; $presenceCaptured = $true }
                elseif ($present -ne $expectedPresent) { throw 'Atomic target presence changed while waiting for a file lock' }
                if ($present) {
                    $digest = Hash-File $Path
                    if (-not $digestCaptured) { $expectedDigest = $digest; $digestCaptured = $true }
                    elseif ($digest -ne $expectedDigest) { throw 'Atomic target bytes changed while waiting for a file lock' }
                    [IO.File]::Replace($temp, $Path, [NullString]::Value)
                } else { [IO.File]::Move($temp, $Path) }
                return
            } catch {
                $cause = $_.Exception
                while ($null -ne $cause.InnerException) { $cause = $cause.InnerException }
                $code = $cause.HResult -band 0xffff
                if ($cause -isnot [IO.IOException] -or $code -notin @(32,33,1175) -or $attempt -ge $delays.Count -or -not [IO.File]::Exists($temp)) { throw }
                Write-Verbose ("Atomic file lock retry {0}/{1}; error {2}; {3}" -f ($attempt + 1),$delays.Count,$code,$Path)
                [Threading.Thread]::Sleep($delays[$attempt])
            }
        }
    } catch {
        $cause = $_.Exception
        while ($null -ne $cause.InnerException) { $cause = $cause.InnerException }
        throw "Atomic write failed for ${Path}: $($_.Exception.Message) (HResult=$($cause.HResult); code=$($cause.HResult -band 0xffff))"
    }
    finally { if ([IO.File]::Exists($temp)) { [IO.File]::Delete($temp) } }
}
function Write-AtomicJson([string]$Path, $Value) {
    Write-AtomicBytes $Path ($Utf8.GetBytes(($Value | ConvertTo-Json -Depth 40)))
}
function Copy-Atomic([string]$Source, [string]$Target, [string]$Expected) {
    if ((Hash-File $Source) -ne $Expected) { throw 'Snapshot source hash differs' }
    Write-AtomicBytes $Target ([IO.File]::ReadAllBytes($Source))
    if ((Hash-File $Target) -ne $Expected) { throw 'Atomic copy verification failed' }
}
function File-Signature($Files) {
    return ((@($Files | Sort-Object path | ForEach-Object { "$($_.path)|$($_.sha256)|$($_.bytes)" })) -join "`n")
}
function Check-SnapshotFile([string]$Path, $File) {
    if (-not [IO.File]::Exists($Path) -or (Get-Item -LiteralPath $Path).Length -ne $File.bytes -or (Hash-File $Path) -ne $File.sha256) {
        throw "Snapshot is missing or changed: $Path"
    }
}
function Check-ManifestDefinition($Definition) {
    $saved = $script:Manifest
    try { $script:Manifest = $Definition; Check-Package $false }
    finally { $script:Manifest = $saved }
}
function Get-UpgradeOperations($OldFiles, $NewFiles) {
    $old = @{}; $new = @{}
    for ($i = 0; $i -lt $OldFiles.Count; $i++) { $old[$OldFiles[$i].path] = $i }
    for ($i = 0; $i -lt $NewFiles.Count; $i++) { $new[$NewFiles[$i].path] = $i }
    $paths = @($NewFiles | ForEach-Object { $_.path }) + @($OldFiles | Where-Object { -not $new.ContainsKey($_.path) } | ForEach-Object { $_.path })
    foreach ($relative in $paths) {
        $oi = -1; $ni = -1
        if ($old.ContainsKey($relative)) { $oi = $old[$relative] }
        if ($new.ContainsKey($relative)) { $ni = $new[$relative] }
        $kind = 'replace'
        if ($oi -lt 0) { $kind = 'add' }
        elseif ($ni -lt 0) { $kind = 'remove' }
        elseif ($OldFiles[$oi].sha256 -eq $NewFiles[$ni].sha256 -and $OldFiles[$oi].bytes -eq $NewFiles[$ni].bytes) { $kind = 'keep' }
        [PSCustomObject]@{path=$relative;old_index=$oi;new_index=$ni;kind=$kind}
    }
}
function Get-PreviousFiles($State, $NewFiles) {
    $files = @($State.files)
    if ($State.status -ne 'installed') {
        $files = @([PSCustomObject]@{path='LaMulanaWin.exe';sha256=$OriginalExe;bytes=(Get-Item -LiteralPath (Inside $StateDir 'original-LaMulanaWin.exe')).Length;operation='replace'})
    }
    foreach ($file in $NewFiles) {
        if ($ReplacedResources -contains $file.path -and @($files | Where-Object { $_.path -eq $file.path }).Count -eq 0) {
            $original = $ResourceOriginals[$file.path]
            $files += [PSCustomObject]@{path=$file.path;sha256=$original.sha256;bytes=$original.bytes;operation='replace'}
        }
    }
    return $files
}
function Get-TargetHash([string]$Relative) {
    $path = Inside $GameDir $Relative
    if ((Test-Path -LiteralPath $path) -and -not [IO.File]::Exists($path)) { throw "Target is not a regular file: $Relative" }
    if ([IO.File]::Exists($path)) { return Hash-File $path }
    return $null
}
function Check-UpgradeTargets($Tx) {
    for ($i = 0; $i -lt $Tx.Operations.Count; $i++) {
        $op = $Tx.Operations[$i]; $actual = Get-TargetHash $op.path; $allowed = @()
        if ($op.old_index -ge 0) { $allowed += $Tx.Plan.old_files[$op.old_index].sha256 } else { $allowed += $null }
        if ($i -le $Tx.Journal.intent_index) {
            if ($op.new_index -ge 0) { $allowed += $Tx.Plan.new_files[$op.new_index].sha256 }
            elseif ($ReplacedResources -contains $op.path) { $allowed += $ResourceOriginals[$op.path].sha256 }
            else { $allowed += $null }
        }
        if ($allowed -notcontains $actual) { throw "File changed outside this transaction: $($op.path)" }
    }
}
function Save-UpgradeJournal($Tx) { Write-AtomicJson $JournalFile $Tx.Journal }
function Check-EngineFiles {
    $engine = Inside $StateDir 'Restore.ps1'; $cmd = Inside $StateDir 'Restore.cmd'; $record = Inside $StateDir 'engine.json'
    $scriptHashes = @($LegacyInstallerHashes) + @((Hash-File $PSCommandPath))
    $cmdHashes = @(
        '3392e579b344159b3f6d97d31064fce5f43b740510ed7a8be351623fd910aabd'
        '2cb1c2f54d0d7527b2618cb35eb457c73ef1189a883c6110ad558cbb742964b2'
        (Hash-Bytes ($Utf8.GetBytes($LegacyRestoreCommand)))
        (Hash-Bytes ($Utf8.GetBytes($RestoreCommand)))
    )
    if ([IO.File]::Exists($record)) {
        $known = Read-Json $record
        if ($known.schema -ne 'lm1-chs-recovery-engine-v1' -or $known.script_sha256 -notmatch '^[0-9a-f]{64}$' -or $known.command_sha256 -notmatch '^[0-9a-f]{64}$') { throw 'Invalid recovery-engine receipt' }
        $scriptHashes += $known.script_sha256; $cmdHashes += $known.command_sha256
    }
    if ([IO.File]::Exists($engine) -and $scriptHashes -notcontains (Hash-File $engine)) { throw 'Saved recovery script was modified; preserve it before upgrading' }
    if ([IO.File]::Exists($cmd) -and $cmdHashes -notcontains (Hash-File $cmd)) { throw 'Saved recovery command was modified; preserve it before upgrading' }
}
function Hash-Bytes([byte[]]$Bytes) {
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($hash.ComputeHash($Bytes)).Replace('-', '').ToLowerInvariant() } finally { $hash.Dispose() }
}
function Save-RecoveryEngine {
    $scriptHash = Hash-File $PSCommandPath
    $engine = Inside $StateDir 'Restore.ps1'
    if ([IO.Path]::GetFullPath($PSCommandPath) -ne $engine -and (-not [IO.File]::Exists($engine) -or (Hash-File $engine) -ne $scriptHash)) { Copy-Atomic $PSCommandPath $engine $scriptHash }
    Write-AtomicBytes (Inside $StateDir 'Restore.cmd') ($Utf8.GetBytes($RestoreCommand))
    Write-AtomicJson (Inside $StateDir 'engine.json') ([PSCustomObject]@{schema='lm1-chs-recovery-engine-v1';script_sha256=$scriptHash;command_sha256=(Hash-Bytes ($Utf8.GetBytes($RestoreCommand)))})
}
function Read-UpgradeTransaction {
    $journal = Read-Json $JournalFile
    if ($journal.schema -ne 'lm1-chs-upgrade-journal-v1' -or $journal.id -notmatch '^[0-9a-f]{32}$' -or $journal.plan_sha256 -notmatch '^[0-9a-f]{64}$') { throw 'Invalid upgrade journal' }
    if ($journal.phase -notin @('prepared','applying','rolling-back','committing','committed','rolled-back')) { throw 'Invalid upgrade phase' }
    $work = Inside $StateDir ('upgrades/upgrade-' + $journal.id)
    $planPath = Inside $work 'plan.json'
    if ((Hash-File $planPath) -ne $journal.plan_sha256) { throw 'Upgrade plan changed' }
    $plan = Read-Json $planPath
    if ($plan.schema -ne 'lm1-chs-upgrade-plan-v1' -or $plan.id -ne $journal.id -or $plan.from_kind -notin @('installed','original')) { throw 'Invalid upgrade plan identity' }
    foreach ($name in @('previous-state','next-state','manifest')) {
        $field = $name.Replace('-', '_') + '_sha256'
        if ($plan.$field -notmatch '^[0-9a-f]{64}$' -or (Hash-File (Inside $work ($name + '.json'))) -ne $plan.$field) { throw "Upgrade metadata changed: $name" }
    }
    $previous = Read-Json (Inside $work 'previous-state.json'); Check-State $previous
    $next = Read-Json (Inside $work 'next-state.json'); Check-State $next
    $definition = Read-Json (Inside $work 'manifest.json'); Check-ManifestDefinition $definition
    if ($previous.package_id -ne $plan.from_package_id -or $next.package_id -ne $plan.to_package_id -or $definition.package_id -ne $plan.to_package_id -or
        (File-Signature $next.files) -ne (File-Signature $plan.new_files) -or (File-Signature $definition.files) -ne (File-Signature $plan.new_files)) { throw 'Upgrade receipt/manifest relationship differs' }
    if ($next.status -ne 'installed') { throw 'Invalid next installation state' }
    if ($plan.from_kind -eq 'installed') {
        if ($previous.status -ne 'installed') { throw 'Invalid previous installed profile' }
    } else {
        if ($previous.status -ne 'restored') { throw 'Invalid previous original profile' }
    }
    if ((File-Signature @(Get-PreviousFiles $previous $plan.new_files)) -ne (File-Signature $plan.old_files)) { throw 'Invalid previous transaction file set' }
    foreach ($relative in $plan.created_directories) {
        if ($AllowedDirectories -notcontains $relative) { throw 'Unexpected transaction directory' }
        $null = Inside $GameDir $relative
    }
    $operations = @(Get-UpgradeOperations $plan.old_files $plan.new_files)
    if ($journal.intent_index -lt -1 -or $journal.intent_index -ge $operations.Count -or $journal.completed_count -lt 0 -or $journal.completed_count -gt $operations.Count) { throw 'Invalid upgrade cursor' }
    for ($i = 0; $i -lt $plan.old_files.Count; $i++) { Check-SnapshotFile (Inside $work ('previous/{0:D3}.bin' -f $i)) $plan.old_files[$i] }
    $receiptHash = Hash-File $StateFile
    if ($receiptHash -ne $plan.previous_state_sha256 -and $receiptHash -ne $plan.next_state_sha256) { throw 'Installation receipt changed during upgrade' }
    return [PSCustomObject]@{Journal=$journal;Plan=$plan;Work=$work;Previous=$previous;Next=$next;Manifest=$definition;Operations=$operations}
}
function Check-UpgradePayloads($Tx) {
    for ($i = 0; $i -lt $Tx.Plan.new_files.Count; $i++) { Check-SnapshotFile (Inside $Tx.Work ('next/{0:D3}.bin' -f $i)) $Tx.Plan.new_files[$i] }
}
function Start-UpgradeTransaction($State) {
    $installed = $State.status -eq 'installed'
    Check-Baseline $installed $State.files
    if ($installed) { Check-Installed $State }
    Save-ResourceBackups $Manifest.files
    $oldFiles = @(Get-PreviousFiles $State $Manifest.files)
    $oldPaths = @($oldFiles | ForEach-Object { $_.path })
    foreach ($file in $Manifest.files) {
        if ($oldPaths -notcontains $file.path -and (Test-Path -LiteralPath (Inside $GameDir $file.path))) { throw "Unowned new target exists: $($file.path)" }
    }
    Check-EngineFiles
    $id = [Guid]::NewGuid().ToString('N'); $work = Inside $StateDir ('upgrades/upgrade-' + $id)
    $created = @($AllowedDirectories | Where-Object { -not [IO.Directory]::Exists((Inside $GameDir $_)) })
    $null = [IO.Directory]::CreateDirectory((Inside $work 'previous'))
    $null = [IO.Directory]::CreateDirectory((Inside $work 'next'))
    [IO.File]::Copy($StateFile, (Inside $work 'previous-state.json'))
    [IO.File]::Copy((Inside $PackageDir 'manifest.json'), (Inside $work 'manifest.json'))
    for ($i = 0; $i -lt $oldFiles.Count; $i++) {
        $path = Inside $work ('previous/{0:D3}.bin' -f $i)
        [IO.File]::Copy((Inside $GameDir $oldFiles[$i].path), $path); Check-SnapshotFile $path $oldFiles[$i]
    }
    for ($i = 0; $i -lt $Manifest.files.Count; $i++) {
        $path = Inside $work ('next/{0:D3}.bin' -f $i)
        [IO.File]::Copy((Inside $PackageDir $Manifest.files[$i].payload), $path); Check-SnapshotFile $path $Manifest.files[$i]
    }
    foreach ($name in @('Restore.ps1','Restore.cmd','engine.json')) {
        $source = Inside $StateDir $name
        if ([IO.File]::Exists($source)) { [IO.File]::Copy($source, (Inside $work ('previous-' + $name))) }
    }
    $directories = @(@($State.created_directories) + $created | Select-Object -Unique)
    $next = [PSCustomObject]@{schema='lm1-chs-install-state-v1';status='installed';package_id=$Manifest.package_id;original_exe_sha256=$OriginalExe;
        files=@($Manifest.files);created_directories=$directories;stage=('stage-' + $id);previous_backup=('upgrades/upgrade-' + $id)}
    Write-AtomicJson (Inside $work 'next-state.json') $next
    $plan = [PSCustomObject]@{schema='lm1-chs-upgrade-plan-v1';id=$id;from_kind=$(if($installed){'installed'}else{'original'});
        from_package_id=$State.package_id;to_package_id=$Manifest.package_id;old_files=$oldFiles;new_files=@($Manifest.files);created_directories=$created;
        previous_state_sha256=(Hash-File (Inside $work 'previous-state.json'));next_state_sha256=(Hash-File (Inside $work 'next-state.json'));
        manifest_sha256=(Hash-File (Inside $work 'manifest.json'))}
    Write-AtomicJson (Inside $work 'plan.json') $plan
    # The pending journal is published only after a standalone recovery engine exists.
    Save-RecoveryEngine
    $journal = [PSCustomObject]@{schema='lm1-chs-upgrade-journal-v1';id=$id;plan_sha256=(Hash-File (Inside $work 'plan.json'));
        phase='prepared';intent_index=-1;completed_count=0;rollback_completed_count=0}
    Write-AtomicJson $JournalFile $journal
    return Read-UpgradeTransaction
}
function Apply-UpgradeOperation($Tx, $Op) {
    $actual = Get-TargetHash $Op.path; $target = Inside $GameDir $Op.path
    if ($Op.new_index -lt 0) {
        if ($ReplacedResources -contains $Op.path) {
            $original = $ResourceOriginals[$Op.path]
            if ($actual -eq $original.sha256) { return $false }
            if ($actual -ne $Tx.Plan.old_files[$Op.old_index].sha256) { throw "Owned obsolete resource changed: $($Op.path)" }
            Copy-Atomic (Resource-Backup $Op.path) $target $original.sha256
            return $true
        }
        if ($null -eq $actual) { return $false }
        if ($actual -ne $Tx.Plan.old_files[$Op.old_index].sha256) { throw "Owned obsolete file changed: $($Op.path)" }
        [IO.File]::Delete($target); return $true
    }
    $wanted = $Tx.Plan.new_files[$Op.new_index]
    if ($actual -eq $wanted.sha256) { return $false }
    if (($Op.old_index -ge 0 -and $actual -ne $Tx.Plan.old_files[$Op.old_index].sha256) -or ($Op.old_index -lt 0 -and $null -ne $actual)) { throw "Target changed before replacement: $($Op.path)" }
    Copy-Atomic (Inside $Tx.Work ('next/{0:D3}.bin' -f $Op.new_index)) $target $wanted.sha256
    return $true
}
function Rollback-UpgradeOperation($Tx, $Op) {
    $actual = Get-TargetHash $Op.path; $target = Inside $GameDir $Op.path
    if ($Op.old_index -lt 0) {
        if ($null -eq $actual) { return $false }
        if ($actual -ne $Tx.Plan.new_files[$Op.new_index].sha256) { throw "New transaction file changed: $($Op.path)" }
        [IO.File]::Delete($target); return $true
    }
    $wanted = $Tx.Plan.old_files[$Op.old_index]
    if ($actual -eq $wanted.sha256) { return $false }
    $removedExpected = if ($ReplacedResources -contains $Op.path) { $ResourceOriginals[$Op.path].sha256 } else { $null }
    if (($Op.new_index -ge 0 -and $actual -ne $Tx.Plan.new_files[$Op.new_index].sha256) -or ($Op.new_index -lt 0 -and $removedExpected -ne $actual)) { throw "Target changed before rollback: $($Op.path)" }
    Copy-Atomic (Inside $Tx.Work ('previous/{0:D3}.bin' -f $Op.old_index)) $target $wanted.sha256
    return $true
}
function Complete-UpgradeJournal($Tx) {
    Write-AtomicJson (Inside $Tx.Work 'result.json') $Tx.Journal
    [IO.File]::Delete($JournalFile)
}
function Rollback-Upgrade($Tx) {
    Check-UpgradeTargets $Tx
    $Tx.Journal.phase = 'rolling-back'; Save-UpgradeJournal $Tx
    for ($i = $Tx.Operations.Count - 1; $i -ge 0; $i--) {
        $changed = Rollback-UpgradeOperation $Tx $Tx.Operations[$i]
        # TEST-BOUNDARY: rollback-operation-complete, before rollback cursor save.
        $Tx.Journal.rollback_completed_count = $Tx.Operations.Count - $i; Save-UpgradeJournal $Tx
    }
    Copy-Atomic (Inside $Tx.Work 'previous-state.json') $StateFile $Tx.Plan.previous_state_sha256
    foreach ($relative in @($Tx.Plan.created_directories | Sort-Object { $_.Length } -Descending)) {
        $directory = Inside $GameDir $relative
        if ([IO.Directory]::Exists($directory) -and [IO.Directory]::GetFileSystemEntries($directory).Length -eq 0) { [IO.Directory]::Delete($directory, $false) }
    }
    if ($Tx.Plan.from_kind -eq 'installed') { Check-Installed $Tx.Previous }
    elseif ((Hash-File (Inside $GameDir 'LaMulanaWin.exe')) -ne $OriginalExe) { throw 'Original rollback hash mismatch' }
    $Tx.Journal.phase = 'rolled-back'; Save-UpgradeJournal $Tx
    Complete-UpgradeJournal $Tx
}
function Commit-Upgrade($Tx) {
    Check-Installed $Tx.Next
    foreach ($op in $Tx.Operations) {
        if ($op.new_index -ge 0) { continue }
        $expected = if ($ReplacedResources -contains $op.path) { $ResourceOriginals[$op.path].sha256 } else { $null }
        if ($expected -ne (Get-TargetHash $op.path)) { throw 'Obsolete owned file differs' }
    }
    $Tx.Journal.phase = 'committing'; Save-UpgradeJournal $Tx
    Copy-Atomic (Inside $Tx.Work 'next-state.json') $StateFile $Tx.Plan.next_state_sha256
    # TEST-BOUNDARY: next-state-saved, phase still committing.
    $Tx.Journal.phase = 'committed'; Save-UpgradeJournal $Tx
    Complete-UpgradeJournal $Tx
}
function Install-Upgrade($Tx) {
    # Keep an interrupted transaction unchanged when a non-owned baseline was edited.
    $savedDefinition = $script:Manifest
    try { $script:Manifest = $Tx.Manifest; Check-Baseline $true (@($Tx.Plan.old_files) + @($Tx.Plan.new_files)) }
    finally { $script:Manifest = $savedDefinition }
    try {
        Check-UpgradePayloads $Tx; Check-UpgradeTargets $Tx
        foreach ($relative in $Tx.Plan.created_directories) { $null = [IO.Directory]::CreateDirectory((Inside $GameDir $relative)) }
        $Tx.Journal.phase = 'applying'; Save-UpgradeJournal $Tx
        for ($i = 0; $i -lt $Tx.Operations.Count; $i++) {
            $Tx.Journal.intent_index = [Math]::Max([int]$Tx.Journal.intent_index, $i); Save-UpgradeJournal $Tx
            $changed = Apply-UpgradeOperation $Tx $Tx.Operations[$i]
            # TEST-BOUNDARY: forward-operation-complete, before completed cursor save.
            $Tx.Journal.completed_count = [Math]::Max([int]$Tx.Journal.completed_count, ($i + 1)); Save-UpgradeJournal $Tx
        }
        Commit-Upgrade $Tx
        # Startup-language selection is part of the installation result. If its
        # atomic config write fails, the retained transaction restores the prior variant.
        Select-ChineseLanguage
    } catch {
        $failure = $_
        try { Rollback-Upgrade $Tx }
        catch { throw "Upgrade needs recovery: $($_.Exception.Message). Keep .lamulana-zh and rerun Install or Restore." }
        throw $failure
    }
}
function New-OriginalReceipt {
    Check-Baseline $false
    foreach ($file in $Manifest.files) {
        if ($file.path -ne 'LaMulanaWin.exe' -and $ReplacedResources -notcontains $file.path -and (Test-Path -LiteralPath (Inside $GameDir $file.path))) { throw "Unowned CHS file exists: $($file.path)" }
    }
    $null = [IO.Directory]::CreateDirectory($StateDir)
    $backup = Inside $StateDir 'original-LaMulanaWin.exe'
    if ([IO.File]::Exists($backup)) { if ((Hash-File $backup) -ne $OriginalExe) { throw 'Original executable backup differs' } }
    else { Copy-Atomic (Inside $GameDir 'LaMulanaWin.exe') $backup $OriginalExe }
    Save-ResourceBackups $Manifest.files
    $seed = [PSCustomObject]@{schema='lm1-chs-install-state-v1';status='restored';package_id=$Manifest.package_id;
        original_exe_sha256=$OriginalExe;files=@($Manifest.files);created_directories=@();stage=('stage-' + [Guid]::NewGuid().ToString('N'))}
    Save-State $seed
    return $seed
}

$OriginalExe = '94228016ffff8a0ba6325140f0cff6896e2bd0579bb2099d234508dede65923f'
$FormalExe = 'e2920f56cf06705e3bf1943e2990e319f76c59a7f46cafd9e411666fc2e36f64'
$TitleExe = '0e44ea2a3d940ebc6f6561026a1c4476fd9ec52c8b21894316457ceee1567ad4'
$SettingsLocaleExe = '9b1081cda51fb9384571078c1ea97bf03a622dd5ead732ae2c4ea27474f2c42f'
$TitleFooterExe = 'a4f7c74d4b468e9bd94ad120442e5eb789ddd0e2e63a6c8e5278d791465498fb'
$AssistantTargets = @('lm_assistant.dll','data/language/chs/assistant-font.ttf')
# Both variants recognize the same historical loaders; each loader binds to a
# specific production translation executable and inherits that exact file set.
$AssistantExeProfiles = @{
    'ba4946a2430da7d783b22a7f6f0cc0197bb7f0a9c6b5b55a757619d975c32c1e' = '0e44ea2a3d940ebc6f6561026a1c4476fd9ec52c8b21894316457ceee1567ad4'
    'd113161ccac9e010106d5c2c0d87b80455fde32d6eab3e858bec199e30b2e14e' = '9b1081cda51fb9384571078c1ea97bf03a622dd5ead732ae2c4ea27474f2c42f'
    'ee081e8cade83ac2df678a0e0467df5385510b9208252a2e306b07d5e1682409' = 'a4f7c74d4b468e9bd94ad120442e5eb789ddd0e2e63a6c8e5278d791465498fb'
    # BUILD-ASSISTANT-PROFILES
}
$TitleTargets = @('data/language/chs/title01.png','data/language/chs/title.msd')
$SettingsTargets = @('data/graphics/00/_banner.png','data/music/00/_banner.png')
$SettingsOriginalSha = 'fa05d6e4a27836cdcf7ef3d5e8a0ddbda2c4c25e2a07ab6674dc3fb0c3c960d2'
$SharedGraphicsTargets = @('data/graphics/00/eveg01.png','data/graphics/00/eveg18.png','data/graphics/00/map01_1.png')
$ResourceOriginals = @{
    'data/graphics/00/_banner.png' = @{sha256=$SettingsOriginalSha;bytes=1316;backup='original-graphics-banner.png'}
    'data/music/00/_banner.png' = @{sha256=$SettingsOriginalSha;bytes=1316;backup='original-music-banner.png'}
    'data/graphics/00/eveg01.png' = @{sha256='e3ff836d03cbbfdc12e9bcd8584972227bf23ddb77498d915d5abd5d75ce4faf';bytes=93941;backup='original-shared-eveg01.png'}
    'data/graphics/00/eveg18.png' = @{sha256='8eaeffd17a4eeee23a086d02b19a119083aa196e740fdaf94e5ca12f008abe59';bytes=89392;backup='original-shared-eveg18.png'}
    'data/graphics/00/map01_1.png' = @{sha256='3097c939bf6b25fc4845a0501a5e46e440572c9662eaa8891f55b9b9aaed7ca9';bytes=386436;backup='original-shared-map01_1.png'}
}
$ReplacedResources = @($SettingsTargets + $SharedGraphicsTargets)
$TitleBaselineHashes = @{'data/graphics/00/title01.png'='0a6378cce5dc1bd1d16da29bb32c0e4820a6f30d37f7f058285845ff528a526c';
                         'data/mapdata/title.msd'='fdb67475730211d9909b6c728bdfd0c0635eed768bb73e9467d5c2ac897872b8'}
$Modes = @('01guardian1c','02guardian1b','03guardian1a','04roomguardian3c','05roomguardian3b','06roomguardian3a',
           '07roomguardian2c','08roomguardian2b','09roomguardian2a','10roomguardian1c','11roomguardian1b','12roomguardian1a')
$Allowed = @('LaMulanaWin.exe')
$AllowedDirectories = @('data/language/chs')
$AllowedBaselines = @('LaMulanaWin.exe','data/graphics/00/01menu.png')
foreach ($name in @('script_code.dat','font00.png','font01.png','font02.png','grif.dat')) { $AllowedBaselines += "data/language/jp/$name" }
foreach ($name in @('script_code.dat','font00.png','font01.png','font02.png','grif.dat','_banner.png','01menu.png')) { $Allowed += "data/language/chs/$name" }
foreach ($mode in $Modes) {
    $directory = "data/ex/$mode/language/chs"
    $AllowedDirectories += $directory
    foreach ($name in @('script_code.dat','title.dat','font02.png')) { $Allowed += "$directory/$name" }
    foreach ($name in @('script_code.dat','title.dat','font02.png')) { $AllowedBaselines += "data/ex/$mode/language/jp/$name" }
}

$Manifest = $null
$mutex = $null
$lockHeld = $false
$LegacyInstallerHashes = @('d6fcd08385fddbb8c281a57269a25723732c52f46e7c21e1db0c9477ff8250fa',
    '688247a9c0267c0bf048a908b95364bf55542badc834a62f63b136c29d75a0be',
    '482158ead80b793ac7563412a7f37365668e87b63fbc634f1e660ef09ef3bd79',
    '57c2f81e051fffce72021cf1d85223402714f40ce6ffec632ae51bd9c937f1a8',
    '2e1980d7edb1ec579a405c836b2935f56d94f41ae52f668bea7f41c723230ea1',
    'b785f5ed81e7a3758ac5e1a88354e89008832f788727385831c61ae2c08ebf74',
    '222bd8a52775d05b7609f4d529138aabfcb08cb349b18b40e18b60848c1ea0b2')
$LegacyRestoreCommand = '@echo off' + "`r`n" + 'powershell.exe -NoLogo -NoProfile -File "%~dp0Restore.ps1" -Action Restore -GameDir "%~dp0.."' + "`r`n" + 'echo Press any key to close...' + "`r`n" + 'pause >nul' + "`r`n"
$RestoreCommand = '@echo off' + "`r`n" + 'powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Restore.ps1" -Action Restore -GameDir "%~dp0.."' + "`r`n" + 'echo Press any key to close...' + "`r`n" + 'pause >nul' + "`r`n"
try {
    $PackageDir = [IO.Path]::GetFullPath($PackageDir)
    if ($Action -ne 'Restore' -and [IO.File]::Exists((Inside $PackageDir 'manifest.json'))) {
        $Manifest = Read-Json (Inside $PackageDir 'manifest.json'); Check-Package
    }
    if ([string]::IsNullOrWhiteSpace($GameDir)) { $GameDir = Read-Host 'Game folder containing LaMulanaWin.exe' }
    $GameDir = [IO.Path]::GetFullPath($GameDir).TrimEnd('\')
    if (-not [IO.Directory]::Exists($GameDir)) { throw 'Game folder not found' }
    if (((Get-Item -LiteralPath $GameDir -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Select the physical game directory, not a junction or symlink' }
    $name = 'Local\LaMulanaCHS-' + (Hash-Bytes ($Utf8.GetBytes($GameDir.ToLowerInvariant())))
    $mutex = New-Object Threading.Mutex($false, $name)
    try { $lockHeld = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $lockHeld = $true }
    if (-not $lockHeld) { throw 'Another patch operation is running for this game directory' }
    $StateDir = Inside $GameDir '.lamulana-zh'; $StateFile = Inside $StateDir 'state.json'; $JournalFile = Inside $StateDir 'upgrade.json'
    if ([IO.File]::Exists((Inside $StateDir 'portable-upgrade.json'))) {
        throw 'An interrupted SteamOS/Linux operation is present. Run Install.sh or Restore.sh under Linux to recover before using the Windows installer.'
    }
    if ($Action -ne 'Restore' -and -not [IO.File]::Exists($JournalFile)) { Check-ModCompatibility }
    $state = $null
    if ([IO.File]::Exists($StateFile)) { $state = Read-Json $StateFile; Check-State $state }
    elseif ([IO.File]::Exists($JournalFile)) { throw 'Upgrade journal has no installation receipt; preserve the backup directory' }
    elseif ([IO.Directory]::Exists($StateDir)) {
        # A crash during original-backup/seed preparation has not changed any game target.
        foreach ($entry in [IO.Directory]::GetFileSystemEntries($StateDir)) {
            $leaf = [IO.Path]::GetFileName($entry)
            $originalLeaves = @('original-LaMulanaWin.exe') + @($ResourceOriginals.Values | ForEach-Object { $_.backup })
            if (-not [IO.File]::Exists($entry) -or ($leaf -notin $originalLeaves -and $leaf -notmatch '^(write|state)-[0-9a-f]{32}\.tmp$')) {
                throw 'Reserved backup folder exists without a valid receipt'
            }
            $null = Inside $StateDir $leaf
        }
    }
    if ($Action -eq 'Check') {
        if ($null -eq $Manifest) { throw 'Patch package manifest not found' }
        if ([IO.File]::Exists($JournalFile)) {
            $tx = Read-UpgradeTransaction; Check-UpgradeTargets $tx
            throw 'An interrupted transaction is present. Run Install to resume, or Restore to restore the original game.'
        }
        if ($null -ne $state -and $state.status -eq 'installed') { Check-Baseline $true $state.files; Check-Installed $state; Write-Output 'PASS: installed files and game baseline match.' }
        else { Check-Baseline $false; Write-Output 'PASS: original game and package match.' }
        exit 0
    }
    Check-GameProcess
    if ([IO.File]::Exists($JournalFile)) {
        $tx = Read-UpgradeTransaction
        $resume = $Action -eq 'Install' -and ($null -eq $Manifest -or $Manifest.package_id -eq $tx.Plan.to_package_id)
        if ($resume -and $null -ne $Manifest -and (File-Signature $Manifest.files) -ne (File-Signature $tx.Plan.new_files)) { throw 'The same package identity now has different files' }
        if ($Action -eq 'Restore' -or -not $resume -or $tx.Journal.phase -in @('rolling-back','rolled-back')) {
            Rollback-Upgrade $tx
            if ($Action -eq 'Install' -and $null -eq $Manifest) {
                $tx.Journal.phase = 'prepared'; $tx.Journal.intent_index = -1; $tx.Journal.completed_count = 0; $tx.Journal.rollback_completed_count = 0
                Save-UpgradeJournal $tx; Install-Upgrade $tx
                Write-Output 'PASS: interrupted installation recovered and completed from its verified local snapshot.'; exit 0
            }
        } else {
            Install-Upgrade $tx
            if ($null -eq $Manifest) { Write-Output 'PASS: interrupted installation completed from its verified local snapshot.'; exit 0 }
        }
        $state = Read-Json $StateFile; Check-State $state
    }
    if ($Action -eq 'Restore') {
        if ($null -eq $state) { throw 'No installation receipt; nothing was changed' }
        Restore-Owned $state
        Write-Output 'PASS: original replaced files restored; owned CHS files removed. Save files were not accessed.'; exit 0
    }
    if ($null -eq $Manifest) { throw 'Patch package manifest not found' }
    if ($null -ne $state -and $state.status -eq 'installing') {
        # Legacy V1 interrupted initial installations are recovered internally.
        Restore-Owned $state
        $state = Read-Json $StateFile; Check-State $state
    }
    if ($null -ne $state -and $state.status -eq 'installed') {
        Check-Installed $state
        if ($state.package_id -eq $Manifest.package_id) {
            if ((File-Signature $state.files) -ne (File-Signature $Manifest.files)) { throw 'The same package identity now has different files' }
            Check-Baseline $true $state.files
            Check-EngineFiles; Save-RecoveryEngine
            Select-ChineseLanguage; Write-Output 'PASS: this package is already installed.'; exit 0
        }
    }
    if ($null -eq $state) { $state = New-OriginalReceipt }
    $tx = Start-UpgradeTransaction $state
    Install-Upgrade $tx
    Write-Output 'PASS: CHS patch installed or upgraded. Startup language is Simplified Chinese. Save files were not accessed.'
    exit 0
} catch {
    if ($_.Exception.Message.StartsWith('This patch does not support La-Mulana EX Map Port', [StringComparison]::Ordinal)) {
        [Console]::Error.WriteLine($_.Exception.Message)
    } else { Write-Error $_.Exception.Message }
    exit 1
} finally {
    if ($lockHeld -and $null -ne $mutex) { $mutex.ReleaseMutex() }
    if ($null -ne $mutex) { $mutex.Dispose() }
}
