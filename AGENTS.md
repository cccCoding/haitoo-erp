# 项目约定

## Docker 环境选择

- 本机测试的所有 Compose 操作必须使用 `./deploy/local.sh <子命令> [参数]`，固定为 `--env-file .env.local -p haitoo-test -f docker-compose.yml -f docker-compose.local.yml`。
- 腾讯云服务器的所有 Compose 操作必须使用 `./deploy/tencent.sh <子命令> [参数]`，固定为 `--env-file .env -p haitorok -f docker-compose.yml -f docker-compose.tencent.yml`。
- 禁止执行或向用户提供省略环境参数的裸 `docker compose` 命令。构建、启动、停止、迁移、日志、容器内命令都遵守同一规则。
- 给出部署命令时明确区分本机和腾讯云；不要创建默认名为 `haitoo-erp` 的 Compose 项目，也不要覆盖已有环境文件或数据库卷。
- 脚本缺少所需文件或拒绝覆盖参数时，修正调用方式，不要绕过固定入口。

## 技能说明语言

- 创建或修改任何 Codex Skill 时，`SKILL.md` 始终使用中文。
- 技能脚本、代码标识符、命令、文件名和必要英文触发词可保留英文；说明、流程、规则及用户可读内容优先使用中文。
