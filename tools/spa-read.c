// SPDX-License-Identifier: GPL-2.0
/* Read-only table transactions; no SPA data/configuration writes. */
#define _DEFAULT_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define SPA_BASE 0x921d4000u
#define SPA_MAP_SIZE 0x1000u
#define SPA_IND_CMD 0x14u
#define SPA_IND_STATUS 0x18u
#define SPA_IND_DATA 0x1cu
#define SPA_IND_READY 1u
#define SPA_IND_READ (1u << 27)
#define SPA_IND_RAM_SHIFT 22u
#define SPA_HASH_RAM 5u
#define SPA_HASH_ENTRIES 8u

static uint32_t reg_read(volatile uint32_t *regs, unsigned int offset)
{
	return regs[offset / sizeof(*regs)];
}

static int wait_ready(volatile uint32_t *regs)
{
	unsigned int retry;

	for (retry = 0; retry < 1000; retry++) {
		if (reg_read(regs, SPA_IND_STATUS) & SPA_IND_READY)
			return 0;
		usleep(1);
	}

	fprintf(stderr, "SPA indirect access timed out; aborting\n");
	return -1;
}

int main(int argc, char **argv)
{
	volatile uint32_t *regs;
	unsigned int entry;
	int fd, result = 1;

	if (argc != 2 || strcmp(argv[1], "--hash")) {
		fprintf(stderr, "Usage: %s --hash\n"
			"Requires an idle H199A SPA indirect port; do not run alongside vendor SDK access.\n",
			argv[0]);
		return 2;
	}

	fd = open("/dev/mem", O_RDWR | O_SYNC);
	if (fd < 0) {
		perror("/dev/mem");
		return 1;
	}
	regs = mmap(NULL, SPA_MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, SPA_BASE);
	close(fd);
	if (regs == MAP_FAILED) {
		perror("mmap SPA");
		return 1;
	}

	printf("SPA 0x%08x status=0x%08x\n", SPA_BASE,
	       reg_read(regs, SPA_IND_STATUS));
	for (entry = 0; entry < SPA_HASH_ENTRIES; entry++) {
		uint32_t high, low;

		if (wait_ready(regs))
			goto out;
		regs[SPA_IND_CMD / sizeof(*regs)] = SPA_IND_READ |
			(SPA_HASH_RAM << SPA_IND_RAM_SHIFT) | entry;
		__sync_synchronize();
		if (wait_ready(regs))
			goto out;
		/* Vendor reads the high word first, then the low word. */
		high = reg_read(regs, SPA_IND_DATA + 4);
		low = reg_read(regs, SPA_IND_DATA);
		printf("hash[%u] data1=0x%08x data0=0x%08x\n", entry, high, low);
	}
	result = 0;
out:
	if (munmap((void *)regs, SPA_MAP_SIZE)) {
		perror("munmap SPA");
		result = 1;
	}
	return result;
}
