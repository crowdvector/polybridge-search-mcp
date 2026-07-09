#!/usr/bin/env python3
"""Build the local PolyBridge MCPB package without publishing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATHS = (
    Path("manifest.json"),
    Path("pyproject.toml"),
    Path("assets/icon.png"),
    Path("src/polybridge_mcp_server"),
    Path("src/polybridge_contracts"),
)
EXCLUDED_PARTS = {"__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a local .mcpb package and .sha256 sidecar."
    )
    parser.add_argument(
        "--dist-dir",
        default="dist",
        help="Output directory for the local package artifacts.",
    )
    args = parser.parse_args()

    manifest = _read_manifest()
    project = _read_pyproject()
    version = _resolve_version(manifest, project)
    package_name = manifest["name"]
    artifact_name = f"{package_name}-v{version}.mcpb"
    dist_dir = Path(args.dist_dir)
    if not dist_dir.is_absolute():
        dist_dir = ROOT / dist_dir
    dist_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = dist_dir / artifact_name
    checksum_path = dist_dir / f"{artifact_name}.sha256"
    package_files = list(_iter_package_files())

    with zipfile.ZipFile(
        artifact_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as package:
        for relative_path in package_files:
            package.write(ROOT / relative_path, relative_path.as_posix())

    digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    checksum_path.write_text(f"{digest}  {artifact_name}\n", encoding="utf-8")

    print(artifact_path)
    print(checksum_path)
    print(digest)
    return 0


def _read_manifest() -> dict:
    with (ROOT / "manifest.json").open(encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest.get("name"), str) or not manifest["name"]:
        raise ValueError("manifest.json must define a package name")
    if not isinstance(manifest.get("version"), str) or not manifest["version"]:
        raise ValueError("manifest.json must define a version")
    return manifest


def _read_pyproject() -> dict:
    in_project = False
    for raw_line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line == "[project]":
            in_project = True
            continue
        if line.startswith("[") and line.endswith("]"):
            in_project = False
        if not in_project or not line.startswith("version"):
            continue
        key, separator, value = line.partition("=")
        if separator and key.strip() == "version":
            return {"project": {"version": value.strip().strip('"')}}
    raise ValueError("pyproject.toml must define project.version")


def _resolve_version(manifest: dict, pyproject: dict) -> str:
    manifest_version = manifest["version"]
    project_version = pyproject.get("project", {}).get("version")
    if manifest_version != project_version:
        raise ValueError(
            "manifest.json version must match pyproject.toml project.version"
        )
    return manifest_version


def _iter_package_files() -> list[Path]:
    files: list[Path] = []
    for package_path in PACKAGE_PATHS:
        absolute_path = ROOT / package_path
        if not absolute_path.exists():
            raise FileNotFoundError(package_path)
        if absolute_path.is_file():
            files.append(package_path)
            continue
        for file_path in sorted(absolute_path.rglob("*")):
            if not file_path.is_file():
                continue
            relative_path = file_path.relative_to(ROOT)
            if EXCLUDED_PARTS.intersection(relative_path.parts):
                continue
            if file_path.suffix in EXCLUDED_SUFFIXES:
                continue
            files.append(relative_path)
    return sorted(files)


if __name__ == "__main__":
    raise SystemExit(main())
