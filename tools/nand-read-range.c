// SPDX-License-Identifier: GPL-2.0-only
/* Copy normal MTD reads to a new RAM file, rejecting uncorrectable/short reads.
 * Unlike read()/dd, MEMREAD exposes ECC failures instead of hiding EBADMSG.
 * The caller must independently verify the controller's ECC mode and image CRCs.
 */
#define _FILE_OFFSET_BITS 64
#include <ctype.h>
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

struct totals {
	uint64_t corrected;
	uint32_t max_bitflips;
};

static int read_corrected(int fd, uint64_t offset, void *buf, size_t size,
			  struct totals *totals)
{
	struct mtd_read_req req = {
		.start = offset, .len = size, .usr_data = (uintptr_t)buf,
		.mode = MTD_OPS_PLACE_OOB,
	};
	int ret, error;

	errno = 0;
	ret = ioctl(fd, MEMREAD, &req);
	error = ret < 0 ? errno : 0;
	if ((ret < 0 && error != EUCLEAN) || req.len != size ||
	    req.ecc_stats.uncorrectable_errors) {
		fprintf(stderr, "rejected offset=0x%" PRIx64 " error=%d bytes=%" PRIu64
			" expected=%zu uncorrectable=%u\n", offset, error,
			(uint64_t)req.len, size, req.ecc_stats.uncorrectable_errors);
		return -1;
	}
	totals->corrected += req.ecc_stats.corrected_bitflips;
	if (req.ecc_stats.max_bitflips > totals->max_bitflips)
		totals->max_bitflips = req.ecc_stats.max_bitflips;
	return 0;
}

static uint64_t number(const char *s)
{
	char *end;
	uint64_t value;

	errno = 0;
	value = strtoull(s, &end, 0);
	if (errno || !*s || *s == '-' || *end) {
		fprintf(stderr, "invalid offset/length\n");
		exit(2);
	}
	return value;
}

static int ram_path(const char *s)
{
	if (strncmp(s, "/tmp/", 5) || !s[5])
		return 0;
	for (s += 5; *s; s++)
		if (!isalnum((unsigned char)*s) && *s != '-' && *s != '_' && *s != '.')
			return 0;
	return 1;
}

int main(int argc, char **argv)
{
	struct mtd_info_user info;
	struct stat st;
	struct totals totals = {0};
	uint64_t offset, length, done = 0;
	char partial[512];
	uint8_t *buf = NULL;
	int fd = -1, out = -1, result = 1, n;

	if (argc != 5 || !ram_path(argv[4])) {
		fprintf(stderr, "usage: nand-read-range MTD offset length /tmp/new-file\n");
		return 2;
	}
	offset = number(argv[2]);
	length = number(argv[3]);
	n = snprintf(partial, sizeof(partial), "%s.partial", argv[4]);
	if (n < 0 || (size_t)n >= sizeof(partial))
		return 2;
	fd = open(argv[1], O_RDONLY | O_CLOEXEC);
	if (fd < 0 || fstat(fd, &st) || !S_ISCHR(st.st_mode) ||
	    ioctl(fd, MEMGETINFO, &info)) {
		perror("open/query MTD character device read-only");
		goto out;
	}
	if (info.writesize != 2048 || info.erasesize != 131072 ||
	    !length || offset % info.writesize || length % info.writesize ||
	    offset > info.size || length > info.size - offset) {
		fprintf(stderr, "unsupported geometry or unaligned/out-of-range request\n");
		goto out;
	}
	buf = malloc(info.erasesize);
	if (!buf)
		goto out;
	out = open(partial, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
	if (out < 0) {
		perror("create new partial RAM output");
		goto out;
	}
	printf("offset=0x%" PRIx64 " length=%" PRIu64 " mtd_flags=0x%x mode=normal\n",
	       offset, length, info.flags);
	fflush(stdout);
	while (done < length) {
		size_t size = length - done < info.erasesize ? length - done : info.erasesize;
		size_t saved = 0;

		if (read_corrected(fd, offset + done, buf, size, &totals))
			goto out;
		while (saved < size) {
			ssize_t wrote = write(out, buf + saved, size - saved);

			if (wrote < 0 && errno == EINTR)
				continue;
			if (wrote <= 0) {
				perror("write RAM output");
				goto out;
			}
			saved += wrote;
		}
		done += size;
	}
	if (fsync(out)) {
		perror("sync RAM output");
		goto out;
	}
	/* link() refuses to overwrite an existing final name. Partial files remain
	 * explicitly marked on any failure; only a complete read gets the final name.
	 */
	if (link(partial, argv[4])) {
		perror("publish complete RAM output");
		goto out;
	}
	if (unlink(partial)) {
		perror("remove partial name");
		goto out;
	}
	printf("complete bytes=%" PRIu64 " corrected_bound=%" PRIu64
	       " max_bitflips=%u uncorrectable=0\n", done,
	       totals.corrected, totals.max_bitflips);
	result = 0;
out:
	if (out >= 0 && close(out))
		result = 1;
	if (fd >= 0)
		close(fd);
	free(buf);
	return result;
}
