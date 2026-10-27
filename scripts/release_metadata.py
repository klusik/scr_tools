# Project: SCR Tools
# Repository: SCR-Tools (local Git-ready source)
# File path: scripts/release_metadata.py
# Module Type: Release resource generator
# Purpose: Derive Windows build metadata from the authoritative version.
# Responsibilities: Validate the version and generate version/manifest files.
# Author: Rudolf Klusal
# License: MIT

"""Generate transient PyInstaller resources without importing the GUI."""

import argparse
import ast
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path


ROOT: Path = Path(__file__).resolve().parents[1]
VERSION_PATTERN: re.Pattern[str] = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
ASSEMBLY_NAMESPACE: str = "urn:schemas-microsoft-com:asm.v1"


def read_version(root: Path) -> str:
    """Read a literal application version without executing source code.

    Args:
        root (Path): Repository directory containing ``src/scr_tools``.

    Returns:
        str: A numeric three-component release version.

    Raises:
        OSError: If the authoritative version file cannot be read.
        ValueError: If the version is absent or not a valid Windows version.
    """
    source: str = (root / "src/scr_tools/version.py").read_text("utf-8")
    tree: ast.Module = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "VERSION" and node.value is not None:
                version: object = ast.literal_eval(node.value)
                if isinstance(version, str) and VERSION_PATTERN.fullmatch(version):
                    if all(int(part) <= 65535 for part in version.split(".")):
                        return version
    raise ValueError("version.py must define a numeric VERSION: str literal.")


def write_metadata(stage: Path, version: str) -> None:
    """Write the EXE version resource and manifest into an owned build stage.

    Args:
        stage (Path): Existing or new temporary build directory.
        version (str): Validated three-component application version.

    Returns:
        None: Two temporary text files are written into ``stage``.

    Raises:
        OSError: If input resources or output files are inaccessible.
        ValueError: If the maintained manifest lacks its assembly identity.
    """
    stage.mkdir(parents=True, exist_ok=True)
    numbers: tuple[int, ...] = tuple(int(part) for part in version.split("."))
    file_version: tuple[int, ...] = (*numbers, 0)
    resource: str = f'''VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={file_version!r}, prodvers={file_version!r},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'Rudolf Klusal'),
        StringStruct('FileDescription', 'SCR Tools'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', 'SCRTools'),
        StringStruct('LegalCopyright', 'Copyright (c) 2026 Rudolf Klusal'),
        StringStruct('OriginalFilename', 'SCRTools.exe'),
        StringStruct('ProductName', 'SCR Tools'),
        StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
'''
    (stage / "version_info.txt").write_text(resource, encoding="utf-8")
    manifest: ElementTree.ElementTree = ElementTree.parse(
        ROOT / "assets/SCRTools.manifest"
    )
    identity: ElementTree.Element | None = manifest.find(
        f"{{{ASSEMBLY_NAMESPACE}}}assemblyIdentity"
    )
    if identity is None:
        raise ValueError("The executable manifest lacks assemblyIdentity.")
    identity.set("version", ".".join(str(part) for part in file_version))
    manifest.write(
        stage / "SCRTools.manifest", encoding="utf-8", xml_declaration=True
    )


def main() -> None:
    """Print the authoritative version and optionally create build resources.

    Returns:
        None: The numeric version is written to standard output.

    Raises:
        OSError: If the version or requested build resources are inaccessible.
        ValueError: If the version or manifest is invalid.
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=__doc__
    )
    parser.add_argument("--stage", type=Path)
    arguments: argparse.Namespace = parser.parse_args()
    version: str = read_version(ROOT)
    if arguments.stage is not None:
        write_metadata(arguments.stage, version)
    print(version)


if __name__ == "__main__":
    main()
