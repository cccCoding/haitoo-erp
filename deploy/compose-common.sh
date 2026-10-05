#!/bin/sh
# 固定部署目标，避免遗漏参数创建另一套容器和数据库。
set -eu

compose_root=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
case "${1-}" in
  local)
    compose_env_file=.env.local
    compose_project=haitoo-test
    compose_overlay=docker-compose.local.yml
    compose_entry=local.sh
    ;;
  tencent)
    compose_env_file=.env
    compose_project=haitorok
    compose_overlay=docker-compose.tencent.yml
    compose_entry=tencent.sh
    ;;
  *)
    printf '%s\n' '请通过 deploy/local.sh 或 deploy/tencent.sh 调用。' >&2
    exit 2
    ;;
esac
shift

if [ "$#" -eq 0 ] || [ "$1" = '--help' ]; then
  printf '用法：./deploy/%s <Compose 子命令> [参数]\n' "$compose_entry"
  printf '固定环境：%s；项目：%s；配置：docker-compose.yml + %s\n' \
    "$compose_env_file" "$compose_project" "$compose_overlay"
  exit 0
fi
case "$1" in
  -*)
    printf '%s\n' '请直接填写 Compose 子命令，例如 up、build、ps、logs、exec。' >&2
    exit 2
    ;;
esac

compose_command=$1
for compose_arg in "$@"; do
  # logs -f 是跟随日志，不是覆盖 Compose 文件。
  if [ "$compose_command" = logs ] && [ "$compose_arg" = '-f' ]; then
    continue
  fi
  case "$compose_arg" in
    --env-file|--env-file=*|--project-name|--project-name=*|-p*|\
    --file|--file=*|-f*|--project-directory|--project-directory=*|\
    --profile|--profile=*)
      printf '环境参数由脚本固定，禁止覆盖：%s\n' "$compose_arg" >&2
      exit 2
      ;;
  esac
done

cd "$compose_root"
for compose_required in "$compose_env_file" docker-compose.yml "$compose_overlay"; do
  if [ ! -f "$compose_required" ]; then
    printf '缺少文件：%s/%s；已停止，未调用 Docker。\n' "$compose_root" "$compose_required" >&2
    exit 2
  fi
done

unset COMPOSE_FILE COMPOSE_PROJECT_NAME COMPOSE_PROFILES COMPOSE_ENV_FILES
printf '部署目标：%s；环境文件：%s；配置：docker-compose.yml + %s\n' \
  "$compose_project" "$compose_env_file" "$compose_overlay" >&2
exec docker compose --env-file "$compose_env_file" -p "$compose_project" \
  -f docker-compose.yml -f "$compose_overlay" "$@"
