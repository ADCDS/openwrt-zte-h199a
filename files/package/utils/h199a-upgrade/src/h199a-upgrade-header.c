// SPDX-License-Identifier: GPL-2.0-only
/* Prepare a staged sysupgrade header using this unit's running bank header.
 * No MTD writes: the output must be a new regular file, created exclusively.
 */
#define _FILE_OFFSET_BITS 64
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define HEADER_SIZE 0x20000u
#define KERNEL_SIZE 0x300000u
#define KERNEL_CRC_SIZE 0x2ffdccu
#define ROOTFS_SIZE 0xd20000u

static uint32_t table[256];

static void init_crc(void)
{
	unsigned int i, bit;

	for (i = 0; i < 256; i++) {
		uint32_t value = i;

		for (bit = 0; bit < 8; bit++)
			value = (value >> 1) ^ ((value & 1) ? 0xedb88320u : 0);
		table[i] = value;
	}
}

static uint32_t le32(const unsigned char *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
	       (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static void put32(unsigned char *p, uint32_t value)
{
	p[0] = value;
	p[1] = value >> 8;
	p[2] = value >> 16;
	p[3] = value >> 24;
}

static uint32_t be32(const unsigned char *p)
{
	return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 |
	       (uint32_t)p[2] << 8 | (uint32_t)p[3];
}

static uint32_t update(uint32_t crc, const unsigned char *p, size_t length)
{
	while (length--)
		crc = table[(crc ^ *p++) & 255] ^ (crc >> 8);
	return crc;
}

static uint32_t crc32(const unsigned char *p, size_t length)
{
	return update(0xffffffffu, p, length) ^ 0xffffffffu;
}

static int read_exact(const char *path, unsigned char *data, size_t size)
{
	struct stat st;
	size_t done = 0;
	ssize_t n;
	int fd = open(path, O_RDONLY | O_NOFOLLOW);

	if (fd < 0)
		return -1;
	if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size != (off_t)size)
		goto fail;
	while (done < size) {
		n = read(fd, data + done, size - done);
		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0)
			goto fail;
		done += n;
	}
	return close(fd);
fail:
	close(fd);
	return -1;
}

static int file_crc(const char *path, off_t size, off_t skip, size_t length,
		    uint32_t *result)
{
	unsigned char buffer[16384];
	struct stat st;
	uint32_t crc = 0xffffffffu;
	ssize_t n;
	int fd = open(path, O_RDONLY | O_NOFOLLOW);

	if (fd < 0)
		return -1;
	if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size != size ||
	    lseek(fd, skip, SEEK_SET) != skip)
		goto fail;
	while (length) {
		size_t want = length < sizeof(buffer) ? length : sizeof(buffer);

		n = read(fd, buffer, want);
		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0)
			goto fail;
		crc = update(crc, buffer, n);
		length -= n;
	}
	*result = crc ^ 0xffffffffu;
	return close(fd);
fail:
	close(fd);
	return -1;
}

static int valid_header(const unsigned char *p, unsigned int bank)
{
	return !memcmp(p + 0x6c, "ZXHN H199A", 10) &&
	       le32(p + 8) == 0x266 &&
	       le32(p + 0x34) == KERNEL_CRC_SIZE &&
	       le32(p + 0x38) == 0x234 && le32(p + 0x40) == ROOTFS_SIZE &&
	       le32(p + 0x44) == 0x300214 &&
	       p[0x8c] == 0 && p[0x8d] == 0 &&
	       le32(p + 0xf4) == 0x33333333 &&
	       le32(p + 0xf8) == 0x66666666 &&
	       le32(p + 0xfc) == 0x99999999 &&
	       le32(p + 0x100) == 0xcccccccc &&
	       le32(p + 0x1e0) == 0x700000 &&
	       le32(p + 0x1e4) == 0x2000000 &&
	       le32(p + 0x1e8) == 0x2000000 &&
	       le32(p + 0x1ec) == 0x3900000 &&
	       le32(p + 0x1f0) == (bank ? 0x2000000u : 0x700000u) &&
	       le32(p + 0xa4) == crc32(p, 0xa4) &&
	       le32(p + 0x1fc) == crc32(p, 0x1fc);
}

/* A bounded FDT walk distinguishes a real capability property from an unused
 * string or bytes in compressed kernel data. Return 0 for a legacy DT, 1 for
 * the new bank-aware contract, and -1 for malformed/foreign input.
 */
static int dt_bank_support(const unsigned char *dt, size_t available)
{
	char path[256] = "";
	size_t parents[32], path_length = 0, pos, end, strings, string_size, total;
	unsigned int depth = 0, roots = 0, nodes_seen = 0, properties_seen = 0;
	int board = 0, marker = 0, aware = 0;

	if (available < 40 || be32(dt) != 0xd00dfeed)
		return -1;
	total = be32(dt + 4);
	pos = be32(dt + 8);
	strings = be32(dt + 12);
	string_size = be32(dt + 32);
	if (total > available || total < 40 || be32(dt + 20) != 17 ||
	    pos < 40 || pos > total || (pos & 3) ||
	    be32(dt + 36) > total - pos || strings > total ||
	    string_size > total - strings)
		return -1;
	end = pos + be32(dt + 36);
	while (pos <= end && end - pos >= 4) {
		uint32_t token = be32(dt + pos);

		pos += 4;
		if (token == 1) {
			const unsigned char *zero = memchr(dt + pos, 0, end - pos);
			size_t length;

			if (!zero || depth >= 32)
				return -1;
			length = zero - (dt + pos);
			if (memchr(dt + pos, '/', length))
				return -1;
			parents[depth] = path_length;
			if (!depth) {
				if (length || roots++)
					return -1;
			} else {
				if (path_length + length + 2 > sizeof(path))
					return -1;
				path[path_length++] = '/';
				memcpy(path + path_length, dt + pos, length);
				path_length += length;
				path[path_length] = 0;
			}
			depth++;
			if (!strcmp(path, "/chosen")) {
				if (nodes_seen & 1)
					return -1;
				nodes_seen |= 1;
			}
			if (!strcmp(path, "/soc/spi@94406000/flash@0")) {
				if (nodes_seen & 2)
					return -1;
				nodes_seen |= 2;
			}
			pos = (pos + length + 1 + 3) & ~(size_t)3;
		} else if (token == 2) {
			if (!depth)
				return -1;
			path_length = parents[--depth];
			path[path_length] = 0;
		} else if (token == 3) {
			uint32_t length, name_offset;
			const char *name;

			if (!depth || pos > end || end - pos < 8)
				return -1;
			length = be32(dt + pos);
			name_offset = be32(dt + pos + 4);
			pos += 8;
			if (length > end - pos || name_offset >= string_size)
				return -1;
			name = (const char *)dt + strings + name_offset;
			if (!memchr(name, 0, string_size - name_offset))
				return -1;
			if (!path[0] && !strcmp(name, "compatible")) {
				size_t at = 0;

				if (properties_seen & 1)
					return -1;
				properties_seen |= 1;
				while (at < length) {
					const unsigned char *zero = memchr(dt + pos + at, 0, length - at);
					if (!zero)
						return -1;
					if (!strcmp((const char *)dt + pos + at, "zte,zxhn-h199a"))
						board = 1;
					at = zero - (dt + pos) + 1;
				}
			}
			if (!strcmp(path, "/chosen") && !strcmp(name, "zte,boot-bank")) {
				if (properties_seen & 2)
					return -1;
				properties_seen |= 2;
				marker = length == 4 && be32(dt + pos) == 0xffffffffu;
			}
			if (!strcmp(path, "/soc/spi@94406000/flash@0") &&
			    !strcmp(name, "zte,bank-aware")) {
				if (properties_seen & 4)
					return -1;
				properties_seen |= 4;
				aware = !length;
			}
			pos = (pos + length + 3) & ~(size_t)3;
		} else if (token == 9) {
			return !depth && board ? marker && aware : -1;
		} else if (token != 4) {
			return -1;
		}
	}
	return -1;
}

static int kernel_bank_support(const char *path)
{
	unsigned char *kernel = malloc(KERNEL_SIZE), header[64];
	const unsigned char *uimage, *payload;
	uint32_t size, start, stop;
	int result = -1;

	if (!kernel || read_exact(path, kernel, KERNEL_SIZE))
		goto out;
	if (le32(kernel) != 0x33333333 || le32(kernel + 4) != 0xcccccccc ||
	    le32(kernel + 8) != 0x88888888 || le32(kernel + 12) != 0xdddddddd)
		goto out;
	uimage = kernel + 32;
	memcpy(header, uimage, sizeof(header));
	memset(header + 4, 0, 4);
	size = be32(uimage + 12);
	if (be32(uimage) != 0x27051956 || be32(uimage + 4) != crc32(header, 64) ||
	    size < 48 || size > KERNEL_SIZE - 96 ||
	    be32(uimage + 16) != 0x40008000 || be32(uimage + 20) != 0x40008000 ||
	    memcmp(uimage + 28, "\x05\x02\x02\x00", 4))
		goto out;
	payload = kernel + 96;
	if (crc32(payload, size) != be32(uimage + 24) || le32(payload + 36) != 0x016f2818)
		goto out;
	start = le32(payload + 40);
	stop = le32(payload + 44);
	if (stop < start || stop - start < 48 || stop - start > size)
		goto out;
	result = dt_bank_support(payload + stop - start, size - (stop - start));
out:
	free(kernel);
	return result;
}

int main(int argc, char **argv)
{
	unsigned char *header = NULL, *backup = NULL;
	uint32_t kernel_crc, rootfs_crc, serial, peer_serial;
	size_t done = 0;
	unsigned int bank;
	ssize_t n;
	int fd = -1, result = 1, support;

	init_crc();
	if (argc == 4 && !strcmp(argv[1], "--check-kernel")) {
		if (strlen(argv[2]) != 1 || (argv[2][0] != 'a' && argv[2][0] != 'b'))
			return 2;
		support = kernel_bank_support(argv[3]);
		if (support < 0 || (argv[2][0] == 'b' && !support)) {
			fprintf(stderr, "invalid kernel or bank-B upgrade with an A-only kernel\n");
			return 1;
		}
		return 0;
	}
	if (argc != 7 || strlen(argv[1]) != 1 ||
	    (argv[1][0] != 'a' && argv[1][0] != 'b')) {
		fprintf(stderr, "usage: %s a|b CURRENT BACKUP KERNEL ROOTFS OUTPUT\n", argv[0]);
		return 2;
	}
	bank = argv[1][0] == 'b';
	header = malloc(HEADER_SIZE);
	backup = malloc(HEADER_SIZE);
	if (!header || !backup || read_exact(argv[2], header, HEADER_SIZE) ||
	    read_exact(argv[3], backup, HEADER_SIZE)) {
		fprintf(stderr, "cannot read exact staged header blocks\n");
		goto out;
	}
	if (!valid_header(header, bank)) {
		fprintf(stderr, "running header identity, bank geometry or CRC is invalid\n");
		goto out;
	}
	serial = le32(header + 0x1f4);
	/* U-Boot checks only the inner CRC before considering a peer's serial.
	 * Its extended CRC may be stale, so never ignore a bootable high serial.
	 */
	if (le32(backup + 0xa4) == crc32(backup, 0xa4)) {
		peer_serial = le32(backup + 0x1f4);
		if (peer_serial > serial)
			serial = peer_serial;
	}
	/* Avoid either signed or unsigned wrap in the vendor's serial compare. */
	if (serial >= 0x7fffffffu) {
		fprintf(stderr, "version serial cannot be incremented safely\n");
		goto out;
	}
	support = kernel_bank_support(argv[4]);
	if (support < 0 || (bank && !support)) {
		fprintf(stderr, "invalid kernel or bank-B upgrade with an A-only kernel\n");
		goto out;
	}
	if (file_crc(argv[4], KERNEL_SIZE, 0x20, KERNEL_CRC_SIZE, &kernel_crc) ||
	    file_crc(argv[5], ROOTFS_SIZE, 0, ROOTFS_SIZE, &rootfs_crc)) {
		fprintf(stderr, "kernel/rootfs is missing, short, oversized or unreadable\n");
		goto out;
	}
	put32(header + 0x3c, kernel_crc);
	put32(header + 0x48, rootfs_crc);
	put32(header + 0xa4, crc32(header, 0xa4));
	put32(header + 0x1f0, bank ? 0x2000000 : 0x700000);
	put32(header + 0x1f4, serial + 1);
	put32(header + 0x1f8, 1);
	put32(header + 0x1fc, crc32(header, 0x1fc));
	fd = open(argv[6], O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
	if (fd < 0) {
		fprintf(stderr, "cannot create new staged output: %s\n", strerror(errno));
		goto out;
	}
	while (done < HEADER_SIZE) {
		n = write(fd, header + done, HEADER_SIZE - done);
		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0)
			goto failed_output;
		done += n;
	}
	if (fsync(fd))
		goto failed_output;
	result = 0;
	printf("bank=%c serial=%u kernel_crc=%08x rootfs_crc=%08x\n",
	       'A' + bank, serial + 1, kernel_crc, rootfs_crc);
	goto out;
failed_output:
	fprintf(stderr, "staged output write failed\n");
	unlink(argv[6]);
out:
	if (fd >= 0)
		close(fd);
	free(backup);
	free(header);
	return result;
}
