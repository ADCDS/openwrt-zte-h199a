// SPDX-License-Identifier: GPL-2.0
/*
 * h199a-header-regen — rewrite the bank-A header CRCs from what is on flash.
 *
 * The bootloader checks exactly three words in the 128 KiB header block:
 *
 *   +0x3c   CRC-32 of the kernel data, kernel[0x20 .. 0x20+0x2ffdcc]
 *   +0x48   CRC-32 of the filesystem image, rootfs[0 .. 0xd20000]
 *   +0xa4   CRC-32 of hdr[0 .. 0xa4]  (must be computed last: the two above
 *           live inside that range)
 *
 * Every other byte is device-specific — vendor fields, the version string, the
 * upgrade keys, the bank start, the version serial at +0x1f4 — and must be
 * preserved from the unit's own header. That is why this tool takes the
 * header from the board rather than shipping one built from somebody else's
 * unit, and it is what lets a single public image install on every unit.
 *
 * Usage:
 *   h199a-header-regen <header-blk> <kernel-part> <rootfs-part> [<output>]
 *
 * With no <output> the header block is rewritten in place. The header is read
 * in full first, so a failure part-way through cannot leave a half-patched
 * block: either the whole 128 KiB is written or nothing is.
 *
 * Builds for the host too, which is how tests/ proves it agrees byte for byte
 * with tools/flash-prep.py.
 */
#define _FILE_OFFSET_BITS 64

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define HEADER_BLK	0x20000u	/* one erase block */
#define HDR_KERNEL_CRC	0x3c
#define HDR_FS_CRC	0x48
#define HDR_SELF_CRC	0xa4
#define HDR_CRC_LEN	0xa4		/* the self-CRC covers hdr[0:0xa4] */
#define KERNEL_SKIP	0x20u		/* the kernel data starts past the tag */
#define CRC_LEN		0x2ffdccu	/* kernel data CRC length */
#define FS_LEN		0xd20000u	/* fixed filesystem size */

/* The usual reflected CRC-32 (poly 0xEDB88320, init and xorout 0xffffffff),
 * i.e. what zlib's crc32() computes. Written out rather than tabulated so this
 * file has no table to get wrong, and it runs once per upgrade.
 */
static uint32_t crc32_update(uint32_t crc, const unsigned char *buf, size_t len)
{
	size_t i;
	int b;

	for (i = 0; i < len; i++) {
		crc ^= buf[i];
		for (b = 0; b < 8; b++)
			crc = (crc >> 1) ^ (0xedb88320u & (~(crc & 1u) + 1u));
	}
	return crc;
}

static uint32_t crc32_of(const unsigned char *buf, size_t len)
{
	return crc32_update(0xffffffffu, buf, len) ^ 0xffffffffu;
}

/* Read exactly `len` bytes from `fd` at `off`. Returns 0 or -errno. */
static int read_at(int fd, unsigned long long off, void *buf, size_t len)
{
	unsigned char *p = buf;
	size_t done = 0;

	while (done < len) {
		ssize_t n = pread(fd, p + done, len - done, (off_t)(off + done));

		if (n < 0) {
			if (errno == EINTR)
				continue;
			return -errno;
		}
		if (n == 0)
			return -EIO;	/* short: the partition is smaller */
		done += (size_t)n;
	}
	return 0;
}

static int write_at(int fd, unsigned long long off, const void *buf, size_t len)
{
	const unsigned char *p = buf;
	size_t done = 0;

	while (done < len) {
		ssize_t n = pwrite(fd, p + done, len - done, (off_t)(off + done));

		if (n < 0) {
			if (errno == EINTR)
				continue;
			return -errno;
		}
		if (n == 0)
			return -EIO;
		done += (size_t)n;
	}
	return 0;
}

static void put_le32(unsigned char *p, uint32_t v)
{
	p[0] = (unsigned char)(v & 0xff);
	p[1] = (unsigned char)((v >> 8) & 0xff);
	p[2] = (unsigned char)((v >> 16) & 0xff);
	p[3] = (unsigned char)((v >> 24) & 0xff);
}

static int crc_over_fd(int fd, unsigned long long off, size_t len,
		       uint32_t *out)
{
	unsigned char *buf;
	uint32_t crc = 0xffffffffu;
	size_t done = 0;

	/* 1 MiB at a time: the kernel region is 3 MiB and the filesystem 13 MiB,
	 * and this has to run on the router.
	 */
	buf = malloc(1u << 20);
	if (!buf)
		return -ENOMEM;
	while (done < len) {
		size_t chunk = len - done > (1u << 20) ? (1u << 20) : len - done;
		int ret = read_at(fd, off + done, buf, chunk);

		if (ret) {
			free(buf);
			return ret;
		}
		crc = crc32_update(crc, buf, chunk);
		done += chunk;
	}
	free(buf);
	*out = crc ^ 0xffffffffu;
	return 0;
}

static void usage(void)
{
	fprintf(stderr,
		"usage: h199a-header-regen <header-blk> <kernel-part> <rootfs-part> [<output>]\n"
		"\n"
		"Rewrites only +0x3c (kernel CRC), +0x48 (filesystem CRC) and\n"
		"+0xa4 (header self-CRC) from what is already on flash; every other\n"
		"byte is preserved from the unit's own header.\n");
}

int main(int argc, char **argv)
{
	unsigned char *hdr;
	uint32_t kcrc, fcrc, hcrc;
	int hfd, kfd, rfd, ofd, ret;

	if (argc < 4 || argc > 5) {
		usage();
		return 2;
	}

	hdr = malloc(HEADER_BLK);
	if (!hdr) {
		perror("malloc");
		return 1;
	}

	hfd = open(argv[1], O_RDONLY);
	if (hfd < 0) {
		fprintf(stderr, "h199a-header-regen: %s: %s\n", argv[1],
			strerror(errno));
		return 1;
	}
	ret = read_at(hfd, 0, hdr, HEADER_BLK);
	close(hfd);
	if (ret) {
		fprintf(stderr, "h199a-header-regen: %s: cannot read a full %u-byte header block (%s)\n",
			argv[1], HEADER_BLK, strerror(-ret));
		return 1;
	}

	kfd = open(argv[2], O_RDONLY);
	if (kfd < 0) {
		fprintf(stderr, "h199a-header-regen: %s: %s\n", argv[2],
			strerror(errno));
		return 1;
	}
	ret = crc_over_fd(kfd, KERNEL_SKIP, CRC_LEN, &kcrc);
	close(kfd);
	if (ret) {
		fprintf(stderr, "h199a-header-regen: kernel CRC over %#x bytes at %#x: %s\n",
			CRC_LEN, KERNEL_SKIP, strerror(-ret));
		return 1;
	}

	rfd = open(argv[3], O_RDONLY);
	if (rfd < 0) {
		fprintf(stderr, "h199a-header-regen: %s: %s\n", argv[3],
			strerror(errno));
		return 1;
	}
	ret = crc_over_fd(rfd, 0, FS_LEN, &fcrc);
	close(rfd);
	if (ret) {
		fprintf(stderr, "h199a-header-regen: filesystem CRC over %#x bytes: %s\n",
			FS_LEN, strerror(-ret));
		return 1;
	}

	put_le32(hdr + HDR_KERNEL_CRC, kcrc);
	put_le32(hdr + HDR_FS_CRC, fcrc);
	/* Last: the two words above are inside the range this covers. */
	hcrc = crc32_of(hdr, HDR_CRC_LEN);
	put_le32(hdr + HDR_SELF_CRC, hcrc);

	ofd = open(argc == 5 ? argv[4] : argv[1],
		   (argc == 5 ? O_WRONLY | O_CREAT | O_TRUNC : O_WRONLY), 0644);
	if (ofd < 0) {
		fprintf(stderr, "h199a-header-regen: %s: %s\n",
			argc == 5 ? argv[4] : argv[1], strerror(errno));
		return 1;
	}
	ret = write_at(ofd, 0, hdr, HEADER_BLK);
	if (ret) {
		fprintf(stderr, "h199a-header-regen: write: %s\n", strerror(-ret));
		close(ofd);
		return 1;
	}
	if (fsync(ofd)) {
		fprintf(stderr, "h199a-header-regen: fsync: %s\n", strerror(errno));
		close(ofd);
		return 1;
	}
	close(ofd);
	free(hdr);

	printf("h199a-header-regen: kernel %08x fs %08x header %08x\n",
	       kcrc, fcrc, hcrc);
	return 0;
}
