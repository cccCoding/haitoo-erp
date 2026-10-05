#!/bin/sh
# 本机测试固定入口，参数传递给 Docker Compose 子命令。
set -eu
exec sh "$(dirname "$0")/compose-common.sh" local "$@"
