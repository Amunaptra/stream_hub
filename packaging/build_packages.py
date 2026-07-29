from __future__ import annotations

import argparse
import hashlib
import shutil
import tarfile
import tempfile
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PACKAGE_CONTENT = {
    "odroid": (
        "stream-hub-odroid",
        [
            "device/agent",
            "device/installer",
            "device/player",
            "pyproject.toml",
            "requirements-device.txt",
        ],
    ),
    "hub": (
        "stream-hub-server",
        [
            "hub/backend",
            "hub/container",
            "hub/installer",
            "hub/ui",
        ],
    ),
}


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def copy_entry(relative: str, package_root: Path) -> None:
    source = ROOT / relative
    target = package_root / relative
    if source.is_dir():
        shutil.copytree(
            source,
            target,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(package_root: Path) -> None:
    files = sorted(path for path in package_root.rglob("*") if path.is_file())
    lines = [
        f"{file_hash(path)}  {path.relative_to(package_root).as_posix()}"
        for path in files
    ]
    (package_root / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    if info.isfile():
        info.mode = 0o755 if info.name.endswith(".sh") else 0o644
    elif info.isdir():
        info.mode = 0o755
    return info


def build(package: str, output_dir: Path, version: str) -> Path:
    archive_prefix, entries = PACKAGE_CONTENT[package]
    folder_name = f"{archive_prefix}-{version}"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"{folder_name}.tar.gz"
    with tempfile.TemporaryDirectory(prefix="stream-hub-package-") as temporary:
        package_root = Path(temporary) / folder_name
        package_root.mkdir()
        for entry in entries:
            copy_entry(entry, package_root)
        shutil.copy2(ROOT / "packaging" / package / "install.sh", package_root / "install.sh")
        shutil.copy2(ROOT / "packaging" / package / "README.md", package_root / "README.md")
        write_manifest(package_root)
        with tarfile.open(archive, "w:gz") as bundle:
            bundle.add(package_root, arcname=folder_name, filter=tar_filter)
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description="Build independent Stream Hub installers")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--version", default=project_version())
    parser.add_argument(
        "--package", choices=["all", *PACKAGE_CONTENT], default="all"
    )
    args = parser.parse_args()

    selected = PACKAGE_CONTENT if args.package == "all" else [args.package]
    archives = [build(name, args.output_dir.resolve(), args.version) for name in selected]
    checksum_file = args.output_dir.resolve() / "SHA256SUMS"
    checksum_file.write_text(
        "".join(f"{file_hash(path)}  {path.name}\n" for path in archives),
        encoding="utf-8",
    )
    for path in archives:
        print(path)
    print(checksum_file)


if __name__ == "__main__":
    main()
