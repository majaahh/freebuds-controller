#!/usr/bin/env python3
# Copyright (c) 2026 Majaahh
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import hashlib
import struct
import zipfile
from pathlib import Path


IMAGE_SHA256 = "f545bfa894895dfbc3d53b76ca0d61b42d0c9a980c14113cc9d7d99affa97a4d"
ZIP_MEMBER = "data/accessory/firmware/para_data/firmware/btft0014/updatepkg.bin"


def extract(image):
    if hashlib.sha256(image).hexdigest() != IMAGE_SHA256:
        raise ValueError(
            "Expected the FreeBuds 5i 2.1.0.218(F001H003C00) firmware image"
        )

    files = {}
    offset = 0x44C
    for entry in range(0xB4, 0x174, 48):
        component = int.from_bytes(image[entry : entry + 2], "big")
        size = struct.unpack_from(">I", image, entry + 12)[0]
        data = image[offset : offset + size]
        files[f"component-{component:02d}.bin"] = data
        offset += size

    bundle = files["component-06.bin"]
    count = struct.unpack_from(">H", bundle, 16)[0]
    for idx in range(count):
        entry = 18 + idx * 70
        name = bundle[entry : entry + 16].rstrip(b"\0").decode("ascii")
        start, size = struct.unpack_from(">II", bundle, entry + 30)
        files[f"mcu/{name}.bin"] = bundle[start : start + size]

    romfs = files["component-07.bin"]
    offset = 32
    while offset:
        next_entry, _, size, _ = struct.unpack_from(">IIII", romfs, offset)
        end = romfs.index(0, offset + 16)
        if next_entry & 7 == 2:
            name = romfs[offset + 16 : end].decode("ascii")
            start = (end + 16) & ~15
            files[f"prompts/{name}"] = romfs[start : start + size]
        offset = next_entry & ~15
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Extract FreeBuds 5i build 2.1.0.218(F001H003C00)"
    )
    parser.add_argument("package", type=Path, help="Official OTA ZIP or updatepkg.bin")
    parser.add_argument("-o", type=Path, required=True, help="New output directory")
    args = parser.parse_args()
    try:
        if zipfile.is_zipfile(args.package):
            with zipfile.ZipFile(args.package) as archive:
                image = archive.read(ZIP_MEMBER)
        else:
            image = args.package.read_bytes()
        files = extract(image)
        args.o.mkdir(parents=True, exist_ok=False)
        for name, data in files.items():
            path = args.o / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        print(f"Extracted {len(files)} files to {args.o}")
    except (KeyError, OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Extraction failed: {exc}\n")


if __name__ == "__main__":
    main()
