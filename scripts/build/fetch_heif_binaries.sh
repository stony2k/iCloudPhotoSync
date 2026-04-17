#!/usr/bin/env bash
#
# Build the bundled heif-convert tree under bin/heif/ by extracting Debian
# bookworm packages for amd64 / arm64 / armhf. Resulting layout per arch:
#
#   bin/heif/<arch>/heif-convert
#   bin/heif/<arch>/lib/<runtime .so files>
#   bin/heif/<arch>/lib/libheif/plugins/libheif-libde265.so
#
# Run in Linux / WSL with curl, tar, dpkg-deb, patchelf. Produces about 4 MB
# per arch. Re-run when you want to bump libheif / libde265 versions.
#
# Why Debian bookworm: DSM ships glibc 2.36, which matches bookworm's glibc
# exactly. Debian's libheif 1.19 (from bookworm-backports) uses the plugin
# architecture, which means the encoder libs (libx265 / libaom / libdav1d)
# are lazy-loaded — we never load them since we only decode HEIC and only
# write JPG. That keeps the bundle small (~1.5 MB core + ~3 MB libtiff deps).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUT_ROOT="$PROJECT_ROOT/bin/heif"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

BASE="https://deb.debian.org/debian/pool/main"

# Package list shared by all archs. The arch suffix is substituted per call.
# Versions pinned so rebuilds produce byte-identical bundles. Bump together
# when upstream libheif changes.
PACKAGES=(
    "libh/libheif/libheif-examples_1.19.7-1~bpo12+1"
    "libh/libheif/libheif1_1.19.7-1~bpo12+1"
    "libh/libheif/libheif-plugin-libde265_1.19.7-1~bpo12+1"
    "libd/libde265/libde265-0_1.0.11-1+deb12u2"
    "libj/libjpeg-turbo/libjpeg62-turbo_2.1.5-2"
    "t/tiff/libtiff6_4.5.0-6+deb12u3"
    "libz/libzstd/libzstd1_1.5.4+dfsg2-5"
    "x/xz-utils/liblzma5_5.4.1-1"
    "l/lerc/liblerc4_4.0.0+ds-2"
    "j/jbigkit/libjbig0_2.1-6.1"
    "libd/libdeflate/libdeflate0_1.14-1"
)

# our_arch -> debian_arch
declare -A DEB_ARCH=(
    [x86_64]=amd64
    [aarch64]=arm64
    [armv7]=armhf
)

fetch_one() {
    local arch="$1"
    local deb_arch="${DEB_ARCH[$arch]}"
    local work="$TMP_ROOT/$arch"
    local bundle="$work/bundle"
    local out="$OUT_ROOT/$arch"

    echo "=== $arch (debian: $deb_arch) ==="
    mkdir -p "$work" "$bundle"

    for pkg in "${PACKAGES[@]}"; do
        local url="$BASE/${pkg}_${deb_arch}.deb"
        local fname=$(basename "${pkg}_${deb_arch}.deb")
        echo "  fetch $fname"
        curl -fsSLo "$work/$fname" "$url"
        dpkg-deb -x "$work/$fname" "$bundle"
    done

    # Debian's multiarch triplet varies per arch. Detect it.
    local triplet
    triplet=$(find "$bundle/usr/lib" -maxdepth 1 -type d -name "*-linux-gnu*" -printf '%f\n' | head -1)
    echo "  triplet: $triplet"

    rm -rf "$out"
    mkdir -p "$out/lib/libheif/plugins"

    cp "$bundle/usr/bin/heif-convert" "$out/heif-convert"

    # Copy every .so at the top level of both lib trees — some packages put
    # files in /lib/<triplet> (like liblzma) and others in /usr/lib/<triplet>.
    for libdir in "$bundle/lib/$triplet" "$bundle/usr/lib/$triplet"; do
        [ -d "$libdir" ] || continue
        find "$libdir" -maxdepth 1 -name "*.so*" -exec cp -a {} "$out/lib/" \;
    done

    cp -a "$bundle/usr/lib/$triplet/libheif/plugins/"*.so "$out/lib/libheif/plugins/"

    # Collapse symlinks: keep a single file under the SONAME-named path.
    # This saves space and makes the bundle portable to filesystems (e.g.
    # Windows NTFS in a WSL workflow) that don't support symlinks well.
    (
        cd "$out/lib"
        for link in $(find . -maxdepth 1 -type l); do
            target=$(readlink "$link")
            [ -f "$target" ] || continue
            rm "$link"
            mv "$target" "$link"
        done
        # Any remaining versioned files (no SONAME link pointed at them) can go.
        find . -maxdepth 1 -name "*.so.*.*" -delete 2>/dev/null || true
    )

    chmod +x "$out/heif-convert"
    du -sh "$out"
}

mkdir -p "$OUT_ROOT"

for arch in x86_64 aarch64 armv7; do
    fetch_one "$arch"
done

echo
echo "Done. Layout:"
find "$OUT_ROOT" -maxdepth 3 -type d | sort
echo
echo "Sizes:"
du -sh "$OUT_ROOT"/*
