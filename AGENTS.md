# 项目约定

## Docker 环境选择

- 本机测试的所有 Compose 操作必须使用 `./deploy/local.sh <子命令> [参数]`，固定为 `--env-file .env.local -p haitoo-test -f docker-compose.yml -f docker-compose.local.yml`。
- 腾讯云服务器的所有 Compose 操作必须使用 `./deploy/tencent.sh <子命令> [参数]`，固定为 `--env-file .env -p haitorok -f docker-compose.yml -f docker-compose.tencent.yml`。
- 禁止执行或向用户提供省略环境参数的裸 `docker compose` 命令。构建、启动、停止、迁移、日志、容器内命令都遵守同一规则。
- 给出部署命令时明确区分本机和腾讯云；不要创建默认名为 `haitoo-erp` 的 Compose 项目，也不要覆盖已有环境文件或数据库卷。
- 脚本缺少所需文件或拒绝覆盖参数时，修正调用方式，不要绕过固定入口。

## 浏览器调试清理

- 浏览器调试使用独立会话或临时配置目录，记录本次创建的会话、窗口和标签页。
- 调试结束（包括失败、中断和超时）后，关闭本次创建的调试会话、窗口和标签页，并确认没有遗留。
- 必须保留用户自行打开的 Chrome 窗口和页面；禁止使用 `killall`、宽泛的 `pkill` 或退出整个 Chrome 的方式清理。
- 只有明确确认归属的调试实例才可关闭；无法确认归属时保留并说明情况。

## 前端本机调试

- 仅修改前端时，优先复用已有 `node_modules` 并使用 Vite 热更新，不反复构建整套 Docker 服务或执行 `npm ci`；依赖未安装或锁文件变化时才安装依赖。
- 本机 Vite 使用 `VITE_API_URL=http://localhost:8001`，运营端端口为 5173，管理端为 5174，绑定 `127.0.0.1` 并启用 `--strictPort`。端口被同环境前端容器占用时，只通过 `./deploy/local.sh stop web` 或 `./deploy/local.sh stop admin-web` 释放对应端口；调试结束后关闭 Vite，并恢复本次停止的服务。
- 验证 Docker 部署或更新腾讯云时，只构建和更新改动的服务，保留构建缓存；不要默认使用 `--pull`、`--no-cache` 或清理镜像。`--pull=false` 不能保证离线构建，基础镜像缺失时仍需获取镜像。

## 技能说明语言

- 创建或修改任何 Codex Skill 时，`SKILL.md` 始终使用中文。
- 技能脚本、代码标识符、命令、文件名和必要英文触发词可保留英文；说明、流程、规则及用户可读内容优先使用中文。
