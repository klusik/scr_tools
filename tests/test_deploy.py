# Project: SCR Tools
# Repository: SCR-Tools (local Git-ready source)
# File path: tests/test_deploy.py
# Module Type: Windows build-tool discovery tests
# Purpose: Verify native compiler discovery without performing a release build.
# Responsibilities: Exercise PATH, overrides, compiler banners and failures.
# Author: Rudolf Klusal
# License: MIT

"""Run the actual PowerShell resolver against isolated native command wrappers."""

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT: Path = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == "win32", "PowerShell discovery needs Windows")
class DeployCompilerTests(unittest.TestCase):
    """Check compiler selection and errors without installing any build tools."""

    def setUp(self) -> None:
        """Create isolated PATH entries and locate the installed PowerShell.

        Returns:
            None. Tests skip if Windows PowerShell is unavailable.
        """
        executable: str | None = shutil.which("powershell.exe")
        if executable is None:
            self.skipTest("Windows PowerShell is unavailable")
        self.powershell: str = executable
        temporary: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder: Path = Path(temporary.name)

    def _compiler(self, directory: str, major: int) -> Path:
        """Create a PATH wrapper with no PE version metadata and a real banner.

        Args:
            directory: Test-local folder name, including spaces where needed.
            major: Inno major version reported by the substitute command.

        Returns:
            Absolute ISCC.cmd path; /? deliberately returns Inno 6's code 1.
        """
        folder: Path = self.folder / directory
        folder.mkdir()
        compiler: Path = folder / "ISCC.cmd"
        compiler.write_text(
            "@echo off\n"
            f"echo Inno Setup {major} Command-Line Compiler\n"
            "exit /b 1\n",
            encoding="ascii",
            newline="\r\n",
        )
        return compiler

    def _resolve(
        self, entries: tuple[Path, ...], requested: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Execute only the maintained resolver in an isolated PowerShell.

        Args:
            entries: Ordered PATH directories; real system installations are
                hidden so each selection/failure is deterministic.
            requested: Explicit compiler override, or None for normal discovery.

        Returns:
            Captured process result: JSON compiler path on success, or a
            nonzero status and operational message on failure.

        Raises:
            subprocess.TimeoutExpired: The resolver does not finish in time.
            OSError: PowerShell cannot be started.
        """
        environment: dict[str, str] = os.environ.copy()
        environment["PATH"] = os.pathsep.join(str(entry) for entry in entries)
        environment["PATHEXT"] = ".EXE;.CMD;.BAT"
        for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            environment[name] = str(self.folder)
        environment["SCR_TEST_DEPLOY"] = str(ROOT / "deploy.ps1")
        environment["SCR_TEST_COMPILER"] = str(requested) if requested else ""
        command: str = r"""
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$parseTokens = $null
$parseErrors = $null
$tree = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:SCR_TEST_DEPLOY, [ref]$parseTokens, [ref]$parseErrors
)
if ($parseErrors.Count) { throw 'deploy.ps1 has syntax errors' }
$definition = $tree.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Find-InnoCompiler'
}, $false)
if (-not $definition) { throw 'Compiler resolver is missing' }
# Load only this function, never the build's top-level effects or exit.
Invoke-Expression $definition.Extent.Text
function Get-ItemProperty {
    <# .SYNOPSIS Hide machine registry installations from this isolated test. #>
    param([string]$LiteralPath, [string]$Name, [string]$ErrorAction)
    return $null
}
try {
    $compiler = Find-InnoCompiler -RequestedPath $env:SCR_TEST_COMPILER
    @{compiler = $compiler} | ConvertTo-Json -Compress
    exit 0
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
"""
        encoded: str = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
        return subprocess.run(
            [self.powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            env=environment, capture_output=True, text=True, timeout=20,
            check=False,
        )

    def test_path_wrapper_with_spaces_and_no_file_version_is_accepted(self) -> None:
        """ISCC on PATH works despite absent PE metadata and help exit code 1."""
        compiler: Path = self._compiler("PATH tools", 6)
        result: subprocess.CompletedProcess[str] = self._resolve((compiler.parent,))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)["compiler"]), compiler)

    def test_explicit_override_takes_precedence_over_path(self) -> None:
        """An optional explicit Inno 7 path remains compatible with callers."""
        on_path: Path = self._compiler("PATH tools", 6)
        override: Path = self._compiler("Override tools", 7)
        result: subprocess.CompletedProcess[str] = self._resolve(
            (on_path.parent,), override
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(json.loads(result.stdout)["compiler"]), override)

    def test_missing_compiler_explains_path_configuration(self) -> None:
        """Missing tools report how to use PATH without requiring a path option."""
        result: subprocess.CompletedProcess[str] = self._resolve(())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PATH", result.stderr)
        self.assertIn("ISCC", result.stderr)

    def test_invalid_explicit_path_does_not_fall_back(self) -> None:
        """A mistyped override cannot silently select an unrelated compiler."""
        on_path: Path = self._compiler("PATH tools", 6)
        result: subprocess.CompletedProcess[str] = self._resolve(
            (on_path.parent,), self.folder / "missing.exe"
        )
        self.assertNotEqual(result.returncode, 0)

    def test_unsupported_compiler_banner_is_rejected(self) -> None:
        """Discovery retains the supported Inno 6/7 contract without PE metadata."""
        compiler: Path = self._compiler("Unsupported tools", 8)
        result: subprocess.CompletedProcess[str] = self._resolve((compiler.parent,))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Inno Setup 6 or 7", result.stderr)


if __name__ == "__main__":
    unittest.main()
