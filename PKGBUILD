# Maintainer: RIOT
pkgname=langtu-boom68-ctl
pkgver=1.0.0
pkgrel=1
pkgdesc="RGB lighting & real-time audio visualizer for Langtu BOOM68 / HE68 keyboard"
arch=('any')
url="https://github.com/meth/langtu-boom68"
license=('MIT')
depends=('python' 'python-gobject' 'gtk3' 'libappindicator-gtk3' 'cava' 'python-numpy' 'pipewire' 'pipewire-pulse')

package() {
    # Install files into /opt
    install -d "${pkgdir}/opt/boom68-ctl"
    install -m755 "${srcdir}"/../boom68_*.py "${pkgdir}/opt/boom68-ctl/"
    
    # Udev rule
    install -Dm644 "${srcdir}/../99-langtu-boom68.rules" "${pkgdir}/usr/lib/udev/rules.d/99-langtu-boom68.rules"

    # Symlinks in /usr/bin
    install -d "${pkgdir}/usr/bin"
    ln -s /opt/boom68-ctl/boom68_gui.py "${pkgdir}/usr/bin/boom68"
    ln -s /opt/boom68-ctl/boom68_gui.py "${pkgdir}/usr/bin/boom68-gui"
    ln -s /opt/boom68-ctl/boom68_tray.py "${pkgdir}/usr/bin/boom68-tray"
    ln -s /opt/boom68-ctl/boom68_visualizer.py "${pkgdir}/usr/bin/boom68-eq"
    ln -s /opt/boom68-ctl/boom68_ctl.py "${pkgdir}/usr/bin/boom68-ctl"

    # Desktop entry
    install -d "${pkgdir}/usr/share/applications"
    cat << 'EOF' > "${pkgdir}/usr/share/applications/langtu-boom68.desktop"
[Desktop Entry]
Type=Application
Name=Langtu BOOM68 RGB
Comment=Управление подсветкой и эквалайзером для Langtu BOOM68 / HE68
Exec=/usr/bin/boom68
Icon=input-keyboard
Terminal=false
Categories=Utility;HardwareSettings;
StartupNotify=false
EOF
}
