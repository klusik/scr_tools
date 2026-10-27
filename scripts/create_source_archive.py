# Project: SCR Tools
# Repository: SCR-Tools (local Git-ready source)
# File path: scripts/create_source_archive.py
# Module Type: Source release packaging
# Purpose: Create and inspect a clean, reproducible source archive.
# Responsibilities: Include maintained files and exclude generated/private data.
# Author: Rudolf Klusal
# License: MIT

"""Package maintained source without Git history, user data or build products."""

import argparse
import hashlib
import zipfile
from pathlib import Path

from release_metadata import read_version


ROOT: Path = Path(__file__).resolve().parents[1]
ROOT_FILES: frozenset[str] = frozenset({
    "AGENTS.md", "README.md", "LICENSE", ".gitignore", ".gitattributes",
    "requirements.txt", "requirements-build.txt", "deploy.ps1",
    "run_scr_tools.py",
})
SOURCE_DIRECTORIES: tuple[str, ...] = (
    "src", "assets", "docs", "installer", "scripts", "tests",
)
EXCLUDED_PARTS: frozenset[str] = frozenset({
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".git", ".venv", "venv", "build", "dist", "release", ".build",
})
EXCLUDED_SUFFIXES: frozenset[str] = frozenset({
    ".pyc", ".pyo", ".log", ".tmp", ".temp", ".bak", ".zip", ".exe",
})
REQUIRED_PATHS: frozenset[str] = ROOT_FILES | frozenset({
    "src/scr_tools/app.py", "src/scr_tools/version.py",
    "src/scr_tools/localization/en.json", "assets/icons/scr_tools.ico",
    "assets/icons/scr_tools.svg", "assets/SCRTools.manifest",
    "installer/SCRTools.iss", "tests/test_configuration.py",
    "docs/BUILD.md", "docs/VERIFICATION.md",
})


def source_paths() -> list[Path]:
    """Collect only maintained repository files from the explicit source areas.

    Returns:
        list[Path]: Sorted regular files, excluding generated/private artifacts.

    Raises:
        FileNotFoundError: A required source file has not been created.
    """
    paths: list[Path] = [ROOT / name for name in ROOT_FILES]
    for directory in SOURCE_DIRECTORIES:
        paths.extend((ROOT / directory).rglob("*"))
    selected: list[Path] = sorted(
        path for path in paths
        if path.is_file()
        and not path.is_symlink()
        and not EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts)
        and path.suffix.lower() not in EXCLUDED_SUFFIXES
        and ".broken." not in path.name
    )
    included: set[str] = {
        path.relative_to(ROOT).as_posix() for path in selected
    }
    missing: frozenset[str] = REQUIRED_PATHS - included
    if missing:
        raise FileNotFoundError("Missing source files: " + ", ".join(sorted(missing)))
    return selected


def create_archive(destination: Path) -> tuple[int, str]:
    """Write and inspect a deterministic source ZIP with one project directory.

    Args:
        destination (Path): Requested ZIP filename outside maintained sources.

    Returns:
        tuple[int, str]: File count and SHA-256 of the completed archive.

    Raises:
        OSError: Input files or the output archive cannot be read/written.
        ValueError: The output suffix is not ZIP or ZIP verification fails.
        FileNotFoundError: A required source file is absent.
    """
    if destination.suffix.lower() != ".zip":
        raise ValueError("Source archive output must have a .zip extension.")
    paths: list[Path] = source_paths()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w") as archive:
        for path in paths:
            member: str = "SCR-Tools/" + path.relative_to(ROOT).as_posix()
            # Stable timestamps/modes make unchanged source bytes reproducible.
            info: zipfile.ZipInfo = zipfile.ZipInfo(member, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    with zipfile.ZipFile(destination) as archive:
        damaged: str | None = archive.testzip()
        if damaged is not None:
            raise ValueError(f"ZIP verification failed for {damaged}.")
        names: set[str] = set(archive.namelist())
        expected: set[str] = {"SCR-Tools/" + name for name in REQUIRED_PATHS}
        if not expected <= names:
            raise ValueError("Required source files are absent from the ZIP.")
    digest: str = hashlib.sha256(destination.read_bytes()).hexdigest()
    return len(paths), digest


def main() -> None:
    """Build the versioned source archive and print its inspection evidence.

    Returns:
        None: The path, member count and SHA-256 are printed.

    Raises:
        OSError: Source enumeration or archive creation fails.
        ValueError: Version, destination or ZIP validation fails.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments: argparse.Namespace = parser.parse_args()
    destination: Path = arguments.output or (
        ROOT / "release" / f"SCRTools_{read_version(ROOT)}_Source.zip"
    )
    destination = destination.resolve()
    count, digest = create_archive(destination)
    print(f"Created and verified {destination}")
    print(f"Maintained files: {count}")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
