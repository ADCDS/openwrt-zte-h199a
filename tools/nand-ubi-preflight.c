// SPDX-License-Identifier: GPL-2.0-only
/* Read-only prerequisite for this board's private UBI qualification image.
 * Attachment writes flash. This utility never attaches, erases, or programs;
 * it accepts only the exact guarded 84..100MiB window and verifies every page.
 */
#define _FILE_OFFSET_BITS 64
#include <dirent.h>
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

#define TEST_OFFSET 0x05400000U
#define TEST_BYTES 0x01000000U
#define BLOCK_BYTES 131072U
#define PAGE_BYTES 2048U
#define OOB_BYTES 128U

static void fail(const char *what)
{
	fprintf(stderr, "STOP: %s (errno=%d: %s); no flash mutation performed\n",
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

static void expect_text(const char *path, const char *expected)
{
	char value[80];

	text_value(path, value, sizeof(value));
	if (strcmp(value, expected))
		fail(path);
}

static void require_absent(const char *path)
{
	struct stat st;

	errno = 0;
	if (!lstat(path, &st) || errno != ENOENT)
		fail(path);
}

static void require_directory(const char *path)
{
	struct stat st;

	if (stat(path, &st) || !S_ISDIR(st.st_mode))
		fail(path);
}

static void check_identity(void)
{
	char path[160];
	const char *drivers[] = {"/sys/bus/spi/drivers/spi-nand",
		"/sys/bus/platform/drivers/zx279128-spifc"};
	DIR *directory;
	struct dirent *entry;

	expect_text("/sys/class/mtd/mtd13/name", "ubi-test");
	if (number("/sys/class/mtd/mtd13/offset") != TEST_OFFSET ||
	    number("/sys/class/mtd/mtd13/size") != TEST_BYTES ||
	    number("/sys/class/mtd/mtd0/size") != 128U * 1024 * 1024)
		fail("wrong partition identity or physical window");
	expect_text("/sys/module/spi_zx279128/parameters/ubi_test", "Y");
	expect_text("/sys/module/spi_zx279128/parameters/write_test", "N");
	expect_text("/sys/module/spinand/parameters/diagnostic_write_guard", "Y");
	for (unsigned i = 0; i <= 13; i++) {
		snprintf(path, sizeof(path), "/sys/class/mtd/mtd%u/flags", i);
		if (number(path) != ((i == 0 || i == 13) ? MTD_WRITEABLE : 0))
			fail("unexpected master/partition write permissions");
	}
	require_absent("/sys/class/mtd/mtd14");
	for (unsigned i = 0; i < sizeof(drivers) / sizeof(drivers[0]); i++) {
		require_directory(drivers[i]);
		snprintf(path, sizeof(path), "%s/bind", drivers[i]);
		require_absent(path);
		snprintf(path, sizeof(path), "%s/unbind", drivers[i]);
		require_absent(path);
	}
	directory = opendir("/sys/class/ubi");
	if (!directory)
		fail("UBI class absent");
	errno = 0;
	while ((entry = readdir(directory))) {
		if (!strncmp(entry->d_name, "ubi", 3))
			fail("UBI already attached; this is a first-attachment preflight only");
	}
	if (errno || closedir(directory))
		fail("inspect UBI class");
}

static void check_blank(int fd)
{
	uint8_t data[PAGE_BYTES], oob[OOB_BYTES];

	for (unsigned block = 0; block < TEST_BYTES / BLOCK_BYTES; block++) {
		int64_t offset = (int64_t)block * BLOCK_BYTES;

		if (ioctl(fd, MEMGETBADBLOCK, &offset) != 0)
			fail("bad block or unreadable bad-block status");
		for (unsigned page = 0; page < BLOCK_BYTES / PAGE_BYTES; page++) {
			for (unsigned raw = 0; raw < 2; raw++) {
				uint64_t position = offset + page * PAGE_BYTES;
				struct mtd_read_req req = {
					.start = position,
					.len = sizeof(data), .ooblen = sizeof(oob),
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
				    req.ecc_stats.max_bitflips) {
					fprintf(stderr, "physical=%#x mode=%s ret=%d\n",
						TEST_OFFSET + (unsigned)position, raw ? "raw" : "ecc", ret);
					fail("page read/ECC status");
				}
				for (unsigned i = 0; i < sizeof(data); i++)
					if (data[i] != 0xff)
						fail("window contains programmed data");
				for (unsigned i = 0; i < sizeof(oob); i++)
					if (oob[i] != 0xff)
						fail("window contains programmed spare bytes or bad-block marker");
			}
		}
		if ((block + 1) % 16 == 0)
			printf("verified %u/128 eraseblocks, raw+corrected data and all OOB bytes erased\n", block + 1);
	}
}

int main(int argc, char **argv)
{
	struct mtd_info_user info;
	struct stat st;
	int fd;

	if (argc != 2 || strcmp(argv[1], "--check-blank")) {
		fprintf(stderr, "usage: nand-ubi-preflight --check-blank\n");
		return 2;
	}
	setvbuf(stdout, NULL, _IONBF, 0);
	check_identity();
	fd = open("/dev/mtd13", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
	if (fd < 0 || fstat(fd, &st) || !S_ISCHR(st.st_mode) ||
	    major(st.st_rdev) != 90 || minor(st.st_rdev) != 26 ||
	    ioctl(fd, MEMGETINFO, &info))
		fail("open/query exact mtd13 character device");
	if (info.type != MTD_NANDFLASH || info.flags != MTD_WRITEABLE ||
	    info.size != TEST_BYTES || info.erasesize != BLOCK_BYTES ||
	    info.writesize != PAGE_BYTES || info.oobsize != OOB_BYTES)
		fail("wrong test partition geometry");
	check_blank(fd);
	if (close(fd))
		fail("close MTD");
	check_identity();
	puts("PASS: guarded 84..100MiB window has 128 good, fully erased blocks; no flash mutation performed");
	return 0;
}
