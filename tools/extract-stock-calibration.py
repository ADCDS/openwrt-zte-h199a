#!/usr/bin/env python3
"""Extract original calibration files from a supported H199A stock bank, offline.

Inputs must come from the owner's own router. Supports the hash-identified
July 2021 stock firmware; other versions are rejected. No flash or network I/O.
Key bytes are derived from the supplied kernel and never printed or saved.
The output directory must be new. Extracted vendor files are not part of this
source repository and should remain with the owner's private backups.
"""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
import collections
import ctypes
import ctypes.util
import hashlib
import json
from pathlib import Path
import struct
import zlib

KERNEL_SHA = "b3b1434a6996c9de266c6db68014889f9f0836a3a53be9145ce7af9a62ae1b64"
PLAIN_SHA = "109d9732f7c2f4dcd4c2b6b74539bb846664ff8442d926d8d24b2f70102ba893"
BASE = 0xc0008000
RAW_SIZE = 6087328
GZIP_OFFSET = 0x6608


def load_kernel(data):
    """Accept verified raw vmlinux or its original 3 MiB bank wrapper."""
    if len(data) == 3 * 1024 * 1024:
        header = bytearray(data[32:96])
        magic, hcrc, _, size, load, entry, dcrc = struct.unpack_from(">7I", header)
        require(magic == 0x27051956 and load == entry == 0x40008000,
                "unexpected stock uImage header")
        require(header[28:32] == bytes((5, 2, 2, 0)), "unsupported uImage format")
        struct.pack_into(">I", header, 4, 0)
        require(zlib.crc32(header) == hcrc, "kernel header CRC mismatch")
        payload = data[96:96 + size]
        require(len(payload) == size and zlib.crc32(payload) == dcrc,
                "kernel payload CRC mismatch")
        require(size > GZIP_OFFSET - 96, "kernel payload is too short")
        decoder = zlib.decompressobj(31)
        data = decoder.decompress(payload[GZIP_OFFSET - 96:], RAW_SIZE + 1)
        require(decoder.eof and len(data) == RAW_SIZE, "invalid or oversized kernel gzip")
    require(len(data) == RAW_SIZE and hashlib.sha256(data).hexdigest() == KERNEL_SHA,
            "unsupported kernel; no offsets or keys were guessed")
    return data


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save(path, data):
    # Existing evidence must agree; never silently replace a differing artifact.
    if path.exists():
        require(path.read_bytes() == data, "existing output differs: " + path.name)
    else:
        with path.open("xb") as stream:
            stream.write(data)
    path.chmod(0o600)


def crc(data):
    return zlib.crc32(data, 0xffffffff) ^ 0xffffffff


def decrypt(kernel, encrypted):
    def cstr(address):
        offset = address - BASE
        return kernel[offset:kernel.index(b"\0", offset)]

    # combine_token @ c000bf60: sprintf then swaps [5..9] with [15..11].
    require(cstr(0xc04f82ac) == b"%s%s", "unexpected key construction format")
    key = bytearray(cstr(0xc04f82ac) % (cstr(0xc04da35c), cstr(0xc04da364)))
    require(len(key) == 16, "unexpected key length")
    for index in range(5):
        key[5 + index], key[15 - index] = key[15 - index], key[5 + index]

    # part_read @ c01e5ff8 calls decry_buf @ c01e5f44 per 2048-byte page.
    # The latter invokes AES_set_decrypt_key(128), then AES_decrypt per block.
    crypto = ctypes.util.find_library("crypto")
    require(crypto is not None, "OpenSSL libcrypto is required")
    library = ctypes.CDLL(crypto)
    library.EVP_CIPHER_CTX_new.restype = ctypes.c_void_p
    library.EVP_aes_128_ecb.restype = ctypes.c_void_p
    library.EVP_DecryptInit_ex.argtypes = [ctypes.c_void_p] * 5
    library.EVP_CIPHER_CTX_set_padding.argtypes = [ctypes.c_void_p, ctypes.c_int]
    library.EVP_DecryptUpdate.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int), ctypes.c_void_p, ctypes.c_int]
    library.EVP_DecryptFinal_ex.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int)]
    library.EVP_CIPHER_CTX_free.argtypes = [ctypes.c_void_p]
    context = library.EVP_CIPHER_CTX_new()
    require(bool(context), "cipher context allocation failed")
    try:
        require(library.EVP_DecryptInit_ex(context, library.EVP_aes_128_ecb(),
            None, ctypes.create_string_buffer(bytes(key)), None) == 1, "cipher init failed")
        require(library.EVP_CIPHER_CTX_set_padding(context, 0) == 1, "padding setup failed")
        output = ctypes.create_string_buffer(len(encrypted) + 16)
        length = ctypes.c_int()
        require(library.EVP_DecryptUpdate(context, output, ctypes.byref(length),
            ctypes.create_string_buffer(encrypted), len(encrypted)) == 1, "decryption failed")
        tail = ctypes.create_string_buffer(16)
        tail_length = ctypes.c_int()
        require(library.EVP_DecryptFinal_ex(context, tail, ctypes.byref(tail_length)) == 1,
            "decryption finalization failed")
        return output.raw[:length.value] + tail.raw[:tail_length.value]
    finally:
        library.EVP_CIPHER_CTX_free(context)


def extract(image, output_dir):
    directories = {}
    inodes = collections.defaultdict(list)
    counts = collections.Counter()
    position = 0
    while position + 12 <= len(image):
        if image[position:position + 2] != b"\x85\x19":
            position += 4
            continue
        _, kind, size, header_crc = struct.unpack_from("<HHII", image, position)
        require(size >= 12 and position + size <= len(image), "invalid JFFS2 node size")
        node = image[position:position + size]
        require(crc(node[:8]) == header_crc, "JFFS2 header CRC mismatch")
        if kind == 0xe001:
            require(size >= 40, "short directory node")
            parent, version, inode, _, name_size, dtype = struct.unpack_from("<IIIIBB", node, 12)
            node_crc, name_crc = struct.unpack_from("<II", node, 32)
            name = node[40:40 + name_size]
            require(len(name) == name_size, "short directory name")
            require(crc(node[:32]) == node_crc and crc(name) == name_crc, "dirent CRC mismatch")
            previous = directories.get((parent, name))
            if previous is None or version > previous[0]:
                directories[parent, name] = version, inode, dtype
            counts["dirent_crc_ok"] += 1
        elif kind == 0xe002:
            require(size >= 68, "short inode node")
            inode, version = struct.unpack_from("<II", node, 12)
            file_size = struct.unpack_from("<I", node, 28)[0]
            offset, compressed_size, data_size = struct.unpack_from("<III", node, 44)
            compression = node[56]
            data_crc, node_crc = struct.unpack_from("<II", node, 60)
            data = node[68:68 + compressed_size]
            require(len(data) == compressed_size and data_size <= 4 * 1024 * 1024,
                    "invalid inode data length")
            require(crc(node[:60]) == node_crc and crc(data) == data_crc, "inode CRC mismatch")
            inodes[inode].append((version, file_size, offset, data_size, compression, data))
            counts["inode_crc_ok"] += 1
        position += (size + 3) & ~3

    paths = {1: "/"}
    for _ in range(30):
        previous_count = len(paths)
        for (parent, name), (_, inode, _) in directories.items():
            if parent in paths and inode and inode not in paths:
                paths[inode] = paths[parent].rstrip("/") + "/" + name.decode()
        if len(paths) == previous_count:
            break

    wanted = {"/etc/Wireless/MT7603e/MT7603E_EEPROM.bin",
        "/etc/Wireless/MT7613E/MT7613E_EEPROM.bin", "/lib/modules/mt7603eap.ko"}
    results = []
    files = []
    for inode, path in paths.items():
        if path not in wanted:
            continue
        fragments = sorted(inodes[inode])
        require(bool(fragments), "file has no data fragments")
        size = fragments[-1][1]
        require(0 < size <= 4 * 1024 * 1024, "invalid target file size")
        output, coverage = bytearray(size), bytearray(size)
        for _, _, offset, data_size, compression, data in fragments:
            require(compression in (0, 6), "unsupported JFFS2 compression")
            if compression == 6:
                decoder = zlib.decompressobj()
                data = decoder.decompress(data, data_size + 1)
                require(decoder.eof, "invalid or oversized compressed fragment")
            require(len(data) == data_size, "decompressed fragment length mismatch")
            end = min(size, offset + len(data))
            if offset < end:
                output[offset:end] = data[:end - offset]
                coverage[offset:end] = b"\x01" * (end - offset)
        require(all(coverage), "incomplete file coverage")
        files.append((Path(path).name, bytes(output)))
        result = {"path": path, "size": size,
            "sha256": hashlib.sha256(output).hexdigest(), "fragments": len(fragments)}
        results.append(result)
        wanted.remove(path)
    require(not wanted, "requested vendor files missing")
    # Validate every target before creating output. A disk error may still
    # leave partial files, but verification.json is written only after success.
    output_dir.mkdir(mode=0o700)
    for name, data in files:
        save(output_dir / name, data)
    return {"files": results, "validation": counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kernel", type=Path, help="corrected stock kernel bank or raw vmlinux")
    parser.add_argument("rootfs", type=Path, help="complete corrected encrypted stock filesystem")
    parser.add_argument("output", type=Path, help="new private output directory")
    args = parser.parse_args()
    require(not args.output.exists(), "output directory already exists")
    require(args.kernel.stat().st_size in (3 * 1024 * 1024, RAW_SIZE),
            "unexpected kernel input size")
    require(args.rootfs.stat().st_size == 13762560, "incomplete stock filesystem")
    kernel = load_kernel(args.kernel.read_bytes())
    encrypted = args.rootfs.read_bytes()
    require(len(encrypted) == 13762560 and zlib.crc32(encrypted) == 0x7bc2f9e9,
        "encrypted filesystem does not match verified bank B")
    plain = decrypt(kernel, encrypted)
    require(hashlib.sha256(plain).hexdigest() == PLAIN_SHA, "decrypted filesystem mismatch")
    result = extract(plain, args.output)
    result.update({"kernel_sha256": KERNEL_SHA, "decrypted_filesystem_sha256": PLAIN_SHA,
                   "encrypted_filesystem_sha256": hashlib.sha256(encrypted).hexdigest()})
    save(args.output / "verification.json", (json.dumps(result, indent=2) + "\n").encode())
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, zlib.error) as error:
        raise SystemExit(f"calibration extraction failed: {error}")
