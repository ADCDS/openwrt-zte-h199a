# SPDX-License-Identifier: GPL-2.0
ifdef CONFIG_ZX279128_PP_TABLES
# Packet-processor table access is linked into the Ethernet driver. Without
# it the driver keeps its original single-object form.
obj-$(CONFIG_ZX279128_ETH) += zx279128_eth.o
zx279128_eth-y := zx279128-eth.o zx279128-pp.o zx279128-pp-hash.o
# The flow-install test path is a further opt-in on top of table access.
zx279128_eth-$(CONFIG_ZX279128_PP_FLOW_TEST) += zx279128-pp-flow.o
# The production hardware-offload path, also on top of table access.
zx279128_eth-$(CONFIG_ZX279128_PP_OFFLOAD) += zx279128-pp-offload.o
else
obj-$(CONFIG_ZX279128_ETH) += zx279128-eth.o
endif
obj-$(CONFIG_ZX279128_PCIE_PROBE_TEST) += zx_pcie_probe_test.o
