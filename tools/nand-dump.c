// SPDX-License-Identifier: GPL-2.0-only
/* Stream physical pages plus OOB from a read-only MTD master. No bad-block
 * skipping and no chip writes. Corrected mode rejects uncorrectable pages.
 * Binary stdout must be captured as a partial
 * file until exit status, length, and independent repeated hashes are checked.
 */
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <mtd/mtd-user.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>

static int emit(const void *data, size_t length)
{
	const uint8_t *p = data;

	while (length) {
		ssize_t n = write(STDOUT_FILENO, p, length);

		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0)
			return -1;
		p += n;
		length -= n;
	}
	return 0;
}

int main(int argc, char **argv)
{
	struct mtd_info_user info;
	struct stat st;
	uint8_t data[2048], oob[128];
	uint64_t offset, total = 0, corrected = 0;
	uint32_t max_bitflips = 0;
	int raw;
	int fd;

	if (argc != 3 || (strcmp(argv[1], "--raw") && strcmp(argv[1], "--corrected"))) {
		fprintf(stderr, "usage: nand-dump --raw|--corrected MTD > new-partial-file\n");
		return 2;
	}
	raw = !strcmp(argv[1], "--raw");
	fd = open(argv[2], O_RDONLY | O_CLOEXEC);
	if (fd < 0 || fstat(fd, &st) || !S_ISCHR(st.st_mode) ||
	    ioctl(fd, MEMGETINFO, &info)) {
		perror("open/query read-only MTD master");
		return 1;
	}
	if (info.size != 128U * 1024 * 1024 || info.writesize != sizeof(data) ||
	    info.oobsize != sizeof(oob) || info.erasesize != 128U * 1024 ||
	    info.flags & MTD_WRITEABLE) {
		fprintf(stderr, "refused: expected read-only 128MiB/2048+128 master\n");
		close(fd);
		return 2;
	}
	fprintf(stderr, "%s interleaved dump: page=2048 oob=128 pages=65536 flags=0x%x\n",
		raw ? "RAW" : "CORRECTED", info.flags);
	for (offset = 0; offset < info.size; offset += sizeof(data)) {
		struct mtd_read_req req = {
			.start = offset, .len = sizeof(data), .ooblen = sizeof(oob),
			.usr_data = (uintptr_t)data, .usr_oob = (uintptr_t)oob,
			.mode = raw ? MTD_OPS_RAW : MTD_OPS_PLACE_OOB,
		};
		int ret, error;

		errno = 0;
		ret = ioctl(fd, MEMREAD, &req);
		error = ret < 0 ? errno : 0;
		if ((ret && !(ret < 0 && !raw && error == EUCLEAN)) ||
		    req.len != sizeof(data) || req.ooblen != sizeof(oob) ||
		    (raw && req.ecc_stats.corrected_bitflips) || req.ecc_stats.uncorrectable_errors) {
			fprintf(stderr, "read rejected: offset=0x%" PRIx64
				" error=%d data=%" PRIu64 " oob=%" PRIu64
				" corrected=%u uncorrectable=%u\n", offset, error,
				(uint64_t)req.len, (uint64_t)req.ooblen,
				req.ecc_stats.corrected_bitflips,
				req.ecc_stats.uncorrectable_errors);
			close(fd);
			return 1;
		}
		if (req.ecc_stats.corrected_bitflips)
			fprintf(stderr, "ECC_CORRECTED offset=0x%" PRIx64
				" bound=%u max=%u\n", offset,
				req.ecc_stats.corrected_bitflips,
				req.ecc_stats.max_bitflips);
		if (emit(data, sizeof(data)) || emit(oob, sizeof(oob))) {
			perror("write binary stdout");
			close(fd);
			return 1;
		}
		corrected += req.ecc_stats.corrected_bitflips;
		if (req.ecc_stats.max_bitflips > max_bitflips)
			max_bitflips = req.ecc_stats.max_bitflips;
		total += sizeof(data) + sizeof(oob);
		if (!((offset / sizeof(data) + 1) % 4096))
			fprintf(stderr, "pages=%" PRIu64 "/65536\n", offset / sizeof(data) + 1);
	}
	if (close(fd)) {
		perror("close MTD");
		return 1;
	}
	fprintf(stderr, "COMPLETE bytes=%" PRIu64 " pages=65536 read-errors=0 corrected-bound=%" PRIu64 " max-bitflips=%u\n",
		total, corrected, max_bitflips);
	return 0;
}
