#!/bin/bash
# Builds the installable disk image (macos/dist/Sumi-VERSION.dmg + .sha256) and the in-app update:
# Sumi-VERSION.zip signed with the Sparkle EdDSA key, plus appcast.xml. Upload all of them to the
# GitHub release v<VERSION>; installed apps read releases/latest/download/appcast.xml.
#
#   macos/release.sh 0.7.0
#
# Steps: environment (python, OpenCV without FFmpeg) -> frozen engine -> Sumi.app (signed inside-out)
# -> audit -> DMG with Applications link -> sign the DMG -> checksum -> update archive and appcast.
#
# Signing and notarization are controlled by environment variables, all optional:
#   SUMI_SIGN_IDENTITY   e.g. "Developer ID Application: Name (TEAMID)". Default: the keychain's
#                        Developer ID, else "Apple Development", else ad-hoc (see packaging/sign.sh).
#   SUMI_NOTARY_PROFILE  name of a `xcrun notarytool store-credentials` profile. When set, the app and
#                        then the DMG are notarized and stapled. Needs a Developer ID identity.
#   SUMI_REUSE_ENGINE=1  skip bootstrap and the engine freeze when macos/.cache/engine already exists.
#
# The DMG background is optional: assets/brand/dmg-background.png (660x400) and, for Retina,
# dmg-background@2x.png (1320x800) next to it.
set -euo pipefail

version="${1:?Uso: macos/release.sh VERSION (ex.: 0.7.0)}"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.]+)?$ ]] || { echo "Versão inválida: $version" >&2; exit 2; }

here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
cache="$here/.cache"
dist="$here/dist"
app="$here/build/Sumi.app"
dmg="$dist/Sumi-$version.dmg"
volume="Sumi"
brand="$root/assets/brand"

# 1. Environment and engine.
if [[ "${SUMI_REUSE_ENGINE:-0}" != "1" || ! -x "$cache/engine/SumiEngine/SumiEngine" ]]; then
    "$here/packaging/bootstrap.sh"
    "$here/packaging/build-engine.sh"
fi

# 2. The app, signed inside-out by build-app.sh.
SUMI_VERSION="$version" "$here/build-app.sh" --bundle

# 3. Audit: portability and GPL media libraries.
python3 "$here/packaging/audit_bundle.py" "$app" --max-minos 15.0

notarize() {  # notarize <file>: submit and wait; needs SUMI_NOTARY_PROFILE
    xcrun notarytool submit "$1" --keychain-profile "$SUMI_NOTARY_PROFILE" --wait
}
if [[ -n "${SUMI_NOTARY_PROFILE:-}" ]]; then
    zip="$(mktemp -d)/Sumi.zip"
    ditto -c -k --keepParent "$app" "$zip"
    notarize "$zip"
    xcrun stapler staple "$app"
fi

# 4. DMG: dmgbuild writes the window layout straight into .DS_Store (no Finder, no AppleScript).
mkdir -p "$dist"
rm -f "$dmg" "$dmg.sha256" "$dist/Sumi-$version.zip" "$dist/appcast.xml"
work="$(mktemp -d)"
background=""
if [[ -f "$brand/dmg-background@2x.png" && -f "$brand/dmg-background.png" ]]; then
    background="$work/background.tiff"
    tiffutil -cathidpicheck "$brand/dmg-background.png" "$brand/dmg-background@2x.png" -out "$background"
elif [[ -f "$brand/dmg-background.png" ]]; then
    background="$brand/dmg-background.png"
fi
cat > "$work/settings.py" <<'PY'
import os
app = os.environ['SUMI_DMG_APP']
files = [app]
symlinks = {'Applications': '/Applications'}
background = os.environ.get('SUMI_DMG_BACKGROUND') or None
icon = os.environ.get('SUMI_DMG_ICON') or None
format = 'UDZO'
compression_level = 9
filesystem = 'HFS+'
window_rect = ((200, 140), (660, 400))
default_view = 'icon-view'
icon_size = 120
text_size = 13
show_icon_preview = False
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
icon_locations = {os.path.basename(app): (165, 200), 'Applications': (495, 200)}
PY
if SUMI_DMG_APP="$app" SUMI_DMG_BACKGROUND="$background" SUMI_DMG_ICON="$here/build/AppIcon.icns" \
    "$cache/venv/bin/python" -m dmgbuild -s "$work/settings.py" "$volume" "$dmg"; then
    :
else
    echo "dmgbuild falhou; criando o DMG simples com hdiutil." >&2
    staging="$work/staging"
    mkdir -p "$staging"
    ditto "$app" "$staging/Sumi.app"
    ln -s /Applications "$staging/Applications"
    hdiutil create -volname "$volume" -srcfolder "$staging" -format UDZO -imagekey zlib-level=9 -ov "$dmg"
fi
rm -rf "$work"

# 5. Sign the DMG with the same identity as the app.
identity="$("$here/packaging/sign.sh" --print-identity)"
if [[ "$identity" == "-" ]]; then
    codesign --force --sign - "$dmg"
else
    codesign --force --sign "$identity" --timestamp "$dmg"
fi
if [[ -n "${SUMI_NOTARY_PROFILE:-}" ]]; then
    notarize "$dmg"
    xcrun stapler staple "$dmg"
fi

# 6. Checksum and verification.
(cd "$dist" && shasum -a 256 "$(basename "$dmg")" > "$(basename "$dmg").sha256")
hdiutil verify "$dmg" >/dev/null
codesign --verify --verbose=2 "$dmg"
spctl -a -t open --context context:primary-signature -vv "$dmg" || echo "spctl: rejeitado, esperado sem notarização (use 'Abrir mesmo assim')."
ls -lh "$dmg" "$dmg.sha256"
cat "$dmg.sha256"

# 7. In-app update: zip of the app, EdDSA signature (private key in the login keychain, account
#    dev.lyon.Sumi; backup in 1Password) and the appcast with this version's CHANGELOG section.
archive="$dist/Sumi-$version.zip"
ditto -c -k --sequesterRsrc --keepParent "$app" "$archive"
signature="$("$here/.build/artifacts/sparkle/Sparkle/bin/sign_update" --account dev.lyon.Sumi "$archive")"
python3 "$root/tools/make_appcast.py" --version "$version" --archive "$archive" \
    --signature "$signature" --output "$dist/appcast.xml"
ls -lh "$archive" "$dist/appcast.xml"
