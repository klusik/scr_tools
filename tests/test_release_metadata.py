# Project: SCR Tools
# Repository: SCR-Tools (local Git-ready source)
# File path: tests/test_release_metadata.py
# Module Type: Release-resource regression tests
# Purpose: Verify versioned manifests remain compatible with Windows packaging.
# Responsibilities: Preserve XML names, namespaces, policies and source assets.
# Author: Rudolf Klusal
# License: MIT

"""Check generated release files without requiring a packaging dependency."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ElementTree

from scripts.release_metadata import ROOT, read_version, write_metadata


class ReleaseMetadataTests(unittest.TestCase):
    """Exercise staged XML and the maintained template's failure contract."""

    def setUp(self) -> None:
        """Create an isolated output stage without editing maintained assets."""
        temporary: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder: Path = Path(temporary.name)

    def test_manifest_preserves_packager_names_and_windows_policies(self) -> None:
        """Generated XML keeps unprefixed tags and all Windows policy namespaces."""
        write_metadata(self.folder, "2.3.4")
        manifest: bytes = (self.folder / "SCRTools.manifest").read_bytes()
        with minidom.parseString(manifest) as document:
            self.assertEqual(document.documentElement.tagName, "assembly")
            self.assertEqual(
                document.documentElement.namespaceURI,
                "urn:schemas-microsoft-com:asm.v1",
            )
            for name in ("trustInfo", "security", "requestedPrivileges"):
                self.assertEqual(len(document.getElementsByTagName(name)), 1)
        root: ElementTree.Element = ElementTree.fromstring(manifest)
        namespaces: dict[str, str] = {
            "asm": "urn:schemas-microsoft-com:asm.v1",
            "trust": "urn:schemas-microsoft-com:asm.v3",
            "compat": "urn:schemas-microsoft-com:compatibility.v1",
            "dpi": "http://schemas.microsoft.com/SMI/2016/WindowsSettings",
        }
        identity: ElementTree.Element | None = root.find(
            "asm:assemblyIdentity", namespaces
        )
        self.assertIsNotNone(identity)
        if identity is not None:
            self.assertEqual(identity.get("version"), "2.3.4.0")
            self.assertEqual(identity.get("processorArchitecture"), "amd64")
        levels: list[ElementTree.Element] = root.findall(
            "trust:trustInfo/trust:security/trust:requestedPrivileges/"
            "trust:requestedExecutionLevel", namespaces
        )
        self.assertEqual(len(levels), 1)
        self.assertEqual(levels[0].get("level"), "asInvoker")
        self.assertEqual(levels[0].get("uiAccess"), "false")
        self.assertEqual(
            root.findtext("trust:application/trust:windowsSettings/dpi:dpiAwareness",
                          namespaces=namespaces),
            "PerMonitorV2,PerMonitor",
        )
        self.assertEqual(
            root.findtext("trust:application/trust:windowsSettings/dpi:longPathAware",
                          namespaces=namespaces),
            "true",
        )
        supported: ElementTree.Element | None = root.find(
            "compat:compatibility/compat:application/compat:supportedOS", namespaces
        )
        self.assertIsNotNone(supported)
        if supported is not None:
            self.assertEqual(supported.get("Id"),
                             "{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}")

    def test_application_version_is_staged_without_modifying_template(self) -> None:
        """Release resources use version.py while the original XML stays intact."""
        template: Path = ROOT / "assets/SCRTools.manifest"
        original: bytes = template.read_bytes()
        version: str = read_version(ROOT)
        write_metadata(self.folder, version)
        with minidom.parse(str(self.folder / "SCRTools.manifest")) as document:
            identity: minidom.Element = document.getElementsByTagName(
                "assemblyIdentity"
            )[0]
            self.assertEqual(identity.getAttribute("version"), version + ".0")
        resource: str = (self.folder / "version_info.txt").read_text("utf-8")
        self.assertIn(f"StringStruct('FileVersion', '{version}')", resource)
        self.assertEqual(template.read_bytes(), original)

    def test_missing_assembly_identity_is_rejected(self) -> None:
        """An incomplete template cannot silently produce unversioned output."""
        template_root: Path = self.folder / "source"
        assets: Path = template_root / "assets"
        assets.mkdir(parents=True)
        (assets / "SCRTools.manifest").write_text(
            '<assembly xmlns="urn:schemas-microsoft-com:asm.v1"/>',
            encoding="utf-8",
        )
        with patch("scripts.release_metadata.ROOT", template_root):
            with self.assertRaisesRegex(ValueError, "assemblyIdentity"):
                write_metadata(self.folder / "stage", "2.3.4")


if __name__ == "__main__":
    unittest.main()
