#!/usr/bin/env python3
"""Build a compact Windows setup from the patched PyInstaller application.

The setup reuses the application's bootloader and bundled Python/Tk runtime.
Only the top-level ``run`` script is replaced with the installer UI.  During
installation it restores the audited original ``run`` payload, producing an
installed executable that is byte-for-byte identical to the patched app.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import marshal
from pathlib import Path
import struct
import zlib


COOKIE_MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"
COOKIE = struct.Struct("!8sIIII64s")
TOC_HEADER = struct.Struct("!iIIIBc")


def parse_archive(blob: bytes):
    cookie_pos = blob.rfind(COOKIE_MAGIC)
    if cookie_pos < 0 or cookie_pos + COOKIE.size != len(blob):
        raise ValueError("PyInstaller cookie not found")
    magic, package_len, toc_pos, toc_len, pyver, pylib = COOKIE.unpack_from(blob, cookie_pos)
    if pyver != 312:
        raise ValueError(f"expected Python 3.12 package, found {pyver}")
    archive_start = cookie_pos + COOKIE.size - package_len
    cursor = archive_start + toc_pos
    end = cursor + toc_len
    entries = []
    while cursor < end:
        entry_size, pos, csize, usize, compressed, typecode = TOC_HEADER.unpack_from(blob, cursor)
        if entry_size < TOC_HEADER.size or cursor + entry_size > end:
            raise ValueError("invalid CArchive TOC")
        name = (
            blob[cursor + TOC_HEADER.size : cursor + entry_size]
            .split(b"\0", 1)[0]
            .decode("utf-8", "surrogateescape")
        )
        entries.append(
            {
                "entry_start": cursor,
                "entry_size": entry_size,
                "pos": pos,
                "csize": csize,
                "usize": usize,
                "compressed": compressed,
                "typecode": typecode,
                "name": name,
            }
        )
        cursor += entry_size
    return {
        "cookie_pos": cookie_pos,
        "archive_start": archive_start,
        "toc_pos": toc_pos,
        "toc_len": toc_len,
        "magic": magic,
        "pyver": pyver,
        "pylib": pylib,
        "entries": entries,
    }


def unpack_entry(blob: bytes, archive_start: int, entry: dict) -> bytes:
    start = archive_start + entry["pos"]
    stored = blob[start : start + entry["csize"]]
    return zlib.decompress(stored) if entry["compressed"] else stored


def replace_run(blob: bytes, raw_run: bytes) -> bytes:
    archive = parse_archive(blob)
    archive_start = archive["archive_start"]
    found = False
    rebuilt = bytearray(blob[:archive_start])
    rebuilt_toc = bytearray()
    for entry in archive["entries"]:
        if entry["name"] == "run" and entry["typecode"] == b"s":
            stored = zlib.compress(raw_run, level=9)
            uncompressed_size = len(raw_run)
            compressed = 1
            found = True
        else:
            start = archive_start + entry["pos"]
            stored = blob[start : start + entry["csize"]]
            uncompressed_size = entry["usize"]
            compressed = entry["compressed"]

        new_pos = len(rebuilt) - archive_start
        rebuilt.extend(stored)
        toc_entry = bytearray(blob[entry["entry_start"] : entry["entry_start"] + entry["entry_size"]])
        struct.pack_into("!I", toc_entry, 4, new_pos)
        struct.pack_into("!I", toc_entry, 8, len(stored))
        struct.pack_into("!I", toc_entry, 12, uncompressed_size)
        struct.pack_into("!B", toc_entry, 16, compressed)
        rebuilt_toc.extend(toc_entry)

    if not found:
        raise ValueError("top-level run script not found")
    new_toc_pos = len(rebuilt) - archive_start
    rebuilt.extend(rebuilt_toc)
    new_package_len = len(rebuilt) + COOKIE.size - archive_start
    rebuilt.extend(
        COOKIE.pack(
            archive["magic"],
            new_package_len,
            new_toc_pos,
            len(rebuilt_toc),
            archive["pyver"],
            archive["pylib"],
        )
    )
    return bytes(rebuilt)


def build_setup(application: Path, template: Path, output: Path) -> tuple[str, str]:
    app_blob = application.read_bytes()
    archive = parse_archive(app_blob)
    run_entry = next(
        (entry for entry in archive["entries"] if entry["name"] == "run" and entry["typecode"] == b"s"),
        None,
    )
    if run_entry is None:
        raise ValueError("application run script was not found")
    original_run = unpack_entry(app_blob, archive["archive_start"], run_entry)

    source = template.read_text(encoding="utf-8")
    marker = "__APP_RUN_PAYLOAD_B64__"
    if source.count(marker) != 1:
        raise ValueError("setup template must contain exactly one run-payload marker")
    source = source.replace(marker, base64.b64encode(original_run).decode("ascii"))
    installer_code = compile(source, "setup_entry.py", "exec", dont_inherit=True, optimize=0)
    installer_run = marshal.dumps(installer_code)
    setup_blob = replace_run(app_blob, installer_run)

    # Reproduce what the installer does and require exact application recovery.
    restored_blob = replace_run(setup_blob, original_run)
    if restored_blob != app_blob:
        raise ValueError("setup self-restoration check failed")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(setup_blob)
    return hashlib.sha256(setup_blob).hexdigest(), hashlib.sha256(app_blob).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("application", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).with_name("setup_entry.py.in"),
    )
    args = parser.parse_args()
    setup_sha, app_sha = build_setup(args.application, args.template, args.output)
    print(f"Setup: {args.output}")
    print(f"Setup SHA256: {setup_sha}")
    print(f"Installed app SHA256: {app_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
