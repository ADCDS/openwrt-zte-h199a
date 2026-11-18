// SPDX-License-Identifier: GPL-2.0-only
/* Read-only normal/raw page comparison, with OOB to force core callback dispatch. */
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
#include <unistd.h>

static void fail(const char *what)
{
	perror(what);
	exit(1);
}

static void save(const char *prefix, const char *mode, const char *kind,
		 const void *data, size_t size)
{
	char path[512];
	const uint8_t *p = data;
	int fd, length;

	length = snprintf(path, sizeof(path), "%s.%s.%s", prefix, mode, kind);
	if (length < 0 || (size_t)length >= sizeof(path)) {
		fprintf(stderr, "output path too long\n");
		exit(2);
	}
	fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
	if (fd < 0)
		fail(path);
	while (size) {
		ssize_t done = write(fd, p, size);

		if (done < 0 && errno == EINTR)
			continue;
		if (done <= 0)
			fail("write output");
		p += done;
		size -= done;
	}
	if (close(fd))
		fail("close output");
}

int main(int argc, char **argv)
{
	struct mtd_info_user info;
	struct stat st;
	uint8_t data[2048], oob[256];
	uint64_t offset;
	char *end;
	int fd, failed = 0;

	if (argc != 4 || strncmp(argv[3], "/tmp/", 5)) {
		fprintf(stderr, "usage: nand-read-probe MTD-device page-byte-offset /tmp/output-prefix\n");
		return 2;
	}
	errno = 0;
	offset = strtoull(argv[2], &end, 0);
	if (errno || !argv[2][0] || argv[2][0] == '-' || *end || offset % sizeof(data)) {
		fprintf(stderr, "invalid page offset\n");
		return 2;
	}
	fd = open(argv[1], O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		fail("open MTD read-only");
	if (fstat(fd, &st) || !S_ISCHR(st.st_mode)) {
		fprintf(stderr, "MTD path must be a character device\n");
		return 2;
	}
	if (ioctl(fd, MEMGETINFO, &info))
		fail("MEMGETINFO");
	if (info.writesize != sizeof(data) || !info.oobsize || info.oobsize > sizeof(oob) ||
	    info.size < sizeof(data) || offset > info.size - sizeof(data)) {
		fprintf(stderr, "unsupported geometry or offset outside device\n");
		return 2;
	}
	printf("device_bytes=%u page_bytes=%u oob_bytes=%u flags=0x%x offset=%" PRIu64 "\n",
	       info.size, info.writesize, info.oobsize, info.flags, offset);
	for (unsigned raw = 0; raw < 2; raw++) {
		const char *name = raw ? "raw" : "normal";
		struct mtd_read_req req = {
			.start = offset, .len = sizeof(data), .ooblen = info.oobsize,
			.usr_data = (uintptr_t)data, .usr_oob = (uintptr_t)oob,
			.mode = raw ? MTD_OPS_RAW : MTD_OPS_PLACE_OOB,
		};
		int result, error;

		memset(data, 0, sizeof(data));
		memset(oob, 0, sizeof(oob));
		errno = 0;
		result = ioctl(fd, MEMREAD, &req);
		error = result < 0 ? errno : 0;
		if ((result < 0 && error != EUCLEAN && error != EBADMSG) ||
		    req.len != sizeof(data) || req.ooblen != info.oobsize) {
			fprintf(stderr, "%s read failed/short: error=%d data=%" PRIu64 " oob=%" PRIu64 "\n",
				name, error, (uint64_t)req.len, (uint64_t)req.ooblen);
			return 1;
		}
		save(argv[3], name, "data", data, sizeof(data));
		save(argv[3], name, "oob", oob, info.oobsize);
		printf("mode=%s error=%d corrected=%u max_bitflips=%u uncorrectable=%u byte509=0x%02x\n",
		       name, error, req.ecc_stats.corrected_bitflips, req.ecc_stats.max_bitflips,
		       req.ecc_stats.uncorrectable_errors, data[509]);
		if (error == EBADMSG || req.ecc_stats.uncorrectable_errors)
			failed = 1;
	}
	close(fd);
	return failed;
}
