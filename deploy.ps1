# Project: SCR Tools
# Repository: SCR-Tools (local Git-ready source)
# File path: deploy.ps1
# Module Type: Windows release build
# Purpose: Build a standalone executable and per-user installer.
# Responsibilities: Validate system Python, test, package and clean stages.
# Author: Rudolf Klusal
# License: MIT

<#
.SYNOPSIS
Build SCR Tools using installed system CPython 3.14 x64 and Inno Setup 6/7.
.DESCRIPTION
Runs source checks and tests, creates a one-file GUI executable with
PyInstaller, then quietly compiles the installer. No environment is created
or activated. No installer is run. Final binaries and diagnostic build logs
remain under release; each invocation's private stage is removed in finally.
.PARAMETER InstallDependencies
Explicitly allow pip to install the pinned requirements into system Python.
.PARAMETER InnoCompiler
Optional full path to ISCC.exe, overriding PATH and installation discovery.
.OUTPUTS
Console progress and versioned files in the release directory.
#>
[CmdletBinding()]
param(
    [switch]$InstallDependencies,
    [string]$InnoCompiler = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-CheckedTool {
    <#
    .SYNOPSIS
    Run one native command, retain its output and enforce its exit status.
    .PARAMETER FilePath
    Absolute executable path validated by the caller.
    .PARAMETER Arguments
    Native arguments, each passed separately without shell interpolation.
    .PARAMETER Step
    Human-readable operation name used in failure diagnostics.
    .PARAMETER LogFile
    File receiving both output streams for later diagnosis.
    .OUTPUTS
    None. Throws if command execution or log writing fails.
    #>
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments,
        [Parameter(Mandatory)][string]$Step,
        [Parameter(Mandatory)][string]$LogFile
    )
    Write-Host $Step
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        throw "$Step executable does not exist: $FilePath"
    }
    # PyInstaller writes normal progress to stderr. Windows PowerShell 5.1
    # may wrap that stream as NativeCommandError; it is not a failure by
    # itself. The native exit code remains authoritative. Log errors still
    # terminate explicitly so a failed log write cannot hide a build error.
    $previousPreference = $ErrorActionPreference
    $nativeExit = -1
    try {
        $ErrorActionPreference = 'Continue'
        & $FilePath @Arguments 2>&1 |
            Tee-Object -FilePath $LogFile -Append -ErrorAction Stop |
            ForEach-Object { Write-Host $_ }
        $nativeExit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($nativeExit -ne 0) {
        throw "$Step failed with exit code $nativeExit. See $LogFile"
    }
}

function Find-InnoCompiler {
    <#
    .SYNOPSIS
    Resolve an installed Inno Setup 6 or 7 console compiler.
    .PARAMETER RequestedPath
    Optional user-supplied compiler path, which must be valid if specified.
    .OUTPUTS
    System.String: Absolute validated ISCC.exe path.
    #>
    [OutputType([string])]
    param([string]$RequestedPath)

    $candidates = [System.Collections.Generic.List[string]]::new()
    if ($RequestedPath) {
        $candidates.Add($RequestedPath)
    }
    else {
        $command = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
        if ($command) {
            $candidates.Add($command.Source)
        }
        $programRoots = @(
            ${env:ProgramFiles(x86)}, $env:ProgramFiles,
            (Join-Path $env:LOCALAPPDATA 'Programs')
        )
        foreach ($major in @(7, 6)) {
            foreach ($programRoot in $programRoots) {
                if ($programRoot) {
                    $candidates.Add(
                        (Join-Path $programRoot "Inno Setup $major\ISCC.exe")
                    )
                }
            }
            $registryRoots = @(
                'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
                'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
                'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
            )
            foreach ($registryRoot in $registryRoots) {
                $key = Join-Path $registryRoot "Inno Setup ${major}_is1"
                $installed = Get-ItemProperty -LiteralPath $key `
                    -Name 'InstallLocation' -ErrorAction SilentlyContinue
                if ($installed -and $installed.InstallLocation) {
                    $candidates.Add(
                        (Join-Path $installed.InstallLocation 'ISCC.exe')
                    )
                }
            }
        }
    }
    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            continue
        }
        $resolved = (Resolve-Path -LiteralPath $candidate).Path
        $majorVersion = (Get-Item -LiteralPath $resolved).VersionInfo.FileMajorPart
        if ($majorVersion -in @(6, 7)) {
            return $resolved
        }
    }
    throw ('Inno Setup 6 or 7 ISCC.exe was not found. Install Inno Setup ' +
        'or pass -InnoCompiler "C:\path\to\ISCC.exe".')
}

$projectRoot = $PSScriptRoot
$stageRoot = $null
$stageParent = Join-Path $projectRoot '.build'
$releaseRoot = Join-Path $projectRoot 'release'
$logRoot = $null
$previousPythonPath = $env:PYTHONPATH
$previousPyInstallerConfig = $env:PYINSTALLER_CONFIG_DIR
$buildSucceeded = $false

try {
    if ($env:OS -ne 'Windows_NT') {
        throw 'Build on Windows 11 x64. PyInstaller is not a cross-compiler.'
    }
    $launcher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if (-not $launcher) {
        throw 'Install system CPython 3.14 x64 with the Python launcher (py.exe).'
    }
    $interpreterProbe = @'
import json
import platform
import struct
import sys
import sysconfig
if sys.version_info[:2] != (3, 14):
    raise SystemExit('CPython 3.14 is required.')
if platform.python_implementation() != 'CPython':
    raise SystemExit('CPython is required.')
if struct.calcsize('P') != 8:
    raise SystemExit('A 64-bit interpreter is required.')
if sysconfig.get_platform() != 'win-amd64':
    raise SystemExit('Windows x64 Python is required.')
if sys.prefix != sys.base_prefix:
    raise SystemExit('Virtual environments are prohibited.')
if sysconfig.get_config_var('Py_GIL_DISABLED') or 0:
    raise SystemExit('Use standard CPython.')
if sys.platform != 'win32' or sys.getwindowsversion().build < 22000:
    raise SystemExit('Build on Windows 11, build 22000 or newer.')
print(json.dumps({'executable': sys.executable, 'version': platform.python_version()}))
'@
    $probeOutput = & $launcher.Source '-3.14' '-c' $interpreterProbe
    if ($LASTEXITCODE -ne 0) {
        throw ('py -3.14 did not select installed standard CPython 3.14 x64. ' +
            'Use a system installation, not a virtual environment.')
    }
    $interpreter = $probeOutput | ConvertFrom-Json
    $pythonExecutable = [string]$interpreter.executable
    Write-Host "Using system CPython $($interpreter.version): $pythonExecutable"
    $compiler = Find-InnoCompiler -RequestedPath $InnoCompiler
    Write-Host "Using Inno Setup compiler: $compiler"

    $buildId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'),
        ([guid]::NewGuid().ToString('N'))
    $stageRoot = Join-Path $stageParent $buildId
    $logRoot = Join-Path (Join-Path $releaseRoot 'buildlogs') $buildId
    New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    $env:PYTHONPATH = Join-Path $projectRoot 'src'
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $stageRoot 'pyinstaller-cache'

    if ($InstallDependencies) {
        Invoke-CheckedTool -FilePath $pythonExecutable -Arguments @(
            '-m', 'pip', 'install', '--disable-pip-version-check',
            '-r', (Join-Path $projectRoot 'requirements-build.txt')
        ) -Step 'Installing explicitly requested build dependencies' `
            -LogFile (Join-Path $logRoot 'dependencies.log')
    }

    $dependencyProbe = @'
import importlib.metadata
import pathlib
import sys
import tkinter
import PIL.Image
import PIL.ImageGrab
import PyInstaller
root = pathlib.Path(sys.argv[1])
for name in ('requirements.txt', 'requirements-build.txt'):
    for raw in (root / name).read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith(('#', '-r')):
            continue
        package, expected = line.split('==', 1)
        actual = importlib.metadata.version(package)
        if actual != expected:
            raise SystemExit(f'{package}: expected {expected}, found {actual}')
        print(f'{package} {actual}')
print('Tcl ' + tkinter.Tcl().eval('info patchlevel'))
'@
    try {
        Invoke-CheckedTool -FilePath $pythonExecutable -Arguments @(
            '-c', $dependencyProbe, $projectRoot
        ) -Step 'Checking runtime/build dependencies and Tcl availability' `
            -LogFile (Join-Path $logRoot 'dependency-check.log')
    }
    catch {
        throw ('Dependency validation failed. Run py -3.14 -m pip install ' +
            '-r requirements-build.txt, or use -InstallDependencies. ' + $_)
    }

    Invoke-CheckedTool -FilePath $pythonExecutable -Arguments @(
        (Join-Path $projectRoot 'scripts\check_source.py')
    ) -Step 'Checking complete source files' `
        -LogFile (Join-Path $logRoot 'source-check.log')
    Invoke-CheckedTool -FilePath $pythonExecutable -Arguments @(
        '-m', 'unittest', 'discover', '-s', (Join-Path $projectRoot 'tests'), '-v'
    ) -Step 'Running automated tests' `
        -LogFile (Join-Path $logRoot 'tests.log')

    $version = & $pythonExecutable `
        (Join-Path $projectRoot 'scripts\release_metadata.py') `
        '--stage' $stageRoot
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') {
        throw 'Could not create release metadata from src/scr_tools/version.py.'
    }
    $version = [string]$version
    $distRoot = Join-Path $stageRoot 'dist'
    $workRoot = Join-Path $stageRoot 'work'
    $installerOutput = Join-Path $stageRoot 'installer-output'
    $bundleArguments = @(
        '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
        '--windowed', '--noupx', '--name', 'SCRTools',
        '--paths', (Join-Path $projectRoot 'src'),
        '--distpath', $distRoot,
        '--workpath', $workRoot,
        '--specpath', $stageRoot,
        '--icon', (Join-Path $projectRoot 'assets\icons\scr_tools.ico'),
        '--manifest', (Join-Path $stageRoot 'SCRTools.manifest'),
        '--version-file', (Join-Path $stageRoot 'version_info.txt'),
        '--add-data', ((Join-Path $projectRoot 'assets\icons\scr_tools.ico') +
            ':assets/icons'),
        '--add-data', ((Join-Path $projectRoot 'src\scr_tools\localization\*.json') +
            ':scr_tools/localization'),
        (Join-Path $projectRoot 'run_scr_tools.py')
    )
    Invoke-CheckedTool -FilePath $pythonExecutable -Arguments $bundleArguments `
        -Step 'Building SCRTools.exe with PyInstaller' `
        -LogFile (Join-Path $logRoot 'pyinstaller.log')
    $sourceExecutable = Join-Path $distRoot 'SCRTools.exe'
    if (-not (Test-Path -LiteralPath $sourceExecutable -PathType Leaf)) {
        throw 'PyInstaller returned success but SCRTools.exe is missing.'
    }

    # /Q is the quiet compiler option accepted by both Inno Setup 6 and 7.
    # Compilation does not run the resulting installer.
    Invoke-CheckedTool -FilePath $compiler -Arguments @(
        '/Q', "/DAppVersion=$version", "/DSourceExe=$sourceExecutable",
        "/DOutputDir=$installerOutput", "/DProjectRoot=$projectRoot",
        (Join-Path $projectRoot 'installer\SCRTools.iss')
    ) -Step 'Compiling the per-user installer' `
        -LogFile (Join-Path $logRoot 'inno-setup.log')

    $setupName = "SCRTools_${version}_Setup.exe"
    $sourceSetup = Join-Path $installerOutput $setupName
    if (-not (Test-Path -LiteralPath $sourceSetup -PathType Leaf)) {
        throw "Inno Setup returned success but $setupName is missing."
    }
    $finalExecutable = Join-Path $releaseRoot "SCRTools_${version}.exe"
    $finalSetup = Join-Path $releaseRoot $setupName
    Copy-Item -LiteralPath $sourceExecutable -Destination $finalExecutable -Force
    Copy-Item -LiteralPath $sourceSetup -Destination $finalSetup -Force
    $buildSucceeded = $true
}
catch {
    Write-Error -Message $_ -ErrorAction Continue
    if ($logRoot) {
        Write-Host "Retained diagnostic logs: $logRoot"
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    $env:PYINSTALLER_CONFIG_DIR = $previousPyInstallerConfig
    if ($stageRoot -and (Test-Path -LiteralPath $stageRoot)) {
        if ($logRoot) {
            Get-ChildItem -LiteralPath $stageRoot -Recurse -File `
                -Filter 'warn-*.txt' -ErrorAction SilentlyContinue |
                ForEach-Object {
                    Copy-Item -LiteralPath $_.FullName -Destination $logRoot `
                        -Force -ErrorAction Continue
                }
        }
        # Remove only the unique direct child created by this invocation.
        $actualParent = [System.IO.Path]::GetFullPath(
            (Split-Path -Parent $stageRoot)
        ).TrimEnd('\')
        $expectedParent = [System.IO.Path]::GetFullPath($stageParent).TrimEnd('\')
        if ($actualParent -eq $expectedParent) {
            try {
                Remove-Item -LiteralPath $stageRoot -Recurse -Force
            }
            catch {
                Write-Warning "Could not remove owned build stage: $stageRoot"
                $buildSucceeded = $false
            }
        }
        else {
            Write-Warning 'Refused cleanup because the stage parent did not match.'
            $buildSucceeded = $false
        }
    }
}

if (-not $buildSucceeded) {
    exit 1
}
Write-Host "Build complete: $finalExecutable"
Write-Host "Installer complete: $finalSetup"
Write-Host "Build logs: $logRoot"
exit 0
