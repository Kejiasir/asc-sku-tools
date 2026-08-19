#!/usr/bin/env python3
"""Build a clickable desktop app for the current operating system.

macOS   -> dist/ASC SKU.app + dist/ASC-SKU-macos.zip
Windows -> dist/ASC-SKU-windows.zip
        -> dist/ASC-SKU-Setup-<version>.exe  (if Inno Setup is installed)

Must be run on the target OS. PyInstaller cannot cross-compile.

Never bundles .p8 / .env. Recipients fill App Store Connect credentials
on first launch; they are stored in the user data directory.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEPARATOR = ";" if sys.platform == "win32" else ":"
APP_NAME = "ASC SKU"


def app_version() -> str:
    return os.environ.get("APP_VERSION", "1.0.0").strip() or "1.0.0"


def _run_pyinstaller() -> Path:
    icon = ROOT / "assets" / ("icon.ico" if sys.platform == "win32" else "AppIcon.icns")
    if not icon.is_file():
        subprocess.run([sys.executable, str(ROOT / "make_icons.py")], check=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--collect-all",
        "customtkinter",
        "--hidden-import",
        "gui",
        "--add-data",
        f"projects{SEPARATOR}projects",
        "--add-data",
        f"assets{SEPARATOR}assets",
        str(ROOT / "create_subscriptions.py"),
    ]
    if icon.is_file():
        command.extend(["--icon", str(icon)])
    if sys.platform == "darwin":
        command.extend(["--osx-bundle-identifier", "com.arvin.asc-sku"])
    subprocess.run(command, cwd=ROOT, check=True)
    if sys.platform == "darwin":
        return ROOT / "dist" / f"{APP_NAME}.app"
    return ROOT / "dist" / APP_NAME / f"{APP_NAME}.exe"


def _package_windows(exe: Path) -> None:
    dist_dir = exe.parent
    archive = ROOT / "dist" / "ASC-SKU-windows"
    zip_path = archive.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(str(archive), "zip", dist_dir)
    print(f"portable zip: {zip_path}")

    iscc_candidates = [
        shutil.which("iscc"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    iscc = next((item for item in iscc_candidates if item and Path(item).is_file()), None)
    iss = ROOT / "packaging" / "windows.iss"
    if iscc and iss.is_file():
        subprocess.run([iscc, f"/DMyAppVersion={app_version()}", str(iss)], cwd=ROOT, check=True)
        print(f"installer: {ROOT / 'dist' / f'ASC-SKU-Setup-{app_version()}.exe'}")
    else:
        print("Inno Setup not found; zip is ready. Install Inno Setup to also get ASC-SKU-Setup.exe.")


def _package_macos(app: Path) -> None:
    zip_path = ROOT / "dist" / "ASC-SKU-macos.zip"
    if zip_path.exists():
        zip_path.unlink()
    subprocess.run(["ditto", "-c", "-k", "--keepParent", str(app), str(zip_path)], check=True)
    print(f"app zip: {zip_path}")
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        return
    applications = Path.home() / "Applications"
    applications.mkdir(exist_ok=True)
    target = applications / f"{APP_NAME}.app"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(app, target)
    print(f"copied to {target}")


def main() -> int:
    built = _run_pyinstaller()
    if not built.exists():
        raise SystemExit(f"build output missing: {built}")
    print(f"built {built}")
    if sys.platform == "win32":
        _package_windows(built)
        return 0
    if sys.platform == "darwin":
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(built)], check=False)
        _package_macos(built)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
