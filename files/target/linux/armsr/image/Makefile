# SPDX-License-Identifier: GPL-2.0-only
#
# Copyright (C) 2016-2017 Yousong Zhou <yszhou4tech@gmail.com>

include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/image.mk

GRUB2_VARIANT =
GRUB_TERMINALS =
GRUB_SERIAL_CONFIG =
GRUB_TERMINAL_CONFIG =
GRUB_CONSOLE_CMDLINE = earlycon

ifneq ($(CONFIG_GRUB_CONSOLE),)
  GRUB_TERMINALS += console
endif

GRUB_SERIAL:=$(call qstrip,$(CONFIG_TARGET_SERIAL))

GRUB_SERIAL_CONFIG := serial --unit=0 --speed=$(CONFIG_GRUB_BAUDRATE) --word=8 --parity=no --stop=1 --rtscts=$(if $(CONFIG_GRUB_FLOWCONTROL),on,off)
GRUB_TERMINALS += serial

GRUB_TERMINAL_CONFIG := terminal_input $(GRUB_TERMINALS); terminal_output $(GRUB_TERMINALS)

ROOTPART:=$(call qstrip,$(CONFIG_TARGET_ROOTFS_PARTNAME))
ROOTPART:=$(if $(ROOTPART),$(ROOTPART),PARTUUID=$(IMG_PART_SIGNATURE)-02)
GPT_ROOTPART:=$(call qstrip,$(CONFIG_TARGET_ROOTFS_PARTNAME))
GPT_ROOTPART:=$(if $(GPT_ROOTPART),$(GPT_ROOTPART),PARTUUID=$(shell echo $(IMG_PART_DISKGUID) | sed 's/00$$/02/'))

GRUB_TIMEOUT:=$(call qstrip,$(CONFIG_GRUB_TIMEOUT))
GRUB_TITLE:=$(call qstrip,$(CONFIG_GRUB_TITLE))

BOOTOPTS:=$(call qstrip,$(CONFIG_GRUB_BOOTOPTS))

define Build/combined
  $(INSTALL_DIR) $@.boot/
	$(CP) $(KDIR)/$(KERNEL_NAME) $@.boot/efi/openwrt/
	-$(CP) $(STAGING_DIR_ROOT)/boot/. $@.boot/boot/
	$(if $(filter $(1),efi),
		$(INSTALL_DIR) $@.boot/efi/boot
		$(CP) $(STAGING_DIR_IMAGE)/grub2/boot$(if $(CONFIG_aarch64),aa64,arm).efi $@.boot/efi/openwrt/
		$(CP) $(STAGING_DIR_IMAGE)/grub2/boot$(if $(CONFIG_aarch64),aa64,arm).efi $@.boot/efi/boot/
	)
	KERNELPARTTYPE=ef FAT_TYPE="32" PADDING="1" SIGNATURE="$(IMG_PART_SIGNATURE)" \
		$(if $(filter $(1),efi),GUID="$(IMG_PART_DISKGUID)") $(SCRIPT_DIR)/gen_image_generic.sh \
		$@ \
		$(CONFIG_TARGET_KERNEL_PARTSIZE) $@.boot \
		$(CONFIG_TARGET_ROOTFS_PARTSIZE) $(IMAGE_ROOTFS) \
		256
endef

define Build/grub-config
	rm -fR $@.boot
	$(INSTALL_DIR) $@.boot/efi/openwrt/
	sed \
		-e 's#@SERIAL_CONFIG@#$(strip $(GRUB_SERIAL_CONFIG))#g' \
		-e 's#@TERMINAL_CONFIG@#$(strip $(GRUB_TERMINAL_CONFIG))#g' \
		-e 's#@ROOTPART@#root=$(ROOTPART) rootwait#g' \
		-e 's#@GPT_ROOTPART@#root=$(GPT_ROOTPART) rootwait#g' \
		-e 's#@CMDLINE@#$(BOOTOPTS) $(GRUB_CONSOLE_CMDLINE)#g' \
		-e 's#@TIMEOUT@#$(GRUB_TIMEOUT)#g' \
		-e 's#@TITLE@#$(GRUB_TITLE)#g' \
		-e 's#@KERNEL_NAME@#$(KERNEL_NAME)#g' \
		./grub-$(1).cfg > $@.boot/efi/openwrt/grub.cfg
endef

define Build/grub-install
	rm -fR $@.grub2
	$(INSTALL_DIR) $@.grub2
endef

DEVICE_VARS += GRUB2_VARIANT UBOOT
define Device/efi-default
  IMAGE/rootfs.img := append-rootfs | pad-to $(ROOTFS_PARTSIZE)
  IMAGE/rootfs.img.gz := append-rootfs | pad-to $(ROOTFS_PARTSIZE) | gzip
  IMAGE/combined-efi.img := grub-config efi | combined efi | grub-install efi | append-metadata
  IMAGE/combined-efi.img.gz := grub-config efi | combined efi | grub-install efi | gzip | append-metadata
  IMAGE/combined-efi.vmdk := grub-config efi | combined efi | grub-install efi | qemu-image vmdk
 ifeq ($(CONFIG_TARGET_IMAGES_GZIP),y)
    IMAGES-y := rootfs.img.gz
    IMAGES-y += combined-efi.img.gz
  else
    IMAGES-y := rootfs.img
    IMAGES-y += combined-efi.img
  endif
  ifeq ($(CONFIG_VMDK_IMAGES),y)
    IMAGES-y += combined-efi.vmdk
  endif
  KERNEL := kernel-bin
  KERNEL_INSTALL := 1
  IMAGES := $$(IMAGES-y)
  ARTIFACTS := $$(ARTIFACTS-y)
  SUPPORTED_DEVICES :=
 ifeq ($(CONFIG_arm),y)
  KERNEL_NAME = zImage
 endif
endef

define Device/generic
  $(call Device/efi-default)
  DEVICE_TITLE := Generic EFI Boot
  GRUB2_VARIANT := generic
  FILESYSTEMS := ext4 squashfs
  UBOOT := $(if $(CONFIG_aarch64),qemu_armv8,qemu_armv7)
  DEVICE_PACKAGES += kmod-amazon-ena kmod-e1000e kmod-vmxnet3 kmod-rtc-rx8025 \
	kmod-i2c-mux-pca954x kmod-gpio-pca953x partx-utils kmod-wdt-sp805 \
	kmod-mvneta kmod-mvpp2 kmod-fsl-dpaa1-net kmod-fsl-dpaa2-net \
	kmod-fsl-enetc-net kmod-dwmac-imx kmod-fsl-fec \
	kmod-dwmac-rockchip kmod-dwmac-sun8i kmod-phy-aquantia kmod-phy-broadcom \
	kmod-phy-marvell kmod-phy-marvell-10g kmod-sfp kmod-atlantic \
	kmod-bcmgenet kmod-octeontx2-net kmod-renesas-net-avb \
	kmod-phy-realtek kmod-phy-smsc $(if $(CONFIG_aarch64),kmod-thunderx-net)
endef
TARGET_DEVICES += generic


# ---------------------------------------------------------------------------
# ZTE ZXHN H199A (Sanechips ZX279128S)
#
# This device is not EFI/grub like the rest of armsr. The vendor bootloader
# ("zteboot") boots a uImage from a fixed NAND offset and validates a separate
# 128 KiB header holding CRC32s of the kernel and filesystem areas, so the
# output is not a single flashable blob but three parts assembled by
# tools/flash-prep.py:
#
#   kernel  -> 0x0700000 (0x300000)   ZTE magic + uImage, zero padded
#   rootfs  -> 0x0a00000 (0xd20000)   squashfs, zero padded
#   header  -> 0x1720000 (0x20000)    CRCs over the two above
#
# flash-prep emits both the individual parts (for first install over U-Boot
# TFTP) and a sysupgrade tar consumed by base-files/lib/upgrade/platform.sh.
# ---------------------------------------------------------------------------

# Resolve in BOTH layouts. In a developer tree OpenWrt sits beside the recipe
# ($(TOPDIR)/.. is the repo root); in a clean clone build.sh clones it INTO the
# recipe directory, so $(TOPDIR)/.. is the recipe itself. Removing the tracked
# `openwrt` symlink fixed a clean clone and broke this path in the same edit.
H199A_FLASH_PREP := $(firstword $(wildcard \
	$(TOPDIR)/../openwrt-zte-h199a/tools/flash-prep.py \
	$(TOPDIR)/../tools/flash-prep.py))
# Header template: either a full NAND dump of THIS device or just the 128 KiB
# header block extracted from it (see docs/INSTALL.md - "Extracting your header
# template"). It is device-specific, so it is not shipped in the repository;
# override with H199A_HEADER=/path/to/header-template.bin.
H199A_REFERENCE  := $(if $(H199A_HEADER),$(H199A_HEADER),$(firstword $(wildcard \
	$(TOPDIR)/../repo/h199a-flash-full.bin \
	$(TOPDIR)/../../repo/h199a-flash-full.bin \
	$(TOPDIR)/../../h199a-firmware/h199a-flash-full.bin)))

# An unresolved template must stop the build here.
#
# It used not to: make expanded the empty variable away, flash-prep.py received
# its arguments shifted by one, and the build died two layers down with
# "FileNotFoundError: ...-sysupgrade.tar.parts" - a path that does not exist
# because it is an OUTPUT, which sends you looking in entirely the wrong place.
# The real cause is a missing input, so say so where it is missing.
#
# The check is a shell test, not $(error): these Build/ macros are expanded
# while the device rules are generated, so a make-level error would abort
# menuconfig and every unrelated target for anyone without the template.
define Build/h199a-parts
	@[ -s "$(H199A_REFERENCE)" ] || { \
		echo "ERROR: no H199A header template."; \
		echo "  It is device-specific and not in this repository."; \
		echo "  See docs/INSTALL.md, 'Extracting your header template',"; \
		echo "  then: H199A_HEADER=/path/to/header-template.bin ./build.sh"; \
		exit 1; }
	$(STAGING_DIR_HOST)/bin/mkimage -A arm -O linux -T kernel -C none \
		-a 0x40008000 -e 0x40008000 -n h199a-openwrt \
		-d $(IMAGE_KERNEL) $@.uImage
	python3 $(H199A_FLASH_PREP) $@.uImage $(H199A_REFERENCE) $@.parts $(IMAGE_ROOTFS)
	mv $@.parts-sysupgrade.tar $@
endef

# Build profile (set by build.sh). The production profile selects a device-tree
# variant whose bank-A partitions and UBI overlay window are writable while
# everything else is read-only; the RAM profiles keep the fully read-only DTS.
#   normal              -> zx279128s-zte-h199a            (RAM qualification / default)
#   production          -> zx279128s-zte-h199a-production (NAND install + sysupgrade)
#   production+qualify  -> zx279128s-zte-h199a-production-qualify (RAM deny-matrix)
H199A_PROFILE := $(if $(H199A_BOOT_PROFILE),$(H199A_BOOT_PROFILE),normal)
H199A_DTS_SUFFIX := $(if $(filter production,$(H199A_PROFILE)),$(if $(filter 1,$(H199A_PRODUCTION_QUALIFY)),-production-qualify,-production),)
# ram-rootfs for either RAM profile (normal RAM_ROOT_TEST or production qualify).
H199A_WANT_RAM := $(or $(filter 1,$(H199A_RAM_ROOT)),$(filter 1,$(H199A_RAM_ROOT_TEST)),$(filter 1,$(H199A_PRODUCTION_QUALIFY)))

define Device/zte_h199a
  DEVICE_VENDOR := ZTE
  DEVICE_MODEL := ZXHN H199A
  DEVICE_DTS := zx279128s-zte-h199a$(H199A_DTS_SUFFIX)
  DEVICE_DTS_DIR := $(DTS_DIR)/zte
  # board_name is the first compatible; both it and the SoC string are
# accepted so an image built either side of the board-compatible change
# installs over the other.
SUPPORTED_DEVICES := zte,zxhn-h199a zte,zx279128s
  DEVICE_COMPAT_VERSION := 1.0
  KERNEL_NAME := zImage
  KERNEL := kernel-bin | append-dtb
  KERNEL_LOADADDR := 0x40008000
  FILESYSTEMS := squashfs
  IMAGE_SIZE := 13762560
  KERNEL_SIZE := 3145728
  IMAGES := $(if $(H199A_WANT_RAM),ram-rootfs.squashfs,sysupgrade.tar)
  IMAGE/ram-rootfs.squashfs := append-rootfs
  IMAGE/sysupgrade.tar := append-rootfs | h199a-parts
  DEVICE_PACKAGES := kmod-mt7615e kmod-mt7615-firmware kmod-mt7663-firmware-ap \
	kmod-mt76-core kmod-mt7603 wpad-mbedtls flock coreutils-timeout iw luci iperf3
endef
TARGET_DEVICES += zte_h199a

$(eval $(call BuildImage))
