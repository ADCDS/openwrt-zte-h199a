// SPDX-License-Identifier: GPL-2.0
/* mtdflash - minimal MTD flash writer for the H199A bring-up.
 *
 * Erases the target blocks, writes the image, and verifies by reading back.
 * Usage: mtdflash <mtd-dev> <image-file> [offset]
 *   offset is optional (default 0), in bytes, must be block-aligned.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <mtd/mtd-user.h>

int main(int argc, char **argv)
{
	const char *dev, *file;
	off_t offset = 0;
	int fd, ifd, ret = 1;
	mtd_info_t info;
	erase_info_t ei;
	unsigned char *buf, *vbuf;
	long fsize;
	size_t done;

	if (argc < 3 || argc > 4) {
		fprintf(stderr, "usage: %s <mtd-dev> <image-file> [offset]\n",
			argv[0]);
		return 1;
	}
	dev = argv[1];
	file = argv[2];
	if (argc == 4)
		offset = strtoull(argv[3], NULL, 0);

	fd = open(dev, O_RDWR);
	if (fd < 0) { perror("open mtd"); return 1; }
	if (ioctl(fd, MEMGETINFO, &info)) { perror("MEMGETINFO"); goto out; }

	ifd = open(file, O_RDONLY);
	if (ifd < 0) { perror("open image"); goto out; }
	fsize = lseek(ifd, 0, SEEK_END);
	if (fsize <= 0) { fprintf(stderr, "empty image\n"); goto out; }
	lseek(ifd, 0, SEEK_SET);
	if (offset + fsize > info.size) {
		fprintf(stderr, "image (%ld) + offset (%llu) > mtd size (%u)\n",
			fsize, (unsigned long long)offset, info.size);
		goto out;
	}

	printf("%s: size=%u erasesize=%u\n", dev, info.size, info.erasesize);
	printf("image %s: %ld bytes at offset %llu\n",
	       file, fsize, (unsigned long long)offset);

	/* 1. erase */
	size_t first_blk = offset / info.erasesize;
	size_t nblks = (fsize + info.erasesize - 1) / info.erasesize;
	for (size_t b = 0; b < nblks; b++) {
		ei.start = (first_blk + b) * info.erasesize;
		ei.length = info.erasesize;
		if (ioctl(fd, MEMERASE, &ei)) {
			fprintf(stderr, "MEMERASE blk %zu @0x%x failed: %s\n",
				first_blk + b, ei.start, strerror(errno));
			goto out;
		}
	}
	printf("erased %zu blocks\n", nblks);

	/* 2. write */
	buf = malloc(fsize);
	vbuf = malloc(fsize);
	if (!buf || !vbuf) { perror("malloc"); goto out; }
	done = 0;
	while (done < (size_t)fsize) {
		ssize_t n = read(ifd, buf + done, fsize - done);
		if (n < 0) { perror("read image"); goto out; }
		if (n == 0) break;
		done += n;
	}
	if (done != (size_t)fsize) { fprintf(stderr, "short image read\n"); goto out; }
	if (lseek(fd, offset, SEEK_SET) < 0) { perror("lseek mtd"); goto out; }
	done = 0;
	while (done < (size_t)fsize) {
		ssize_t n = write(fd, buf + done, fsize - done);
		if (n < 0) { perror("write mtd"); goto out; }
		done += n;
	}
	printf("wrote %zu bytes\n", done);

	/* 3. verify */
	if (lseek(fd, offset, SEEK_SET) < 0) { perror("lseek mtd"); goto out; }
	done = 0;
	while (done < (size_t)fsize) {
		ssize_t n = read(fd, vbuf + done, fsize - done);
		if (n < 0) { perror("read mtd"); goto out; }
		if (n == 0) break;
		done += n;
	}
	size_t bad = 0, first_bad = 0;
	for (size_t i = 0; i < (size_t)fsize; i++) {
		if (buf[i] != vbuf[i]) {
			if (!bad) first_bad = i;
			bad++;
		}
	}
	if (bad) {
		printf("VERIFY FAILED: %zu differing bytes, first at +0x%zx "
		       "(wrote %02x read %02x)\n", bad, first_bad,
		       buf[first_bad], vbuf[first_bad]);
		ret = 2;
	} else {
		printf("VERIFY OK (%zu bytes)\n", done);
		ret = 0;
	}
out:
	close(fd);
	close(ifd);
	return ret;
}
