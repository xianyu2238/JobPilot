"""Install a pinned, verified Windows Tectonic binary inside this project."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import platform
import zipfile

import httpx

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.17.0"
URL = "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.17.0/tectonic-0.17.0-x86_64-pc-windows-msvc.zip"
DIGEST = "f61ce51f0b0ade1015b7de7ef368541c5424e9756ecbd0d7af97d6d48030845f"
SIZE = 21060223


def download(proxy: str) -> bytes:
    # Bounded range requests avoid long stalled transfers on some proxies.
    step = 1024 * 1024
    def chunk(index):
        start, end = index * step, min(SIZE - 1, (index + 1) * step - 1)
        for attempt in range(3):
            try:
                with httpx.Client(proxy=proxy or None, timeout=60, follow_redirects=True) as client:
                    response = client.get(URL, headers={"Range": f"bytes={start}-{end}"})
                    response.raise_for_status()
                    if response.status_code != 206 or response.headers.get("content-range") != f"bytes {start}-{end}/{SIZE}":
                        raise ValueError("Unexpected download range")
                    if len(response.content) != end - start + 1:
                        raise ValueError("Incomplete download range")
                    return index, response.content
            except (httpx.HTTPError, ValueError):
                if attempt == 2:
                    raise
    parts = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for future in as_completed([pool.submit(chunk, index) for index in range((SIZE + step - 1) // step)]):
            index, content = future.result()
            parts[index] = content
            print(f"Downloaded {len(parts)}/21 parts", flush=True)
    return b"".join(parts[index] for index in range(len(parts)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proxy", default="", help="Optional proxy for downloading public binaries")
    args = parser.parse_args()
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise SystemExit("Install Tectonic or XeLaTeX for your platform and configure JOBPILOT_LATEX_BINARY.")
    target = ROOT / ".tools" / "tectonic"
    binary = target / "tectonic.exe"
    if binary.exists():
        print("Project Tectonic already installed:", binary)
        return
    print("Downloading official Tectonic", VERSION, flush=True)
    content = download(args.proxy)
    if sha256(content).hexdigest() != DIGEST:
        raise SystemExit("Binary archive checksum mismatch; nothing installed.")
    with zipfile.ZipFile(BytesIO(content)) as archive:
        member = next(name for name in archive.namelist() if Path(name).name == "tectonic.exe")
        target.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(archive.read(member))
    (target / "INSTALL.json").write_text(json.dumps({"version": VERSION, "url": URL, "archive_sha256": DIGEST}, indent=2), encoding="utf-8")
    print("Installed and checksum verified:", binary, flush=True)


if __name__ == "__main__":
    main()
