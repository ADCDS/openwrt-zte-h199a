ARCH:=arm
SUBTARGET:=armv7
BOARDNAME:=32-bit (armv7) machines
CPU_TYPE:=cortex-a9
CPU_SUBTYPE:=
KERNELNAME:=zImage dtbs
FEATURES+=nand

define Target/Description
	Build images for $(BOARDNAME)
endef
