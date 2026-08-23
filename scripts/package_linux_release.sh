#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

APP_NAME="${APP_NAME:-DPO4000Desk}"
APP_ID="${APP_ID:-io.github.ami3go.DPO4000Desk}"
APP_COMMAND="dpo4000-desk"
BINARY="${BINARY:-${ROOT}/dist/${APP_NAME}}"
ASSETS_DIR="${RELEASE_ASSETS_DIR:-${ROOT}/release-assets}"
BUILD_DIR="${ROOT}/build/linux-packages"
FLATPAK_RUNTIME_VERSION="${FLATPAK_RUNTIME_VERSION:-24.08}"
BUILD_FLATPAK="${BUILD_FLATPAK:-1}"
REQUIRE_FLATPAK="${REQUIRE_FLATPAK:-0}"
VERSION="${RELEASE_VERSION:-}"

if [[ -z "${VERSION}" && "${GITHUB_REF_TYPE:-}" == "tag" ]]; then
  VERSION="${GITHUB_REF_NAME#v}"
fi

if [[ -z "${VERSION}" ]]; then
  VERSION="$(${PYTHON:-python3} - <<'PY'
from pathlib import Path
import tomllib
project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
print(project["project"]["version"])
PY
)"
fi

VERSION="${VERSION#v}"
DEB_ARCH="${DEB_ARCH:-amd64}"
APPIMAGE_ARCH="${APPIMAGE_ARCH:-x86_64}"

if [[ ! -f "${BINARY}" ]]; then
  echo "ERROR: expected Linux binary not found: ${BINARY}" >&2
  echo "Run BUILD_MODE=onefile scripts/build_linux_executable.sh first." >&2
  exit 1
fi

mkdir -p "${ASSETS_DIR}" "${BUILD_DIR}"
chmod +x "${BINARY}"
cp "${BINARY}" "${ASSETS_DIR}/${APP_NAME}-linux"
chmod +x "${ASSETS_DIR}/${APP_NAME}-linux"

DESKTOP_FILE="${BUILD_DIR}/${APP_ID}.desktop"
METAINFO_FILE="${BUILD_DIR}/${APP_ID}.metainfo.xml"
ICON_FILE="${BUILD_DIR}/${APP_ID}.png"

cat > "${DESKTOP_FILE}" <<EOF_DESKTOP
[Desktop Entry]
Type=Application
Name=DPO4000 Desk
GenericName=Oscilloscope Utility
Comment=Bench desktop application for Tektronix DPO4000-family oscilloscopes
Exec=${APP_COMMAND}
Icon=${APP_ID}
Terminal=false
Categories=Science;Engineering;Development;
StartupNotify=true
EOF_DESKTOP

cat > "${METAINFO_FILE}" <<EOF_META
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>${APP_ID}</id>
  <name>DPO4000 Desk</name>
  <summary>Bench desktop application for Tektronix DPO4000 oscilloscopes</summary>
  <metadata_license>MIT</metadata_license>
  <project_license>MIT</project_license>
  <description>
    <p>DPO4000 Desk provides screenshot capture, waveform export, measurement management, trigger controls, acquisition controls, and display setup for Tektronix DPO4000-family oscilloscopes.</p>
  </description>
  <launchable type="desktop-id">${APP_ID}.desktop</launchable>
  <releases>
    <release version="${VERSION}" date="2026-08-22" />
  </releases>
</component>
EOF_META

${PYTHON:-python3} - <<PY
from pathlib import Path
from PIL import Image
root = Path("${ROOT}")
out = Path("${ICON_FILE}")
source = root / "dpo4000_utils" / "gui" / "dpo_scope_icon.ico"
image = Image.open(source)
try:
    largest = max(getattr(image, "ico", image).sizes())
    image = image.resize(largest)
except Exception:
    pass
image = image.convert("RGBA")
image.thumbnail((256, 256))
out.parent.mkdir(parents=True, exist_ok=True)
image.save(out)
PY

build_deb() {
  local deb_root="${BUILD_DIR}/deb-root"
  rm -rf "${deb_root}"
  mkdir -p \
    "${deb_root}/DEBIAN" \
    "${deb_root}/usr/bin" \
    "${deb_root}/usr/share/applications" \
    "${deb_root}/usr/share/icons/hicolor/256x256/apps" \
    "${deb_root}/usr/share/metainfo" \
    "${deb_root}/usr/share/doc/dpo4000-desk"

  install -m 0755 "${BINARY}" "${deb_root}/usr/bin/${APP_COMMAND}"
  install -m 0644 "${DESKTOP_FILE}" "${deb_root}/usr/share/applications/${APP_ID}.desktop"
  install -m 0644 "${ICON_FILE}" "${deb_root}/usr/share/icons/hicolor/256x256/apps/${APP_ID}.png"
  install -m 0644 "${METAINFO_FILE}" "${deb_root}/usr/share/metainfo/${APP_ID}.metainfo.xml"
  install -m 0644 "${ROOT}/README.md" "${deb_root}/usr/share/doc/dpo4000-desk/README.md"

  local installed_size
  installed_size="$(du -sk "${deb_root}/usr" | cut -f1)"

  cat > "${deb_root}/DEBIAN/control" <<EOF_CONTROL
Package: dpo4000-desk
Version: ${VERSION}
Section: science
Priority: optional
Architecture: ${DEB_ARCH}
Maintainer: Aleksandr Chasnyk <69671996+ami3go@users.noreply.github.com>
Installed-Size: ${installed_size}
Depends: libegl1, libgl1, libxcb-cursor0, libxkbcommon-x11-0
Homepage: https://github.com/ami3go/Tektronix_DPO4000_utils
Description: DPO4000 Desk oscilloscope bench desktop application
 DPO4000 Desk is a desktop application built on dpo4000-utils for
 Tektronix DPO4000-family oscilloscopes. It supports screenshot capture,
 waveform export, measurement management, trigger/acquisition controls,
 and display setup.
EOF_CONTROL

  dpkg-deb --build "${deb_root}" "${ASSETS_DIR}/dpo4000-desk_${VERSION}_${DEB_ARCH}.deb"
}

build_appimage() {
  local appdir="${BUILD_DIR}/${APP_NAME}.AppDir"
  rm -rf "${appdir}"
  mkdir -p \
    "${appdir}/usr/bin" \
    "${appdir}/usr/share/applications" \
    "${appdir}/usr/share/icons/hicolor/256x256/apps" \
    "${appdir}/usr/share/metainfo"

  install -m 0755 "${BINARY}" "${appdir}/usr/bin/${APP_COMMAND}"
  install -m 0644 "${DESKTOP_FILE}" "${appdir}/usr/share/applications/${APP_ID}.desktop"
  install -m 0644 "${DESKTOP_FILE}" "${appdir}/${APP_ID}.desktop"
  install -m 0644 "${METAINFO_FILE}" "${appdir}/usr/share/metainfo/${APP_ID}.metainfo.xml"
  install -m 0644 "${ICON_FILE}" "${appdir}/usr/share/icons/hicolor/256x256/apps/${APP_ID}.png"
  install -m 0644 "${ICON_FILE}" "${appdir}/${APP_ID}.png"

  cat > "${appdir}/AppRun" <<'EOF_APPRUN'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(dirname "$(readlink -f "$0")")"
exec "${HERE}/usr/bin/dpo4000-desk" "$@"
EOF_APPRUN
  chmod +x "${appdir}/AppRun"

  local appimagetool="${APPIMAGETOOL:-${BUILD_DIR}/appimagetool-${APPIMAGE_ARCH}.AppImage}"
  if [[ ! -x "${appimagetool}" ]]; then
    wget -O "${appimagetool}" "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${APPIMAGE_ARCH}.AppImage"
    chmod +x "${appimagetool}"
  fi

  APPIMAGE_EXTRACT_AND_RUN=1 ARCH="${APPIMAGE_ARCH}" "${appimagetool}" \
    "${appdir}" "${ASSETS_DIR}/${APP_NAME}-${APPIMAGE_ARCH}.AppImage"
  chmod +x "${ASSETS_DIR}/${APP_NAME}-${APPIMAGE_ARCH}.AppImage"
}

build_flatpak() {
  if [[ "${BUILD_FLATPAK}" != "1" ]]; then
    echo "Skipping Flatpak bundle because BUILD_FLATPAK=${BUILD_FLATPAK}."
    return 0
  fi
  if ! command -v flatpak-builder >/dev/null 2>&1 || ! command -v flatpak >/dev/null 2>&1; then
    if [[ "${REQUIRE_FLATPAK}" == "1" ]]; then
      echo "ERROR: flatpak and flatpak-builder are required but are not installed." >&2
      exit 1
    fi
    echo "Skipping Flatpak bundle because flatpak-builder is not available."
    return 0
  fi

  local manifest="${BUILD_DIR}/${APP_ID}.yml"
  local flatpak_build="${BUILD_DIR}/flatpak-build"
  local flatpak_repo="${BUILD_DIR}/flatpak-repo"

  cat > "${manifest}" <<EOF_MANIFEST
app-id: ${APP_ID}
runtime: org.freedesktop.Platform
runtime-version: '${FLATPAK_RUNTIME_VERSION}'
sdk: org.freedesktop.Sdk
command: ${APP_COMMAND}
finish-args:
  - --share=ipc
  - --share=network
  - --socket=x11
  - --socket=wayland
  - --device=all
  - --filesystem=home
modules:
  - name: dpo4000-desk
    buildsystem: simple
    build-commands:
      - install -Dm755 DPO4000Desk /app/bin/${APP_COMMAND}
      - install -Dm644 ${APP_ID}.desktop /app/share/applications/${APP_ID}.desktop
      - install -Dm644 ${APP_ID}.metainfo.xml /app/share/metainfo/${APP_ID}.metainfo.xml
      - install -Dm644 ${APP_ID}.png /app/share/icons/hicolor/256x256/apps/${APP_ID}.png
    sources:
      - type: file
        path: ${BINARY}
        dest-filename: DPO4000Desk
      - type: file
        path: ${DESKTOP_FILE}
      - type: file
        path: ${METAINFO_FILE}
      - type: file
        path: ${ICON_FILE}
EOF_MANIFEST

  rm -rf "${flatpak_build}" "${flatpak_repo}"
  flatpak-builder --force-clean --default-branch=stable --repo="${flatpak_repo}" "${flatpak_build}" "${manifest}"
  flatpak build-bundle "${flatpak_repo}" "${ASSETS_DIR}/${APP_NAME}.flatpak" "${APP_ID}" stable
}

build_deb
build_appimage
build_flatpak

printf '\nRelease assets created in %s:\n' "${ASSETS_DIR}"
find "${ASSETS_DIR}" -maxdepth 1 -type f -printf '  %f\n' | sort
