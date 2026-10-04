#!/usr/bin/env python3
"""Fetch the official Ubuntu Jammy cloud image and verify its HTTPS checksum."""

import argparse
import hashlib
import time
import urllib.request
from pathlib import Path

BASE = 'https://cloud-images.ubuntu.com/jammy/current/'
NAME = 'jammy-server-cloudimg-amd64.img'


def checksum(path):
    """Hash a local image without reading the whole file into memory."""
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    """Preview by default; download and verify to a dedicated directory on apply."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = args.output_dir.expanduser().resolve()
    if root in (Path('/'), Path('/home'), Path('/tmp')):
        parser.error('Use a dedicated image-cache directory')
    print(f'Official image: {BASE}{NAME}\nOutput: {root}')
    if not args.apply:
        print('Preview only. Add --apply to download; no files changed.')
        return
    root.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(BASE + 'SHA256SUMS', timeout=30) as response:
        sums = response.read(1024 * 1024).decode()
    expected = next(line.split()[0] for line in sums.splitlines() if line.split()[-1].lstrip('*') == NAME)
    image = root / NAME
    if image.exists():
        if checksum(image) != expected:
            raise RuntimeError('Existing image differs from current checksum; use a new output directory or supply its original pinned checksum to provision_lab.py')
    else:
        partial = root / (NAME + '.partial')
        start = last = time.monotonic()
        downloaded = 0
        with urllib.request.urlopen(BASE + NAME, timeout=30) as response, partial.open('wb') as handle:
            while True:
                if time.monotonic() - start > 900:
                    raise TimeoutError('Image download exceeded 15 minutes')
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if time.monotonic() - last >= 30:
                    print(f'Downloaded {downloaded // (1024 * 1024)} MiB', flush=True)
                    last = time.monotonic()
        if checksum(partial) != expected:
            raise RuntimeError('Downloaded image checksum mismatch; partial file retained for inspection')
        partial.replace(image)
    (root / (NAME + '.sha256')).write_text(expected + '\n')
    print(f'Verified SHA-256: {expected}\nImage: {image}')


if __name__ == '__main__':
    main()
