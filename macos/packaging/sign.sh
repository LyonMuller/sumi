#!/bin/bash
# Signs Sumi.app inside-out: every Mach-O in Contents/Resources/engine first (deepest first), then the
# two engine executables with their entitlements, then the app itself.
#
#   packaging/sign.sh macos/build/Sumi.app
#   packaging/sign.sh --print-identity     # only prints the identity that would be used
#
# Environment (all optional):
#   SUMI_SIGN_IDENTITY  codesign identity. Default: "Developer ID Application" if the keychain has
#                       one, else "Apple Development", else ad-hoc ("-").
#   SUMI_TIMESTAMP      "auto" (default: Apple timestamp server for real identities, none for
#                       ad-hoc), "none" to skip it (offline builds).
#   SUMI_HARDENED       "auto" (default: hardened runtime for real identities), "1" or "0".
#                       Ad-hoc signatures cannot satisfy library validation, so auto leaves it off.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
bundle_id="dev.lyon.Sumi"

identity="${SUMI_SIGN_IDENTITY:-}"
if [[ -z "$identity" ]]; then
    listing="$(security find-identity -v -p codesigning)"
    identity="$(awk -F'"' '/Developer ID Application/ {print $2; exit}' <<<"$listing")"
    [[ -n "$identity" ]] || identity="$(awk -F'"' '/Apple Development/ {print $2; exit}' <<<"$listing")"
    [[ -n "$identity" ]] || identity="-"
fi
# release.sh asks which identity will be used to sign the DMG with the same rules.
if [[ "${1:-}" == "--print-identity" ]]; then
    echo "$identity"
    exit 0
fi

app="${1:?Uso: sign.sh Sumi.app}"
engine_root="$app/Contents/Resources/engine"

hardened="${SUMI_HARDENED:-auto}"
[[ "$hardened" == "auto" ]] && { [[ "$identity" == "-" ]] && hardened=0 || hardened=1; }
timestamp="${SUMI_TIMESTAMP:-auto}"
[[ "$timestamp" == "auto" ]] && { [[ "$identity" == "-" ]] && timestamp=none || timestamp=apple; }

common=(--force --sign "$identity")
[[ "$hardened" == "1" ]] && common+=(--options runtime)
[[ "$timestamp" == "none" ]] && common+=(--timestamp=none) || common+=(--timestamp)
echo "Assinando com: $identity (hardened runtime: $hardened, timestamp: $timestamp)"

engine_exe="$engine_root/SumiEngine"
output_exe="$engine_root/_internal/video_output/SumiVideoOutput"

# codesign wrapper: Apple's timestamp service occasionally answers with a stale time or times out
# ("timestamps differ by N seconds"), so retry a few times before giving up.
sign() {
    local attempt log
    for attempt in 1 2 3 4 5; do
        if log="$(codesign "$@" 2>&1)"; then
            return 0
        fi
        sleep 2
    done
    echo "$log" >&2
    echo "Falha ao assinar: ${*: -1}" >&2
    return 1
}

# Mach-O files (thin, fat or dylib), deepest paths first, without the executables handled below.
macho_files() {
    python3 - "$1" "$engine_exe" "$output_exe" <<'PY'
import os, sys
root, *skip = sys.argv[1:]
magics = {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}
found = []
for folder, _, names in os.walk(root):
    for name in names:
        path = os.path.join(folder, name)
        if os.path.islink(path) or path in skip:
            continue
        try:
            with open(path, 'rb') as handle:
                if handle.read(4) in magics:
                    found.append(path)
        except OSError:
            pass
for path in sorted(found, key=lambda p: (-p.count('/'), p)):
    print(path)
PY
}

if [[ -d "$engine_root" ]]; then
    count=0
    while IFS= read -r file; do
        sign "${common[@]}" "$file"
        count=$((count + 1))
    done < <(macho_files "$engine_root")
    echo "Mach-O assinados: $count"
    if [[ -x "$output_exe" ]]; then
        sign "${common[@]}" --identifier "$bundle_id.video-output" "$output_exe"
    fi
    sign "${common[@]}" --identifier "$bundle_id.engine" \
        --entitlements "$here/entitlements-engine.plist" "$engine_exe"
fi

# Sparkle, inside-out: its helper app and installer tool, then the framework.
sparkle="$app/Contents/Frameworks/Sparkle.framework"
if [[ -d "$sparkle" ]]; then
    sign "${common[@]}" "$sparkle/Versions/B/Updater.app"
    sign "${common[@]}" "$sparkle/Versions/B/Autoupdate"
    sign "${common[@]}" "$sparkle"
fi

sign "${common[@]}" --identifier "$bundle_id" --entitlements "$here/entitlements-app.plist" "$app"

codesign --verify --deep --strict --verbose=2 "$app"
echo "codesign --verify: ok"
spctl -a -vv "$app" || echo "spctl: rejeitado, esperado sem notarização (use 'Abrir mesmo assim')."
