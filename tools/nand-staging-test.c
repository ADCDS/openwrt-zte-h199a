// SPDX-License-Identifier: GPL-2.0-only
/* Destructive qualification of ONE previously verified-empty H199A block.
 * Requires the matching bounded transport and private test DTB. No path,
 * offset, erase size or page count is accepted from the command line.
 */
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <mtd/mtd-user.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

#define PAGE_BYTES 2048
#define OOB_BYTES 128
#define BLOCK_BYTES 131072
#define TEST_OFFSET 0x63e0000

static void fail(const char *what)
{
	fprintf(stderr, "STOP: %s (errno=%d: %s); no automatic retry/cleanup erase\n",
		what, errno, strerror(errno));
	exit(1);
}

static void text_value(const char *path, char *buf, size_t size)
{
	FILE *stream = fopen(path, "r");
	size_t n;

	if (!stream)
		fail(path);
	n = fread(buf, 1, size - 1, stream);
	if (!n || ferror(stream) || !feof(stream) || buf[n - 1] != '\n')
		fail("malformed/oversized sysfs value");
	buf[n - 1] = '\0';
	if (fclose(stream))
		fail("close sysfs");
}

static uint64_t number(const char *path)
{
	char buf[80], *end;
	uint64_t value;

	text_value(path, buf, sizeof(buf));
	errno = 0;
	value = strtoull(buf, &end, 0);
	if (errno || !buf[0] || buf[0] == '-' || *end)
		fail("malformed sysfs number");
	return value;
}

static void check_identity(void)
{
	char path[128], value[80];

	text_value("/sys/class/mtd/mtd13/name", value, sizeof(value));
	if (strcmp(value, "write-test") ||
	    number("/sys/class/mtd/mtd13/offset") != TEST_OFFSET ||
	    number("/sys/class/mtd/mtd13/size") != BLOCK_BYTES ||
	    number("/sys/class/mtd/mtd0/size") != 128U * 1024 * 1024)
		fail("wrong partition identity or physical window");
	text_value("/sys/module/spi_zx279128/parameters/write_test", value, sizeof(value));
	if (strcmp(value, "Y"))
		fail("bounded transport guard is not enabled");
	for (unsigned i = 0; i <= 13; i++) {
		snprintf(path, sizeof(path), "/sys/class/mtd/mtd%u/flags", i);
		if (number(path) != ((i == 0 || i == 13) ? MTD_WRITEABLE : 0))
			fail("unexpected master/partition write permissions");
	}
}

static void pattern(unsigned page, uint8_t *data)
{
	uint32_t state = 0x6d2b79f5U ^ page;

	for (unsigned i = 0; i < PAGE_BYTES; i++) {
		state ^= state << 13;
		state ^= state >> 17;
		state ^= state << 5;
		data[i] = page == 0 ? 0 : page == 1 ? (i & 1 ? 0xaa : 0x55) : state;
	}
}

static void verify_block(int fd, int programmed)
{
	uint8_t data[PAGE_BYTES], oob[OOB_BYTES], expected[PAGE_BYTES];
	unsigned parity_seen = 0;

	for (unsigned page = 0; page < BLOCK_BYTES / PAGE_BYTES; page++) {
		if (programmed)
			pattern(page, expected);
		else
			memset(expected, 0xff, sizeof(expected));
		for (unsigned raw = 0; raw < 2; raw++) {
			struct mtd_read_req req = {
				.start = page * PAGE_BYTES, .len = sizeof(data), .ooblen = sizeof(oob),
				.usr_data = (uintptr_t)data, .usr_oob = (uintptr_t)oob,
				.mode = raw ? MTD_OPS_RAW : MTD_OPS_PLACE_OOB,
			};
			int ret;

			memset(data, 0x5a, sizeof(data));
			memset(oob, 0x5a, sizeof(oob));
			errno = 0;
			ret = ioctl(fd, MEMREAD, &req);
			if (ret || req.len != sizeof(data) || req.ooblen != sizeof(oob) ||
			    req.ecc_stats.uncorrectable_errors || req.ecc_stats.corrected_bitflips ||
			    req.ecc_stats.max_bitflips || memcmp(data, expected, sizeof(data))) {
				fprintf(stderr, "page=%u mode=%s ret=%d corrected=%u uncorrectable=%u\n",
					page, raw ? "raw" : "ecc", ret, req.ecc_stats.corrected_bitflips,
					req.ecc_stats.uncorrectable_errors);
				fail("page readback/ECC check");
			}
			for (unsigned i = 0; i < sizeof(oob); i++) {
				/* Preserve the BBM and all metadata at OOB[0:64].
				 * Only the chip may change its ECC parity at [64:128]. */
				if ((!programmed || i < 64) && oob[i] != 0xff)
					fail("erased/free spare bytes or bad-block marker changed");
				if (programmed && raw && i >= 64 && oob[i] != 0xff)
					parity_seen++;
			}
		}
	}
	if (programmed && !parity_seen)
		fail("programmed pages have no stored ECC evidence");
	printf("verified 64 pages, data+OOB, corrected and raw: %s\n",
	       programmed ? "exact patterns, intact BBM, zero corrections" : "all erased");
}

static void erase_test_block(int fd)
{
	struct erase_info_user64 erase = { .start = 0, .length = BLOCK_BYTES };

	if (ioctl(fd, MEMERASE64, &erase))
		fail("erase block799");
	puts("erased block799 only");
}

int main(int argc, char **argv)
{
	struct mtd_info_user info;
	struct stat st;
	uint8_t data[PAGE_BYTES];
	int64_t bad_offset = 0;
	int fd, execute;

	if (argc != 2 || (strcmp(argv[1], "--check") &&
			  strcmp(argv[1], "--execute-staging-block799"))) {
		fprintf(stderr, "usage: nand-staging-test --check|--execute-staging-block799\n");
		return 2;
	}
	setvbuf(stdout, NULL, _IONBF, 0);
	execute = !strcmp(argv[1], "--execute-staging-block799");
	check_identity();
	fd = open("/dev/mtd13", (execute ? O_RDWR : O_RDONLY) | O_CLOEXEC | O_NOFOLLOW);
	if (fd < 0 || fstat(fd, &st) || !S_ISCHR(st.st_mode) ||
	    major(st.st_rdev) != 90 || minor(st.st_rdev) != 26 ||
	    ioctl(fd, MEMGETINFO, &info))
		fail("open/query exact mtd13 character device");
	if (info.type != MTD_NANDFLASH || info.flags != MTD_WRITEABLE ||
	    info.size != BLOCK_BYTES || info.erasesize != BLOCK_BYTES ||
	    info.writesize != PAGE_BYTES || info.oobsize != OOB_BYTES)
		fail("wrong test partition geometry");
	if (ioctl(fd, MEMGETBADBLOCK, &bad_offset) != 0)
		fail("bad block or unreadable bad-block status");
	verify_block(fd, 0);
	if (execute) {
		erase_test_block(fd);
		verify_block(fd, 0);
		for (unsigned page = 0; page < BLOCK_BYTES / PAGE_BYTES; page++) {
			struct mtd_write_req req = {
				.start = page * PAGE_BYTES, .len = sizeof(data),
				.usr_data = (uintptr_t)data, .mode = MTD_OPS_PLACE_OOB,
			};

			pattern(page, data);
			if (ioctl(fd, MEMWRITE, &req))
				fail("one full-page program attempt");
			printf("programmed page %u/63 once\n", page);
		}
		verify_block(fd, 1);
		erase_test_block(fd);
		verify_block(fd, 0);
	}
	if (close(fd))
		fail("close test partition");
	puts(execute ? "PASS: block799 program/read/erase qualification; left erased" :
		      "PASS: read-only preflight; block799 is erased");
	return 0;
}
