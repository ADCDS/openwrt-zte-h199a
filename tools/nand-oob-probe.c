// SPDX-License-Identifier: GPL-2.0-only
/* Validate full-page data/OOB writes on an erased staging block only. */
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <mtd/mtd-user.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

#define PAGE 2048
#define OOB 64
#define BLOCK 131072

static void fail(const char *what)
{
	perror(what);
	exit(1);
}

static void read_page(int fd, uint64_t offset, uint8_t *data, uint8_t *oob)
{
	struct mtd_read_req req = {
		.start = offset, .len = PAGE, .ooblen = OOB,
		.usr_data = (uintptr_t)data, .usr_oob = (uintptr_t)oob,
		.mode = MTD_OPS_RAW,
	};

	memset(data, 0, PAGE);
	memset(oob, 0, OOB);
	if (ioctl(fd, MEMREAD, &req))
		fail("MEMREAD");
	if (req.len != PAGE || req.ooblen != OOB) {
		fprintf(stderr, "short raw page/OOB read\n");
		exit(1);
	}
}

static void require_erased(int fd, uint64_t offset)
{
	uint8_t data[PAGE], oob[OOB];
	unsigned int page, i;

	for (page = 0; page < BLOCK / PAGE; page++) {
		read_page(fd, offset + page * PAGE, data, oob);
		for (i = 0; i < PAGE + OOB; i++) {
			uint8_t byte = i < PAGE ? data[i] : oob[i - PAGE];

			if (byte != 0xff) {
				fprintf(stderr, "not erased: page=%u byte=%u value=%02x\n",
					page, i, byte);
				exit(1);
			}
		}
	}
}

static void data_pattern(uint8_t *data)
{
	unsigned int i;

	for (i = 0; i < PAGE; i++)
		data[i] = (i * 73 + (i >> 3) + 19) & 0xff;
}

static void damage_pattern(uint8_t *data)
{
	unsigned int i, flips = 0;

	for (i = 0; i < 512 * 8 && flips < 8; i++) {
		uint8_t mask = 1U << (i % 8);

		if (data[i / 8] & mask) {
			data[i / 8] &= ~mask;
			flips++;
		}
	}
}

static void require_fixture(int fd, uint64_t offset)
{
	uint8_t data[PAGE], oob[OOB], expected[PAGE], expected_oob[OOB];
	unsigned int page, i;

	for (page = 0; page < BLOCK / PAGE; page++) {
		read_page(fd, offset + page * PAGE, data, oob);
		memset(expected, 0xff, PAGE);
		memset(expected_oob, 0xff, OOB);
		if (page == 1 || page == 3)
			data_pattern(expected);
		if (page == 3)
			damage_pattern(expected);
		if (page == 1)
			for (i = 12; i < OOB; i++)
				expected_oob[i] = (i * 29 + 7) & 0xff;
		if (memcmp(data, expected, PAGE) ||
		    memcmp(oob, expected_oob, page == 3 ? 12 : OOB)) {
			fprintf(stderr, "block does not match retained fixture at page %u\n", page);
			exit(1);
		}
	}
}

int main(int argc, char **argv)
{
	struct mtd_info_user info;
	struct mtd_write_req write_req = {0};
	struct erase_info_user64 erase_req;
	struct stat st;
	uint8_t data[PAGE], oob[OOB], got_data[PAGE], got_oob[OOB];
	char path[128], name[32], *end;
	uint64_t offset;
	int64_t bad_offset;
	FILE *f;
	unsigned int i, pass;
	int fd, bad;
	bool cleanup = argc > 1 && !strcmp(argv[1], "--erase-fixture");
	bool keep = argc > 1 && !strcmp(argv[1], "--bch-keep");
	bool bch = keep || (argc > 1 && !strcmp(argv[1], "--bch"));

	if (bch || cleanup) {
		argv++;
		argc--;
	}

	if (argc != 3) {
		fprintf(stderr, "usage: nand-oob-probe [--bch|--bch-keep|--erase-fixture] /dev/mtdN block-offset\n"
			"Requires an entirely erased block in the staging partition.\n");
		return 2;
	}
	errno = 0;
	offset = strtoull(argv[2], &end, 0);
	if (errno || !argv[2][0] || argv[2][0] == '-' || *end || offset % BLOCK) {
		fprintf(stderr, "invalid block offset\n");
		return 2;
	}
	fd = open(argv[1], O_RDWR | O_SYNC);
	if (fd < 0)
		fail("open");
	if (fstat(fd, &st))
		fail("fstat");
	if (!S_ISCHR(st.st_mode) || major(st.st_rdev) != 90 || minor(st.st_rdev) % 2) {
		fprintf(stderr, "expected a writable MTD character device\n");
		return 2;
	}
	snprintf(path, sizeof(path), "/sys/class/mtd/mtd%u/name", minor(st.st_rdev) / 2);
	f = fopen(path, "r");
	if (!f)
		fail("MTD name");
	if (!fgets(name, sizeof(name), f) || strcmp(name, "staging\n")) {
		fprintf(stderr, "refusing a partition other than staging\n");
		return 2;
	}
	fclose(f);
	if (ioctl(fd, MEMGETINFO, &info))
		fail("MEMGETINFO");
	if (info.type != MTD_NANDFLASH || info.writesize != PAGE ||
	    info.oobsize != OOB || info.erasesize != BLOCK || info.size < BLOCK ||
	    offset > info.size - BLOCK) {
		fprintf(stderr, "unexpected geometry or out-of-range block\n");
		return 2;
	}
	bad_offset = offset;
	bad = ioctl(fd, MEMGETBADBLOCK, &bad_offset);
	if (bad < 0)
		fail("MEMGETBADBLOCK");
	if (bad) {
		fprintf(stderr, "refusing a bad block\n");
		return 2;
	}
	if (cleanup) {
		require_fixture(fd, offset);
		puts("FIXTURE VERIFIED: only the expected test pages are programmed");
		goto erase_block;
	}
	require_erased(fd, offset);
	printf("ERASED staging offset=0x%" PRIx64 " size=%u\n", offset, BLOCK);
	fflush(stdout);
	data_pattern(data);
	memset(oob, 0xff, OOB);
	for (i = 12; i < OOB; i++)
		oob[i] = (i * 29 + 7) & 0xff;
	/* Keep page zero and all bad-block marker bytes erased. */
	write_req.start = offset + PAGE;
	write_req.len = PAGE;
	write_req.ooblen = OOB;
	write_req.usr_data = (uintptr_t)data;
	write_req.usr_oob = (uintptr_t)oob;
	write_req.mode = MTD_OPS_RAW;
	if (ioctl(fd, MEMWRITE, &write_req))
		fail("MEMWRITE (test block retained)");
	for (pass = 0; pass < 3; pass++) {
		/* Evict the driver's page cache before checking persistent media. */
		read_page(fd, offset + 2 * PAGE, got_data, got_oob);
		read_page(fd, offset + PAGE, got_data, got_oob);
		if (memcmp(data, got_data, PAGE) || memcmp(oob, got_oob, OOB)) {
			fprintf(stderr, "VERIFY FAILED pass=%u; test block retained\n", pass);
			for (i = 0; i < OOB; i++)
				if (oob[i] != got_oob[i])
					fprintf(stderr, "OOB[%u] expected=%02x got=%02x\n",
						i, oob[i], got_oob[i]);
			return 1;
		}
	}
	printf("VERIFIED data=%u OOB=%u passes=3\n", PAGE, OOB);
	fflush(stdout);
	if (bch) {
		uint8_t damaged[PAGE], parity[OOB];
		struct mtd_read_req req = {0};
		int ret;

		/* A separate page leaves the raw-layout specimen intact. */
		write_req.start = offset + 3 * PAGE;
		write_req.mode = MTD_OPS_PLACE_OOB;
		memset(oob, 0xff, OOB);
		if (ioctl(fd, MEMWRITE, &write_req))
			fail("BCH write");
		read_page(fd, write_req.start, got_data, parity);
		if (memcmp(data, got_data, PAGE) || !memcmp(parity + 12, oob + 12, OOB - 12)) {
			fprintf(stderr, "BCH data mismatch or parity absent; check protected range\n");
			return 1;
		}
		memcpy(damaged, data, PAGE);
		damage_pattern(damaged);
		write_req.mode = MTD_OPS_RAW;
		write_req.usr_data = (uintptr_t)damaged;
		write_req.usr_oob = (uintptr_t)parity;
		if (ioctl(fd, MEMWRITE, &write_req))
			fail("raw bit injection");
		read_page(fd, write_req.start, got_data, got_oob);
		if (memcmp(damaged, got_data, PAGE) || memcmp(parity, got_oob, OOB)) {
			fprintf(stderr, "raw injection did not preserve damaged data and parity\n");
			return 1;
		}
		req.start = write_req.start;
		req.len = PAGE;
		req.ooblen = OOB;
		req.usr_data = (uintptr_t)got_data;
		req.usr_oob = (uintptr_t)got_oob;
		req.mode = MTD_OPS_PLACE_OOB;
		ret = ioctl(fd, MEMREAD, &req);
		if (ret && errno != EUCLEAN)
			fail("corrected read");
		if (req.len != PAGE || req.ooblen != OOB ||
		    memcmp(data, got_data, PAGE) || req.ecc_stats.corrected_bitflips != 8 ||
		    req.ecc_stats.max_bitflips != 8 || req.ecc_stats.uncorrectable_errors) {
			fprintf(stderr, "BCH correction failed: corrected=%u max=%u failed=%u\n",
				req.ecc_stats.corrected_bitflips, req.ecc_stats.max_bitflips,
				req.ecc_stats.uncorrectable_errors);
			return 1;
		}
		read_page(fd, write_req.start, got_data, got_oob);
		if (memcmp(damaged, got_data, PAGE)) {
			fprintf(stderr, "raw read reused corrected data\n");
			return 1;
		}
		puts("BCH VERIFIED: 8 injected bits corrected; raw data still damaged");
	}
	if (keep) {
		printf("FIXTURE RETAINED: block=0x%" PRIx64 " corrected-page=0x%" PRIx64 "\n",
		       offset, offset + 3 * PAGE);
		close(fd);
		return 0;
	}
erase_block:
	erase_req.start = offset;
	erase_req.length = BLOCK;
	if (ioctl(fd, MEMERASE64, &erase_req))
		fail("cleanup erase");
	require_erased(fd, offset);
	puts("PASS: staging block restored to erased state");
	close(fd);
	return 0;
}
