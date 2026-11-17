#!/bin/bash
# Run from a synced OrangeFox fox_12.1 source checkout.
set -eo pipefail
TREE="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="${1:?usage: tools/build-recovery.sh /path/to/OrangeFox/source}"
SOURCE="$(realpath "$SOURCE")"
EXPECTED="$SOURCE/device/xiaomi/camellia"
[ "$TREE" = "$EXPECTED" ] || { echo "Place this tree at $EXPECTED before building" >&2; exit 1; }
[ -f "$SOURCE/build/envsetup.sh" ] || { echo "OrangeFox source is not synced" >&2; exit 1; }
python3 "$TREE/tools/validate-tree.py"
export FOX_BUILD_DEVICE=camellia
export ALLOW_MISSING_DEPENDENCIES=true
export LC_ALL=C
cd "$SOURCE"
set +e
# shellcheck source=/dev/null
source "$SOURCE/build/envsetup.sh"
lunch twrp_camellia-eng
rc=$?
set -e
[ "$rc" = 0 ] || exit "$rc"
if grep -q 'vendor-boot-v3.mk' "$TREE/recovery-layout.mk"; then
  m -j"${JOBS:-4}" adbd bootimage vendorbootimage
else
  m -j"${JOBS:-4}" adbd bootimage
fi
