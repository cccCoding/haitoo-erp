#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PROJECT_PYTHON="$(pwd)/../.venv/bin/python"
[[ -x "$PROJECT_PYTHON" ]] || { echo "未找到项目 .venv/bin/python" >&2; exit 1; }
RELEASE=false
if [[ "${1:-}" == "--release" ]]; then RELEASE=true; elif [[ $# -gt 0 ]]; then echo '用法：./build_macos.sh [--release]' >&2; exit 1; fi
if $RELEASE; then
  : "${HAITOO_MAC_SIGN_IDENTITY:?请配置 Developer ID Application 签名身份}"
  : "${HAITOO_MAC_NOTARY_PROFILE:?请配置 notarytool 钥匙串凭据名称}"
  : "${HAITOO_RELEASE_PRIVATE_KEY:?请指定离线 Ed25519 私钥文件}"
  : "${HAITOO_RELEASE_KEY_ID:?请配置发布 key_id}"
  "$PROJECT_PYTHON" -c 'import json; assert json.load(open("trusted_keys.json")), "正式构建必须内置发布公钥"'
fi
AGENT_VERSION="$("$PROJECT_PYTHON" -c 'import json; print(json.load(open("agent-version.json"))["version"])')"
AGENT_ARCH="$("$PROJECT_PYTHON" -c 'import platform; print("arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64")')"
BASENAME="HaitooHubAgent-macos-$AGENT_ARCH-$AGENT_VERSION"
PACKAGE_DIRECTORY="$(mktemp -d "${TMPDIR:-/tmp}/haitoo-connector-package.XXXXXX")"
trap 'rm -rf "$PACKAGE_DIRECTORY"' EXIT
if $RELEASE; then
  # PyInstaller 的 codesign_identity 确保嵌套 Mach-O 先签名，最后签应用整体。
  "$PROJECT_PYTHON" -m PyInstaller --noconfirm --windowed --osx-bundle-identifier com.haitoo.hub-agent --codesign-identity "$HAITOO_MAC_SIGN_IDENTITY" --osx-entitlements-file install/macos/entitlements.plist --add-data "trusted_keys.json:." --add-data "agent-version.json:." --name HaitooHubAgent haitoo_hub_agent.py
  codesign --force --options runtime --timestamp --entitlements install/macos/entitlements.plist --sign "$HAITOO_MAC_SIGN_IDENTITY" dist/HaitooHubAgent.app
  codesign --verify --deep --strict dist/HaitooHubAgent.app
  ditto -c -k --keepParent dist/HaitooHubAgent.app "$PACKAGE_DIRECTORY/notarize.zip"
  xcrun notarytool submit "$PACKAGE_DIRECTORY/notarize.zip" --keychain-profile "$HAITOO_MAC_NOTARY_PROFILE" --wait
  xcrun stapler staple dist/HaitooHubAgent.app
  spctl --assess --type execute dist/HaitooHubAgent.app
  mkdir "$PACKAGE_DIRECTORY/dmg"
  ditto dist/HaitooHubAgent.app "$PACKAGE_DIRECTORY/dmg/HaitooHubAgent.app"
  ln -s /Applications "$PACKAGE_DIRECTORY/dmg/Applications"
  hdiutil create -volname 'Haitoo Hub 连接器' -srcfolder "$PACKAGE_DIRECTORY/dmg" -ov -format UDZO "dist/$BASENAME.dmg"
  codesign --timestamp --sign "$HAITOO_MAC_SIGN_IDENTITY" "dist/$BASENAME.dmg"
  xcrun notarytool submit "dist/$BASENAME.dmg" --keychain-profile "$HAITOO_MAC_NOTARY_PROFILE" --wait
  xcrun stapler staple "dist/$BASENAME.dmg"
  "$PROJECT_PYTHON" package_release.py --source dist/HaitooHubAgent.app --output "dist/$BASENAME-update.zip" --preserve-links
  "$PROJECT_PYTHON" sign_release.py --package "dist/$BASENAME-update.zip" --installer "dist/$BASENAME.dmg" --key "$HAITOO_RELEASE_PRIVATE_KEY" --key-id "$HAITOO_RELEASE_KEY_ID" --version "$AGENT_VERSION" --platform macos --arch "$AGENT_ARCH" --kind agent --entrypoint HaitooHubAgent.app/Contents/MacOS/HaitooHubAgent --output "dist/$BASENAME-manifest.json"
  echo "正式发布产物：dist/$BASENAME.dmg、-update.zip、-manifest.json"
else
  "$PROJECT_PYTHON" -m PyInstaller --noconfirm --windowed --osx-bundle-identifier com.haitoo.hub-agent --add-data "trusted_keys.json:." --add-data "agent-version.json:." --name HaitooHubAgent haitoo_hub_agent.py
  "$PROJECT_PYTHON" -m PyInstaller --noconfirm --console --add-data "trusted_keys.json:." --add-data "agent-version.json:." --name HaitooHubAgentConsole haitoo_hub_agent.py
  cp start_and_pair_macos.command dist/启动并配对.command
  chmod +x dist/启动并配对.command
  (cd dist && zip -qry "$PACKAGE_DIRECTORY/$BASENAME.zip" HaitooHubAgent.app HaitooHubAgentConsole 启动并配对.command)
  mv "$PACKAGE_DIRECTORY/$BASENAME.zip" "dist/$BASENAME.zip"
  echo "内部测试 ZIP：dist/$BASENAME.zip；正式发布请使用 --release 完成签名及公证。"
fi
