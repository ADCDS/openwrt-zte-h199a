// SPDX-License-Identifier: GPL-2.0
/* RAM-only bench sink: record labeled UDP payloads without generating replies. */
#include <arpa/inet.h>
#include <errno.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

static int64_t milliseconds(void)
{
	struct timespec now;

	if (clock_gettime(CLOCK_MONOTONIC, &now)) {
		perror("clock_gettime");
		exit(1);
	}
	return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

int main(int argc, char **argv)
{
	struct sockaddr_in address = { .sin_family = AF_INET };
	struct pollfd descriptor;
	unsigned char data[2048];
	char *end;
	long port;
	int64_t stop, remaining;
	int result;
	ssize_t length;

	if (argc != 2)
		return 2;
	errno = 0;
	port = strtol(argv[1], &end, 10);
	if (errno || !argv[1][0] || *end || port < 1024 || port > 65535)
		return 2;
	address.sin_port = htons((unsigned short)port);
	address.sin_addr.s_addr = htonl(INADDR_ANY);
	descriptor.fd = socket(AF_INET, SOCK_DGRAM, 0);
	if (descriptor.fd < 0 || bind(descriptor.fd, (void *)&address, sizeof(address))) {
		perror("UDP socket/bind");
		return 1;
	}
	descriptor.events = POLLIN;
	puts("READY");
	fflush(stdout);
	stop = milliseconds() + 5000;
	while ((remaining = stop - milliseconds()) > 0) {
		result = poll(&descriptor, 1, (int)remaining);
		if (result < 0 && errno == EINTR)
			continue;
		if (result < 0) {
			perror("poll");
			return 1;
		}
		if (!result)
			break;
		length = recv(descriptor.fd, data, sizeof(data), MSG_DONTWAIT);
		if (length < 0 && (errno == EINTR || errno == EAGAIN))
			continue;
		if (length < 0) {
			perror("recv");
			return 1;
		}
		printf("len=%zd label=%u\n", length, length ? data[0] : 0);
		fflush(stdout);
	}
	close(descriptor.fd);
	return 0;
}
