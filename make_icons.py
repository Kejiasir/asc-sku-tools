#!/usr/bin/env python3
"""Build PNG / ICO / ICNS app icons from assets/icon.png."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "assets" / "icon.png"


def main() -> int:
    if not SRC.is_file():
        print(f"missing {SRC}", file=sys.stderr)
        return 1
    image = Image.open(SRC).convert("RGBA")
    (ROOT / "assets").mkdir(exist_ok=True)
    image.resize((256, 256), Image.Resampling.LANCZOS).save(ROOT / "assets" / "icon_256.png")

    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    image.save(
        ROOT / "assets" / "icon.ico",
        sizes=ico_sizes,
        format="ICO",
    )

    if sys.platform == "darwin":
        iconset = ROOT / "assets" / "AppIcon.iconset"
        if iconset.exists():
            shutil.rmtree(iconset)
        iconset.mkdir()
        specs = [
            (16, "icon_16x16.png"),
            (32, "icon_16x16@2x.png"),
            (32, "icon_32x32.png"),
            (64, "icon_32x32@2x.png"),
            (128, "icon_128x128.png"),
            (256, "icon_128x128@2x.png"),
            (256, "icon_256x256.png"),
            (512, "icon_256x256@2x.png"),
            (512, "icon_512x512.png"),
            (1024, "icon_512x512@2x.png"),
        ]
        for size, name in specs:
            image.resize((size, size), Image.Resampling.LANCZOS).save(iconset / name)
        icns = ROOT / "assets" / "AppIcon.icns"
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)], check=True)
        shutil.rmtree(iconset)
        print(f"wrote {icns}")

    print(f"wrote {ROOT / 'assets' / 'icon.ico'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
