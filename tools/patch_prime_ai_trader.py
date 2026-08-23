#!/usr/bin/env python3
"""Inject the audited market guard into a PrimeAITrader 0.9.0 executable.

The supplied application is a PyInstaller one-file executable.  This tool keeps
every original archive member byte-for-byte, renames the original signal engine
to ``legacy_engine`` and inserts the two reviewed source modules from this repo.
"""

from __future__ import annotations

import argparse
import marshal
from pathlib import Path
import struct
import zlib


COOKIE_MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"
COOKIE = struct.Struct("!8sIIII64s")
TOC_HEADER = struct.Struct("!iIIIBc")
TARGET = "prime_ai_trader.signals.engine"
LEGACY = "prime_ai_trader.signals.legacy_engine"
GUARD = "prime_ai_trader.signals.market_guard"


def read_carchive_toc(blob: bytes, archive_start: int, toc_pos: int, toc_len: int):
    cursor = archive_start + toc_pos
    end = cursor + toc_len
    while cursor < end:
        entry_start = cursor
        entry_size, pos, csize, usize, compressed, typecode = TOC_HEADER.unpack_from(blob, cursor)
        if entry_size < TOC_HEADER.size or cursor + entry_size > end:
            raise ValueError(f"invalid CArchive TOC entry at {cursor}")
        name = (
            blob[cursor + TOC_HEADER.size : cursor + entry_size]
            .split(b"\0", 1)[0]
            .decode("utf-8", "surrogateescape")
        )
        yield {
            "entry_start": entry_start,
            "entry_size": entry_size,
            "pos": pos,
            "csize": csize,
            "usize": usize,
            "compressed": compressed,
            "typecode": typecode,
            "name": name,
        }
        cursor += entry_size


def read_pyz(data: bytes):
    if data[:4] != b"PYZ\0":
        raise ValueError("PYZ signature not found")
    toc_offset = struct.unpack("!I", data[8:12])[0]
    toc = marshal.loads(data[toc_offset:])
    if not isinstance(toc, list):
        raise ValueError("unsupported PYZ TOC format")
    return toc_offset, toc


def compile_module(path: Path, internal_filename: str) -> bytes:
    source = path.read_text(encoding="utf-8")
    code = compile(source, internal_filename, "exec", dont_inherit=True, optimize=0)
    return zlib.compress(marshal.dumps(code), level=9)


def build_pyz(original: bytes, source_root: Path) -> bytes:
    _, toc = read_pyz(original)
    first_payload = min(pos for _, (kind, pos, length) in toc if length)
    header = bytearray(original[:first_payload])
    rebuilt = bytearray(header)
    new_toc = []
    found_target = False

    for name, (kind, pos, length) in toc:
        if name in {LEGACY, GUARD}:
            raise ValueError(f"executable already contains overlay module {name}")
        output_name = LEGACY if name == TARGET else name
        found_target = found_target or name == TARGET
        if kind == 3 or length == 0:
            new_toc.append((output_name, (kind, len(rebuilt), 0)))
            continue
        payload = original[pos : pos + length]
        new_pos = len(rebuilt)
        rebuilt.extend(payload)
        new_toc.append((output_name, (kind, new_pos, len(payload))))

    if not found_target:
        raise ValueError(f"target module {TARGET} was not found")

    modules = (
        (GUARD, source_root / "prime_ai_trader" / "signals" / "market_guard.py"),
        (TARGET, source_root / "prime_ai_trader" / "signals" / "engine.py"),
    )
    for name, source_path in modules:
        payload = compile_module(source_path, name.replace(".", "/") + ".py")
        pos = len(rebuilt)
        rebuilt.extend(payload)
        new_toc.append((name, (0, pos, len(payload))))

    toc_offset = len(rebuilt)
    rebuilt.extend(marshal.dumps(new_toc))
    struct.pack_into("!I", rebuilt, 8, toc_offset)
    return bytes(rebuilt)


def patch_executable(input_path: Path, output_path: Path, source_root: Path) -> None:
    blob = input_path.read_bytes()
    cookie_pos = blob.rfind(COOKIE_MAGIC)
    if cookie_pos < 0 or cookie_pos + COOKIE.size != len(blob):
        raise ValueError("modern PyInstaller cookie was not found at end of executable")
    magic, package_len, toc_pos, toc_len, pyver, pylib = COOKIE.unpack_from(blob, cookie_pos)
    if pyver != 312:
        raise ValueError(f"expected Python 3.12 executable, found encoded version {pyver}")
    archive_start = cookie_pos + COOKIE.size - package_len
    entries = list(read_carchive_toc(blob, archive_start, toc_pos, toc_len))
    pyz_entry = next((entry for entry in entries if entry["name"].lower().endswith(".pyz")), None)
    if pyz_entry is None:
        raise ValueError("PYZ entry not found in executable")
    pyz_start = archive_start + pyz_entry["pos"]
    pyz_end = pyz_start + pyz_entry["csize"]
    if pyz_end != archive_start + toc_pos:
        raise ValueError("expected PYZ to be the final CArchive data entry")
    original_pyz = blob[pyz_start:pyz_end]
    if pyz_entry["compressed"]:
        original_pyz = zlib.decompress(original_pyz)
    new_pyz = build_pyz(original_pyz, source_root)
    stored_pyz = zlib.compress(new_pyz, level=9) if pyz_entry["compressed"] else new_pyz

    original_toc = bytearray(blob[archive_start + toc_pos : archive_start + toc_pos + toc_len])
    relative_entry = pyz_entry["entry_start"] - (archive_start + toc_pos)
    struct.pack_into("!I", original_toc, relative_entry + 8, len(stored_pyz))
    struct.pack_into("!I", original_toc, relative_entry + 12, len(new_pyz))

    rebuilt = bytearray(blob[:pyz_start])
    rebuilt.extend(stored_pyz)
    new_toc_pos = len(rebuilt) - archive_start
    rebuilt.extend(original_toc)
    new_package_len = len(rebuilt) + COOKIE.size - archive_start
    rebuilt.extend(COOKIE.pack(magic, new_package_len, new_toc_pos, toc_len, pyver, pylib))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(rebuilt)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_exe", type=Path)
    parser.add_argument("output_exe", type=Path)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="directory containing prime_ai_trader/signals/*.py",
    )
    args = parser.parse_args()
    patch_executable(args.input_exe, args.output_exe, args.source_root)
    print(f"Patched executable written to {args.output_exe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
