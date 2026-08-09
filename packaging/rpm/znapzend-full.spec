Name:           znapzend-full
Version:        0.1.0
Release:        1%{?dist}
Summary:        Comprehensive backup wrapper for znapzend

License:        GPL-3.0-or-later
URL:            https://github.com/yourusername/znapzend-full
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  systemd-rpm-macros

Requires:       python3
Requires:       python3-pyyaml
Requires:       python3-dbus
Requires:       znapzend
Requires:       zfs
Requires:       gdisk
Requires:       openssh-clients
Requires:       polkit

Recommends:     python3-qt6
Recommends:     python3-textual

%description
znapzend-full provides a complete backup solution built on top of znapzend.
It adds backup of EFI partitions and GPT layouts, full ZFS/zpool property
backup, hash-based change detection, a D-Bus service for status monitoring,
a system tray application, an interactive restore utility, and a CLI control
tool for headless systems.

%package gui
Summary:        GUI components for znapzend-full
Requires:       %{name} = %{version}-%{release}
Requires:       python3-qt6

%description gui
This package provides the graphical user interface components:
- System tray application
- Configuration dialog

Install this on systems with a desktop environment.

%prep
%autosetup

%build
%py3_build

%install
%py3_install

# Install bin scripts
install -D -m 755 bin/znapzend-full-pre-backup \
    %{buildroot}%{_libdir}/znapzend-full/bin/znapzend-full-pre-backup
install -D -m 755 bin/znapzend-full-post-backup \
    %{buildroot}%{_libdir}/znapzend-full/bin/znapzend-full-post-backup

# Install systemd services
install -D -m 644 systemd/znapzend-full.service \
    %{buildroot}%{_unitdir}/znapzend-full.service
install -D -m 644 systemd/znapzend-full-dbus.service \
    %{buildroot}%{_unitdir}/znapzend-full-dbus.service

# Install D-Bus configuration
install -D -m 644 dbus/org.znapzend.Full.conf \
    %{buildroot}%{_sysconfdir}/dbus-1/system.d/org.znapzend.Full.conf

# Install Polkit policy
install -D -m 644 polkit/org.znapzend.full.policy \
    %{buildroot}%{_datadir}/polkit-1/actions/org.znapzend.full.policy

# Install example config
install -D -m 644 config/znapzend-full.yaml.example \
    %{buildroot}%{_docdir}/%{name}/config.yaml.example

# Create config directory
mkdir -p %{buildroot}%{_sysconfdir}/znapzend-full

# Create log directory
mkdir -p %{buildroot}%{_localstatedir}/log/znapzend-full

%post
%systemd_post znapzend-full.service znapzend-full-dbus.service

# Install example config if no config exists
if [ ! -f %{_sysconfdir}/znapzend-full/config.yaml ]; then
    cp %{_docdir}/%{name}/config.yaml.example \
       %{_sysconfdir}/znapzend-full/config.yaml
    chmod 640 %{_sysconfdir}/znapzend-full/config.yaml
fi

%preun
%systemd_preun znapzend-full.service znapzend-full-dbus.service

%postun
%systemd_postun_with_restart znapzend-full.service znapzend-full-dbus.service

%files
%license LICENSE
%doc README.md
%doc %{_docdir}/%{name}/config.yaml.example
%{python3_sitelib}/znapzend_full/
%{python3_sitelib}/znapzend_full-*.egg-info/
%{_bindir}/znapzend-full-ctl
%{_bindir}/znapzend-full-restore
%{_bindir}/znapzend-full-dbus-service
%{_libdir}/znapzend-full/
%{_unitdir}/znapzend-full.service
%{_unitdir}/znapzend-full-dbus.service
%{_sysconfdir}/dbus-1/system.d/org.znapzend.Full.conf
%{_datadir}/polkit-1/actions/org.znapzend.full.policy
%dir %{_sysconfdir}/znapzend-full
%dir %{_localstatedir}/log/znapzend-full
# Exclude GUI binary from base package
%exclude %{_bindir}/znapzend-full-tray

%files gui
%{_bindir}/znapzend-full-tray

%changelog
* Sun Dec 29 2025 Your Name <your.email@example.com> - 0.1.0-1
- Initial release
