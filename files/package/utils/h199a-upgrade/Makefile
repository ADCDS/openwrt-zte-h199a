include $(TOPDIR)/rules.mk

PKG_NAME:=h199a-upgrade
PKG_RELEASE:=2
PKG_LICENSE:=GPL-2.0-only

include $(INCLUDE_DIR)/package.mk

define Package/h199a-upgrade
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=H199A active-bank sysupgrade header preparation
  DEPENDS:=@TARGET_armsr
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
	$(CP) ./src/*.c $(PKG_BUILD_DIR)/
endef

define Build/Compile
	$(TARGET_CC) $(TARGET_CFLAGS) $(TARGET_CPPFLAGS) -Wall -Wextra -Werror \
		-o $(PKG_BUILD_DIR)/h199a-upgrade-header \
		$(PKG_BUILD_DIR)/h199a-upgrade-header.c $(TARGET_LDFLAGS)
endef

define Package/h199a-upgrade/install
	$(INSTALL_DIR) $(1)/usr/sbin
	$(INSTALL_BIN) $(PKG_BUILD_DIR)/h199a-upgrade-header $(1)/usr/sbin/
endef

$(eval $(call BuildPackage,h199a-upgrade))
