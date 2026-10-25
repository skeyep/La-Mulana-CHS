param(
    [ValidateSet('Check','Install','Restore')][string]$Action = 'Install',
    [string]$GameDir = '',
    [string]$PackageDir = $PSScriptRoot,
    [switch]$ListOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

function Add-Directory($List, [string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return }
    try {
        $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
        if ([IO.Directory]::Exists($full) -and @($List | Where-Object { $_ -eq $full }).Count -eq 0) { $List.Add($full) }
    } catch { }
}
function Get-LaMulanaSteamDirectories {
    $steamRoots = New-Object 'Collections.Generic.List[string]'
    foreach ($key in @('HKCU:\Software\Valve\Steam','HKLM:\SOFTWARE\WOW6432Node\Valve\Steam','HKLM:\SOFTWARE\Valve\Steam')) {
        try {
            $item = Get-ItemProperty -LiteralPath $key -ErrorAction Stop
            foreach ($name in @('SteamPath','InstallPath')) {
                if ($null -ne $item.PSObject.Properties[$name]) { Add-Directory $steamRoots ([string]$item.$name) }
            }
        } catch { }
    }
    if (-not [string]::IsNullOrWhiteSpace(${env:ProgramFiles(x86)})) { Add-Directory $steamRoots (Join-Path ${env:ProgramFiles(x86)} 'Steam') }
    $libraries = New-Object 'Collections.Generic.List[string]'
    foreach ($steam in $steamRoots) {
        Add-Directory $libraries $steam
        $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
        if (-not [IO.File]::Exists($vdf)) { continue }
        $text = [IO.File]::ReadAllText($vdf, [Text.Encoding]::UTF8)
        foreach ($match in [regex]::Matches($text, '"path"\s+"([^"]+)"|"\d+"\s+"([A-Za-z]:[^"]+)"')) {
            $path = $match.Groups[1].Value
            if ([string]::IsNullOrEmpty($path)) { $path = $match.Groups[2].Value }
            Add-Directory $libraries ($path.Replace('\\','\'))
        }
    }
    $games = New-Object 'Collections.Generic.List[string]'
    foreach ($library in $libraries) {
        $acf = Join-Path $library 'steamapps\appmanifest_230700.acf'
        if (-not [IO.File]::Exists($acf)) { continue }
        $text = [IO.File]::ReadAllText($acf, [Text.Encoding]::UTF8)
        if ($text -notmatch '"appid"\s+"230700"') { continue }
        $match = [regex]::Match($text, '"installdir"\s+"([^"]+)"')
        if (-not $match.Success) { continue }
        $name = $match.Groups[1].Value
        if ($name -match '[\\/:]' -or $name -in @('.','..')) { continue }
        $candidate = Join-Path (Join-Path $library 'steamapps\common') $name
        if ([IO.File]::Exists((Join-Path $candidate 'LaMulanaWin.exe'))) { Add-Directory $games $candidate }
    }
    return @($games.ToArray())
}
function Select-LaMulanaDirectory($Candidates) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object Windows.Forms.FolderBrowserDialog
    try {
        $dialog.Description = 'Select the La-Mulana game folder containing LaMulanaWin.exe.'
        $dialog.ShowNewFolderButton = $false
        if ($Candidates.Count -gt 0) { $dialog.SelectedPath = $Candidates[0] }
        if ($dialog.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { throw 'Game folder selection canceled.' }
        $selected = [IO.Path]::GetFullPath($dialog.SelectedPath)
        if (-not [IO.File]::Exists((Join-Path $selected 'LaMulanaWin.exe'))) { throw 'The selected folder does not contain LaMulanaWin.exe.' }
        return $selected
    } finally { $dialog.Dispose() }
}

try {
    if ($ListOnly) {
        $candidates = @(Get-LaMulanaSteamDirectories)
        ConvertTo-Json -InputObject $candidates -Compress
        exit 0
    }
    if (-not [string]::IsNullOrWhiteSpace($GameDir)) {
        $GameDir = [IO.Path]::GetFullPath($GameDir)
        if (-not [IO.File]::Exists((Join-Path $GameDir 'LaMulanaWin.exe'))) { throw 'The specified folder does not contain LaMulanaWin.exe.' }
    } else {
        $candidates = @(Get-LaMulanaSteamDirectories)
        if ($candidates.Count -eq 1) { $GameDir = $candidates[0] }
        else { $GameDir = Select-LaMulanaDirectory $candidates }
    }
    $patch = Join-Path $PSScriptRoot 'Patch.ps1'
    if (-not [IO.File]::Exists($patch)) { throw 'Patch.ps1 is missing. Extract the complete package and try again.' }
    $arguments = @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$patch,'-Action',$Action,'-GameDir',$GameDir,'-PackageDir',$PackageDir)
    & powershell.exe @arguments
    exit $LASTEXITCODE
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
