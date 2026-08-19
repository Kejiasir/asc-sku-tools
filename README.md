# ASC SKU Tools

Batch-create App Store Connect auto-renewable subscription SKUs. One desktop app, one JSON catalog per app.

**Do not commit** `AuthKey_*.p8`, `.env`, or any App Store Connect private key. Those stay on each person's machine.

## Windows team members

After GitHub Actions finishes, download **ASC-SKU-windows** from the [Actions](https://github.com/Kejiasir/asc-sku-tools/actions) run:

- `ASC-SKU-Setup.exe` — installer (Start Menu + Desktop shortcut)
- `ASC-SKU-windows.zip` — portable folder

First launch: paste Issuer ID and Key ID, choose your `.p8`, then Connect. Credentials are stored in `%APPDATA%\ASC SKU\`, not in the installer.

## macOS (from source)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python create_subscriptions.py
```

Or double-click `ASC SKU.app` after the venv exists.

## GitHub Actions

Push to `main` (or run **Build Windows** manually) to produce the Windows installer. The workflow never receives your `.p8`.
