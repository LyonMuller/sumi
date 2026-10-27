#!/bin/bash
# Builds macos/build/Sumi.app.
#
#   macos/build-app.sh                  # development: debug build, engine from the repository's .venv
#   macos/build-app.sh --dev release    # same, optimized Swift build
#   macos/build-app.sh --bundle         # self-contained: frozen engine inside the app, release build
#
# --dev   The app runs main.py --service from this repository's .venv, so Python changes need no
#         rebuild. The repository path is written to Info.plist; the app only works on this Mac.
# --bundle  Embeds the engine from macos/.cache/engine (run packaging/build-engine.sh first, or let
#         release.sh do everything), adds the third-party notices and signs inside-out.
#
# Environment: SUMI_VERSION (default: sumi.__version__), SUMI_SIGN_IDENTITY,
# SUMI_TIMESTAMP, SUMI_HARDENED (see packaging/sign.sh).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(dirname "$here")"
mode="dev"
config="debug"
for argument in "$@"; do
    case "$argument" in
        --dev) mode="dev" ;;
        --bundle) mode="bundle"; config="release" ;;
        debug|release) config="$argument" ;;
        *) echo "Uso: $0 [--dev|--bundle] [debug|release]" >&2; exit 2 ;;
    esac
done
[[ "$mode" == "bundle" ]] && config="release"

app="$here/build/Sumi.app"
bundle_id="dev.lyon.Sumi"
version="${SUMI_VERSION:-$(sed -n "s/^__version__ = '\(.*\)'/\1/p" "$root/sumi/__init__.py")}"
version="${version:-0.7.0}"
engine="$here/.cache/engine/SumiEngine"  # PyInstaller folder: SumiEngine + _internal/

if [[ "$mode" == "dev" && ! -x "$root/.venv/bin/python" ]]; then
    echo "Motor não encontrado: crie o .venv do repositório (veja macos/README.md)." >&2
    exit 1
fi
if [[ "$mode" == "bundle" && ! -x "$engine/SumiEngine" ]]; then
    echo "Motor congelado não encontrado em $engine: rode macos/packaging/build-engine.sh." >&2
    exit 1
fi

swift build -c "$config" --package-path "$here" --product Sumi
binary="$(swift build -c "$config" --package-path "$here" --show-bin-path)/Sumi"

rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources" "$app/Contents/Frameworks"
cp "$binary" "$app/Contents/MacOS/Sumi"
install_name_tool -add_rpath "@executable_path/../Frameworks" "$app/Contents/MacOS/Sumi"

# Sparkle (in-app updates), arm64 only like the rest of the app. The XPC services exist for sandboxed
# apps; Sumi is not sandboxed, so Sparkle installs through Autoupdate directly.
sparkle="$app/Contents/Frameworks/Sparkle.framework"
ditto "$(dirname "$binary")/Sparkle.framework" "$sparkle"
for macho in "$sparkle/Versions/B/Sparkle" "$sparkle/Versions/B/Autoupdate" \
             "$sparkle/Versions/B/Updater.app/Contents/MacOS/Updater"; do
    lipo "$macho" -thin arm64 -output "$macho"
done
rm -rf "$sparkle/Versions/B/XPCServices" "$sparkle/XPCServices"

# Icon from the brand PNG, cached between builds.
icon="$here/build/AppIcon.icns"
if [[ ! -f "$icon" || "$root/assets/brand/app-icon-macos.png" -nt "$icon" ]]; then
    iconset="$(mktemp -d)/AppIcon.iconset"
    mkdir -p "$iconset"
    for size in 16 32 128 256 512; do
        sips -z $size $size "$root/assets/brand/app-icon-macos.png" --out "$iconset/icon_${size}x${size}.png" >/dev/null
        double=$((size * 2))
        sips -z $double $double "$root/assets/brand/app-icon-macos.png" --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
    done
    iconutil -c icns "$iconset" -o "$icon"
fi
cp "$icon" "$app/Contents/Resources/AppIcon.icns"

# Updates: the appcast is uploaded with each GitHub release (see release.sh). The public key pairs with
# the EdDSA private key in the login keychain (account dev.lyon.Sumi), backed up in 1Password.
feed_url="${SUMI_FEED_URL:-https://github.com/LyonMuller/sumi/releases/latest/download/appcast.xml}"
public_ed_key="uLMLiAF5e6nKIkeBwXEcKxwTlSxwn7DzATwQhbr0Rvw="

repository_key=""
if [[ "$mode" == "dev" ]]; then
    repository_key="<key>SumiRepository</key><string>$root</string>"
fi

cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key><string>$bundle_id</string>
    <key>CFBundleName</key><string>Sumi</string>
    <key>CFBundleDisplayName</key><string>Sumi</string>
    <key>CFBundleExecutable</key><string>Sumi</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>$version</string>
    <key>CFBundleVersion</key><string>$version</string>
    <key>CFBundleDevelopmentRegion</key><string>pt-BR</string>
    <key>LSMinimumSystemVersion</key><string>15.0</string>
    <key>LSApplicationCategoryType</key><string>public.app-category.video</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSCameraUsageDescription</key>
    <string>O Sumi usa a webcam para aplicar o efeito de desaparecer. A imagem fica só neste Mac.</string>
    <key>SUFeedURL</key><string>$feed_url</string>
    <key>SUPublicEDKey</key><string>$public_ed_key</string>
    <key>SUEnableAutomaticChecks</key><true/>
    $repository_key
</dict>
</plist>
PLIST
plutil -lint "$app/Contents/Info.plist" >/dev/null

if [[ "$mode" == "bundle" ]]; then
    # Resources, not Helpers: codesign wants every file under Contents/Helpers to be signed code, while
    # Resources are sealed as data. The Mach-O files inside are signed one by one by sign.sh.
    ditto "$engine" "$app/Contents/Resources/engine"
    "$here/.cache/venv/bin/python" "$here/packaging/make_notices.py" \
        --engine "$app/Contents/Resources/engine" --version "$version" \
        --output "$app/Contents/Resources/Licenses"
    "$here/packaging/sign.sh" "$app"
else
    # A stable certificate keeps the camera permission across rebuilds; ad-hoc asks again each time.
    identity="$(security find-identity -v -p codesigning | awk -F'"' '/Apple Development/ {print $2; exit}')"
    if [[ -n "$identity" ]]; then
        codesign --force --sign "$identity" "$sparkle/Versions/B/Updater.app"
        codesign --force --sign "$identity" "$sparkle/Versions/B/Autoupdate"
        codesign --force --sign "$identity" "$sparkle"
        codesign --force --sign "$identity" --identifier "$bundle_id" "$app"
        echo "Assinado com: $identity"
    else
        codesign --force --deep --sign - --identifier "$bundle_id" "$app"
        echo "Assinatura ad-hoc (sem certificado Apple Development): o macOS pode pedir a câmera de novo a cada build."
    fi
fi

echo "Pronto ($mode): $app"
