"""Every Mach-O file under a folder that codesign signs, found by its header rather than its
name: `exe<TAB>path` for an executable, `lib<TAB>path` for a library or a loadable bundle
(a Python extension module is one). Object files and the like are left out.

    macho.py <folder>
"""

import os
import struct
import sys

EXECUTE, DYLIB, BUNDLE = 2, 6, 8
THIN = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"}  # 64- and 32-bit, little-endian
FAT = {b"\xca\xfe\xba\xbe": 20, b"\xca\xfe\xba\xbf": 32}  # the size of one arch entry


def filetype(path: str) -> int | None:
    with open(path, "rb") as handle:
        head = handle.read(8)
        if head[:4] in THIN:
            handle.seek(12)
            return struct.unpack("<I", handle.read(4))[0]
        if head[:4] in FAT:
            count = struct.unpack(">I", head[4:8])[0]
            # Java class files share the fat magic; their next field is a version, not a
            # count of architectures.
            if not 0 < count < 16:
                return None
            entry = handle.read(FAT[head[:4]])
            offset = struct.unpack(">I", entry[8:12])[0] if len(entry) == 20 else struct.unpack(">Q", entry[8:16])[0]
            handle.seek(offset)
            if handle.read(4) not in THIN:
                return None
            handle.seek(offset + 12)
            return struct.unpack("<I", handle.read(4))[0]
    return None


def main() -> None:
    for folder, _, files in os.walk(sys.argv[1]):
        for name in sorted(files):
            path = os.path.join(folder, name)
            if os.path.islink(path) or os.path.getsize(path) < 32:
                continue
            kind = filetype(path)
            if kind == EXECUTE:
                print(f"exe\t{path}")
            elif kind in (DYLIB, BUNDLE):
                print(f"lib\t{path}")


if __name__ == "__main__":
    main()
