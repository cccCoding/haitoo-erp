# Haitoro AI 工作台

多公司、多成员的 TikTok POD 运营系统 MVP。当前版本包含：

- FastAPI + MySQL 8 后端，包含 JWT 登录、公司/角色/店铺授权边界。
- 产品模板、印花贴合模拟任务、人工选图和商品草稿 API。
- Vue 3 运营端工作台，覆盖模板库、POD 工作台、任务与草稿。

登录接口 `/auth/login` 共用于运营端和超级管理员后台。同一 IP 自首次尝试起 60 秒内可登录 20 次；同一邮箱自首次密码失败起 15 分钟内可失败 5 次。下一次请求返回 HTTP 429 和 `Retry-After`，到期后自动恢复；成功登录会清除该邮箱的失败计数。计数存于 MySQL，多个 API worker 共用。升级时先运行 `./deploy/local.sh run --rm migrate`，再重启 API；`20260929_18` 迁移会创建计数表。

Docker 部署默认从内部代理获取客户端 IP：Cloudflare Tunnel 使用 `CF-Connecting-IP`，腾讯云 Nginx 使用其覆写的 `X-Real-IP`。直接运行后端时默认只使用连接地址。不要将 API 容器端口直接公开到互联网。

数据库标准：MySQL 不使用外键；关联字段以普通 ID 和索引保存，所有权限、存在性及删除限制由应用层校验。

妙手接入标准：妙手 App ID 和 App Secret 归属公司级妙手账号，密钥加密后存储；店铺是通过该账号 API 同步的资源，上架也使用公司级妙手账号调用 API。

## 部署方式

本机固定使用隔离测试环境，腾讯云固定使用服务器环境。各环境分别维护配置和数据卷。
所有 Compose 操作都通过仓库内的固定入口执行，避免遗漏参数创建重复环境：

| 环境 | 固定入口 | 环境文件 | 项目名 | Compose 配置 |
| --- | --- | --- | --- | --- |
| 本机测试 | `./deploy/local.sh` | `.env.local` | `haitoo-test` | `docker-compose.yml` + `docker-compose.local.yml` |
| 腾讯云 | `./deploy/tencent.sh` | `.env` | `haitorok` | `docker-compose.yml` + `docker-compose.tencent.yml` |

例如，本机执行 `./deploy/local.sh ps`，服务器执行 `./deploy/tencent.sh ps`。
脚本自动定位项目根目录，缺少文件时停止，并拒绝覆盖环境文件、项目名、配置文件及 profile。
脚本也会清除外部设置的 `COMPOSE_FILE`、`COMPOSE_PROJECT_NAME`、`COMPOSE_PROFILES`、
`COMPOSE_ENV_FILES`。后续通用运维示例采用本机入口；服务器执行时将入口替换为
`./deploy/tencent.sh`，其余参数相同。不要直接使用省略环境参数的 Compose 命令。

### 基础镜像源切换

如果构建在 `FROM python:3.12-slim` 处出现 `auth.docker.io` 连接超时，这是基础镜像仓库的网络问题，修改 pip 源不能解决。Python、Node、Nginx 和 MySQL 统一支持 `DOCKER_REGISTRY` 配置，默认值为 `docker.io`。仓库前缀不包含 `https://` 或结尾斜杠，需要提供对应的 `library` 镜像路径。

腾讯云 CVM 服务器可尝试腾讯云镜像源（是否可用以服务器网络和镜像源服务状态为准）：

```bash
DOCKER_REGISTRY=mirror.ccs.tencentyun.com ./deploy/tencent.sh build
```

本机使用 DaoCloud 国内镜像源（是否可用以镜像源服务状态为准）：

```bash
DOCKER_REGISTRY=docker.m.daocloud.io ./deploy/local.sh build
```

要持续使用替代源，在对应环境文件中设置 `DOCKER_REGISTRY`：腾讯云编辑已有 `.env`，本机编辑已有 `.env.local`，保留其他配置。只在单次命令前设置变量时，仅该命令使用替代源；后续拉取 MySQL 或腾讯云入口 Nginx 时也需要相同变量。上述构建命令不会重启服务。Cloudflare Tunnel 仍使用原有镜像地址。

### 只修改前端时

本机日常调试优先使用 Vite 热更新，保存 Vue、CSS 等文件后即可更新页面，不需要每次构建 Docker 镜像。已有 `node_modules` 且依赖未变化时，直接运行下面命令；只有首次安装或 `package-lock.json` 变化时才在对应前端目录执行 `npm ci`。

本机运营端（后端继续使用已启动的本机测试容器）：

```bash
./deploy/local.sh stop web
VITE_API_URL=http://localhost:8001 npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

本机管理端：

```bash
./deploy/local.sh stop admin-web
VITE_API_URL=http://localhost:8001 npm --prefix frontend-admin run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

使用 `http://localhost:5173`、`http://localhost:5174` 访问，与本机默认 CORS 配置保持一致。调试结束按 `Ctrl+C` 关闭 Vite，恢复本次停止的容器，例如运营端执行 `./deploy/local.sh start web`；管理端执行 `./deploy/local.sh start admin-web`。恢复的是原镜像，保留最新修改需按下述方式构建。

需要验证容器部署时，本机只更新运营端：

```bash
./deploy/local.sh build --pull=false web
./deploy/local.sh up -d --no-deps --no-build --pull never web
```

腾讯云服务器只更新运营端：

```bash
./deploy/tencent.sh build --pull=false web
./deploy/tencent.sh up -d --no-deps --no-build --pull never web
```

管理端将 `web` 替换为 `admin-web`。上述命令适用于依赖服务已运行、仅修改前端的情况；后端或迁移也有改动时，仍需更新对应服务。

两个前端 Dockerfile 已将 `package*.json` 和 `npm ci` 放在源码复制之前，依赖文件未变且缓存保留时可复用依赖层。不要在日常构建时使用 `--no-cache` 或清理构建缓存。日志中的 `load metadata` / `Head ... manifests` 是基础镜像元数据检查，不代表每次都完整下载 Node；即使使用 `--pull=false`，基础镜像缺失或缓存不足时仍可能联网，因此 Docker Hub 返回 EOF 时，本机调试可先使用上面的 Vite 流程。

### 本机隔离测试环境

本机测试使用独立的 `.env.local`、Compose 项目名和 MySQL 数据卷，不修改腾讯云服务器配置，也不要连接生产数据库。下面初始化命令仅供首次建立环境；已有 `.env.local` 时保留原文件和密钥，直接使用固定入口升级。首次建立时复制配置模板并生成随机密钥：

```bash
cp deploy/env/local.env.example .env.local
credential_key=$(openssl rand -hex 32)
sed -i '' "s/^MYSQL_ROOT_PASSWORD=$/MYSQL_ROOT_PASSWORD=$(openssl rand -hex 32)/" .env.local
sed -i '' "s/^MYSQL_PASSWORD=$/MYSQL_PASSWORD=$(openssl rand -hex 32)/" .env.local
sed -i '' "s/^SECRET_KEY=$/SECRET_KEY=$credential_key/" .env.local
sed -i '' "s/^CREDENTIAL_ENCRYPTION_KEY=$/CREDENTIAL_ENCRYPTION_KEY=$credential_key/" .env.local
chmod 600 .env.local
```

上面的 `sed -i ''` 适用于 macOS。启动和检查：

```bash
./deploy/local.sh up -d --build
./deploy/local.sh ps
```

运营端为 `http://localhost:5173`，管理端为 `http://localhost:5174`，API 文档为 `http://localhost:8001/docs`。首次启动空库后创建本机超级管理员：

```bash
./deploy/local.sh exec api python -m app.admin_cli create-super-admin \
  --email test-admin@example.com --name "本机管理员"
```

本地端口只绑定 `127.0.0.1`。不要加腾讯云的 `docker-compose.tencent.yml`，也不要启用 `cloudflare` profile。`VITE_API_URL` 是前端构建参数，修改后要重新执行 `up -d --build`。若需要测试图片上传，请在 `.env.local` 中填写**独立测试 R2 Bucket** 的配置，并为本地运营端域名设置 PUT CORS；留空时上传功能不可用。真实 AI、妙手、HubStudio 操作会调用外部服务，应使用测试账号和测试数据。若要导入线上数据，应先脱敏，并清除第三方凭据与待执行任务。

停止本机环境时使用相同的参数执行 `./deploy/local.sh down`；不要加 `-v`，否则会删除测试 MySQL 数据卷。

本机 Clash / Mihomo 等代理可能将公网图片域名解析成 `198.18.0.0/15` 或
`2001:2::/48` 网段的 Fake-IP。`docker-compose.local.yml` 仅为 API 和结果 Worker
开启 `IMAGE_DOWNLOAD_ALLOW_FAKE_IP`，允许通过这些域名下载图片，仍校验连接 IP
一致性、重定向和图片大小，并拒绝直接填写的保留 IP 及其他内网地址。
此模式信任本机代理的域名映射；应用默认关闭兼容开关，腾讯云配置不启用它。
直接使用虚拟环境运行本机后端时，可按需设置 `IMAGE_DOWNLOAD_ALLOW_FAKE_IP=true`。

两个密码必须是至少 32 个字符的十六进制随机字符串。MySQL 只监听 Compose
内部网络的 `3306` 端口，不映射到宿主机；API 和 Worker 使用应用密码连接数据库。
已有部署升级时，将 `CREDENTIAL_ENCRYPTION_KEY` 设置为当前 `SECRET_KEY` 的值，
确保数据库中已有的第三方凭据仍能解密。未配置新变量时，程序暂时沿用 `SECRET_KEY`；
以后更换登录用 `SECRET_KEY` 时，需保留原加密密钥。

Compose 会以生产方式构建容器：API 使用两个 Uvicorn worker，两个 Vue 前端先由
Vite 生成静态文件，再由 Nginx 提供服务。`VITE_API_URL` 是前端构建参数，修改后
必须重新执行 `./deploy/local.sh up -d --build`，仅重启容器不会更新浏览器产物。
所有容器使用 Docker `json-file` 日志驱动，每个日志文件最多 10MB，并保留最近
5 个文件，避免长期运行产生的容器日志占满服务器磁盘。

产品库订单导入支持最大 30MB 的 XLSX 文件，压缩包内解压后内容合计不超过 150MB，
单次最多 20,000 条有效数据行。腾讯云 API 入口允许 31MB 请求体，为上传表单留出余量，
代理读取超时为 300 秒。修改限制后需要重新构建 API 并重建入口 Nginx 容器以生效。

产品库点击“数据统计”后会立即创建后台任务，由 `product-library-rankings-worker`
计算截至昨天的 7、15、30 天销量榜单与近 7 天销量档位。同一公司已有任务排队或运行时
复用该任务。任务提交时固定香港本地统计日期；成功后替换当期快照，失败时保留旧快照。
Worker 重启后会恢复中断任务，并定期清理超过最近 30 个统计日的快照；不会自动生成榜单。
首次部署此功能需执行
`./deploy/local.sh up -d --build`，以创建新的 Worker 服务。

### 下线妙手公共采集箱数据同步

`20261011_33` 删除公共采集箱同步缓存表和公司同步、清理时间字段；升级时会清除全部同步缓存。妙手管理仅保留管理员的 API Key 配置、店铺同步和人员分配，商品草稿发布至妙手、认领及分配店铺继续使用原有数据。回滚迁移只恢复空缓存表，无法恢复已删除的缓存。

升级时使用 `--remove-orphans` 删除已下线的采集箱同步 Worker，避免旧容器继续调用妙手。启动入口会先执行数据库迁移，再启动 API 和其余 Worker。

本机隔离测试环境：

```bash
./deploy/local.sh up -d --build --remove-orphans
```

腾讯云生产环境：

```bash
./deploy/tencent.sh up -d --build --remove-orphans
```

### 产品库销量统计升级（20261005_25）

本次迁移会一次性删除**所有公司**的产品库店铺（含负责人分配）、产品、订单及订单明细、
快照和统计任务。素材、产品模板、商品草稿及其他业务店铺保留。执行前完成数据库备份，
并停止 API 和产品库统计 Worker，防止旧程序在迁移期间写入数据。
本机测试环境统一通过 `./deploy/local.sh` 执行以下升级步骤；每一步成功后才执行下一步：

```bash
./deploy/local.sh build migrate api product-library-rankings-worker web &&
./deploy/local.sh stop api product-library-rankings-worker &&
./deploy/local.sh run --rm migrate &&
./deploy/local.sh up -d api product-library-rankings-worker web
```

腾讯云在已同步最新代码的项目目录执行：

```bash
./deploy/tencent.sh build migrate api product-library-rankings-worker web &&
./deploy/tencent.sh stop api product-library-rankings-worker &&
./deploy/tencent.sh run --rm migrate &&
./deploy/tencent.sh up -d api product-library-rankings-worker web edge &&
./deploy/tencent.sh exec edge nginx -t &&
./deploy/tencent.sh exec edge nginx -s reload
```

升级后重新下载产品库导入模板，填写必需的「数量」列，再导入历史订单、分配店铺负责人，
点击「数据统计」生成新榜单。数量填写每行完整平台 SKU（含尺码）的销售件数；同订单
不同尺码相加，重导仅覆盖文件内尺码的数量，未出现的尺码保留，重复导入不累加。
排行榜和榜单按公司、基础 SKU 汇总；订单数去重，销量累计，按销量降序排序。
店铺多选仅汇总当前账号可见且选中的店铺，未选择表示全部可见店铺；榜单详情使用
相同店铺范围及对应快照。数据库降级不会恢复已删除的数据。

Compose 会先运行一次 `migrate` 服务，将数据库升级到代码要求的 Alembic 版本；成功后才启动 API。API 和 Worker 自身只检查版本，不会在启动时建表或执行 DDL。生产部署应在迁移前完成数据库备份，也可显式执行并检查迁移结果：

```bash
./deploy/local.sh run --rm migrate
./deploy/local.sh run --rm api alembic current
```

### 代码更新后的数据库迁移

升级到图片去重版本 `20261017_40` 时，需要额外处理历史图片。几万张图片应先在旧系统在线期间预缓存，再停写、备份、迁移并并发回填；不能直接套用普通重启流程。具体命令及中断恢复方式见[图片回填与两阶段部署](docs/image-file-dedup.md#部署与历史整理)。

当 API 日志提示“数据库版本不匹配”时，表示代码已更新而 MySQL 还没执行对应迁移。按以下顺序处理：

```bash
# 1. 在项目根目录执行版本化迁移（会升级 MySQL 表结构）
./deploy/local.sh run --rm migrate

# 2. 确认当前数据库已到代码要求的 head 版本
./deploy/local.sh run --rm api alembic current

# 3. 重启 API 与两个后台 Worker，使它们加载新代码与新表结构
./deploy/local.sh restart api submit-worker result-worker

# 4. 查看 API 启动结果；应出现“应用初始化完成”
./deploy/local.sh logs --tail=50 api
```

如果 compose 服务尚未启动，可改用 `./deploy/local.sh up -d --build`；它会先执行 `migrate`。正常版本升级只运行 `./deploy/local.sh run --rm migrate`，**不要**附加 `--adopt-legacy`。

全新数据库直接执行普通迁移，首次启动 `./deploy/local.sh up -d --build` 时也会自动执行同一流程：

```bash
./deploy/local.sh run --rm migrate
```

只有从旧版启动期自动建表流程升级，且数据库已有业务表但没有 `alembic_version` 时，迁移服务才会要求显式接管。确认数据库备份可恢复后执行一次：

```bash
./deploy/local.sh run --rm migrate python -m app.db_migrate --adopt-legacy
```

成功后再正常执行 `./deploy/local.sh up -d`。不要对全新数据库或已纳入 Alembic 的数据库使用 `--adopt-legacy`。

以后每次修改 ORM 表结构，都必须创建新的版本文件，禁止继续修改已有基线迁移：

```bash
./deploy/local.sh run --rm api alembic revision --autogenerate -m "变更说明"
```

API 文档地址为当前环境的 API 域名加 `/docs`。

## HubStudio 环境自动上品

HubStudio 环境可包含本土店和跨境店，当前自动上品只支持用户确认的 TikTok 本土店。环境与妙手同步店铺分开管理，不再新增本土店、分配人员、手工填写环境 ID 或绑定电脑。“HubStudio管理”向全公司开放，展示自动上品任务 ID、商品数量、创建人、创建时间、执行环境和状态。管理员默认查看全公司记录并可按成员筛选，成员及组长仅查看自己的记录；公司 App ID、App Secret、Group Code 配置仅管理员可见可修改。记录默认每页 25 条，可选择每页 50、100、500 或 1000 条，进入页面加载，也可手动刷新。

员工启动新版执行器，在本机工作页 `http://127.0.0.1:45679` 输入 ERP 邮箱和密码授权。环境每 60 秒从当前 HubStudio 客户端完整同步，仅保存在本机内存，不上传到 ERP、不写数据库；本机配置只保存唯一自动上品环境的 ID。超过 5 分钟的本机快照禁止领取任务，重新同步成功后恢复。环境列表按分组折叠，展示序号及其下方 ID、环境名称、分组、标签和自动上品开关。

本机只能启用一个确认属于 TikTok 本土店的环境，启用新环境会自动关闭原环境，任务执行中不能切换。ERP 草稿页直接生成账号任务及固定 XLSX，无需选择目标环境，也无需等待环境同步。执行器领取任务时使用本机已启用的环境；未启用或当前无法访问时，任务留在队列中。

数据库只保存任务、执行尝试、实际执行目标及运行锁，不再保存新的环境目录或访问关系。同环境全公司串行运行、多电脑原子领取。独立心跳每 15 秒续租，90 秒失联后转人工处理，不自动重新提交。重试复用原 XLSX，使用领取电脑当前启用的环境，保留之前每次执行的目标和日志；请先核对原环境的平台结果。只有平台明确接受或人工确认后才标记草稿已发布，“已提交”不代表已上架。

本功能要求数据库版本 `20261007_30`，并同时更新 ERP 前端和协议 3 的本地执行器。升级保留历史店铺、环境表、任务和 XLSX；历史环境表不再被同步写入。旧排队及运行任务转为待人工核对，旧领取凭证失效，原执行环境继续阻止新任务，直到人工处理。旧执行器收到 HTTP 426 升级提示后无法继续领取或报告。

本机测试升级：

```bash
./deploy/local.sh run --rm migrate
./deploy/local.sh up -d --build api web submit-worker result-worker
```

腾讯云升级：

```bash
./deploy/tencent.sh run --rm migrate
./deploy/tencent.sh up -d --build api web submit-worker result-worker
```

执行器构建、员工安装和测试说明见 [hub_agent/README.md](hub_agent/README.md)。

系统启动时不会创建公司、演示账号或默认超级管理员。首次部署后，通过容器内的一次性命令创建平台超级管理员；密码将在终端中安全输入两次，不会进入命令历史或环境变量：

```bash
./deploy/local.sh exec api python -m app.admin_cli create-super-admin \
  --email owner@example.com \
  --name "平台管理员"
```

超级管理员后台是独立前端项目，启动后访问当前环境的管理端域名。登录后可开通公司及其首位公司管理员，公司管理员再从运营端创建普通成员和运营组、任命运营组长。组长沿用普通运营的业务权限；删除运营组会将该组所有人恢复为未分组普通运营。

平台超级管理员的其他运维命令：

```bash
# 查看全部平台超级管理员
./deploy/local.sh exec api python -m app.admin_cli list-super-admins

# 重置密码；成功后该账号原有登录令牌立即失效
./deploy/local.sh exec api python -m app.admin_cli reset-super-admin-password \
  --email owner@example.com

# 启用或停用；系统禁止停用最后一个有效的超级管理员
./deploy/local.sh exec api python -m app.admin_cli disable-super-admin \
  --email owner@example.com
./deploy/local.sh exec api python -m app.admin_cli enable-super-admin \
  --email owner@example.com
```

超级管理员密码至少 12 个字符，并且必须包含字母、数字和特殊字符。已有数据库升级时，应用不会自动删除历史演示账号或公司；应先创建并验证正式超级管理员，再人工停用历史演示账号，确认其没有业务数据后另行清理。

## 图片任务数量与采用率

`backend/scripts/image_task_statistics.py` 只读统计 SKU 图（`sku_image`）、轮播图（`carousel`）、首图（`main_image`），输出三类汇总及按创建人的明细。统一以 `selected_result_url` 非空（非 NULL 且长度大于 0）判断采用，采用率为 **采用任务数 ÷ 全部任务数**；失败、排队、生成中及未审核任务均计入分母，不关联素材库或商品发布情况。一个任务采用多张图片或重复重试仍只计一次。结果反映运行时保存的采用字段，不能还原历史采用情况；零任务显示 `0.00%`。

默认查询全部公司、全部历史；可使用 `--company-id`、`--creator-id` 筛选公司和任务创建人，`--start-date`、`--end-date` 按任务创建日期筛选。日期格式为 `YYYY-MM-DD`，采用香港时区，包含起止日期全天。明细带公司和人员 ID，同名人员分别统计；已删除的公司或人员信息不影响任务计数。

腾讯云环境（`haitorok`，脚本随 API 镜像部署后，在服务器项目目录执行）：

```bash
./deploy/tencent.sh exec -T api python scripts/image_task_statistics.py

# 按公司、创建日期筛选；结束日期包含当天全天
./deploy/tencent.sh exec -T api python scripts/image_task_statistics.py \
  --company-id 3 \
  --start-date 2026-10-01 --end-date 2026-10-11

# 导出 UTF-8 CSV，包含汇总及人员明细；文件保存在当前服务器目录
./deploy/tencent.sh exec -T api python scripts/image_task_statistics.py \
  --company-id 3 \
  --start-date 2026-10-01 --end-date 2026-10-11 \
  --format csv > image-task-statistics.csv
```

本机测试环境（`haitoo-test`）：

```bash
./deploy/local.sh exec -T api python scripts/image_task_statistics.py
```

默认输出中文终端表格，`--format csv` 输出相同统计结果的 CSV。公司和人员筛选可组合使用，不存在或无匹配数据的筛选条件输出三类零值汇总。脚本复用 API 的数据库配置，不修改业务数据或创建数据库表。

## 每张白底图大小与创作人

独立只读脚本 `backend/scripts/white_image_statistics.py` 查询数据库中当前登记的白底图，每条输出白底图 ID／名称、公司 ID／名称、创作人 ID／姓名、模板 ID／名称、图片大小、读取状态和图片链接。这里“创作人”指白底图记录的所属人员（`user_id`），数据库没有记录实际上传操作人，管理员代上传时仍显示所属人员。

脚本按公司分页读取 `template-white/company/{公司 ID}/` 的 R2 对象列表（每页最多 1000 个），用对象 key 匹配记录，不逐张调用 `HeadObject` 或下载图片。同一个对象被多条白底图记录引用时，每条记录均展示大小；某公司所需对象全部找到后停止该公司的扫描。只报告数据库已登记白底图，未登记或已删除记录的 R2 文件不在报告中。

大小仅显示 KiB／MiB／GiB／TiB，保留两位小数，不输出原始字节数。R2 对象缺失、链接不属于当前 R2、目录或公司不匹配的记录保留，大小显示 `—` 并标注状态；历史公司、人员或模板信息缺失时保留 ID。需要配置 `R2_PUBLIC_BASE_URL` 来解析图片链接，以及 R2 对象列表读取权限。扫描请求失败时返回非零退出码，不输出部分报告。

默认全部公司，支持 `--company-id`、`--creator-id`、`--template-id` 筛选，按公司、创作人、模板、白底图 ID 排序。开始、每页读取完成及统计完成时将进度打印到 stderr，不混入 CSV；`--no-progress` 可关闭进度。

腾讯云环境（`haitorok`，新版 API 镜像部署后，在服务器项目目录执行）：

```bash
sudo ./deploy/tencent.sh exec -T api python scripts/white_image_statistics.py

# 筛选指定公司和所属创作人
sudo ./deploy/tencent.sh exec -T api python scripts/white_image_statistics.py \
  --company-id 3 --creator-id 12

# 导出每张白底图明细，进度仍显示在终端
sudo ./deploy/tencent.sh exec -T api python scripts/white_image_statistics.py \
  --format csv > white-image-statistics.csv
```

本机测试环境（`haitoo-test`）：

```bash
./deploy/local.sh exec -T api python scripts/white_image_statistics.py
```

## 按白底图统计 SKU 生成图平均大小

独立只读脚本 `backend/scripts/white_image_generation_statistics.py` 仅统计 SKU 图任务，不包含轮播图或首图。每个白底图历史版本一行，包含公司、白底图 ID／名称、所属创作人 ID／姓名及信息来源、模板、白底图链接及大小／读取状态、关联生成图总数、取样数量、成功／无法读取数量、生成图平均大小及读取状态。

来源使用任务保存的 `white_image_id`、`white_image_name`、`white_image_url`，按公司、白底图 ID、历史链接分组；同一 ID 后来替换图片时分开统计，包含当前无生成结果的白底图和可关联的已删除白底图。任务只有历史链接、没有 ID 时仍保留来源链接；缺少历史链接的任务不会用当前图片猜测来源，会向 stderr 提醒未关联任务数量。创作人优先使用白底图记录的所属人员；记录已删除时使用该版本最新来源 SKU 任务的创作人，并标明信息来源。白底图名称优先使用该版本最新任务保存的名称，无任务时使用当前名称。

所有候选结果均参与关联，不按采用状态过滤。同一白底图版本内按生成图链接去重，计算关联总数。按任务完成时间倒序（没有完成时间时使用创建时间）、任务 ID 倒序、任务内结果顺序，最多取最近 **2000 张**作为固定样本。平均大小只用样本中成功读取的大小合计除以成功读取数量；文件缺失、非当前 R2 链接、目录或公司不匹配的样本不按零计算，也不从更老结果中补取。真实零大小文件参与计算；无成功样本时显示 `—`。

白底图按公司目录、生成图按 `generated/` 批量分页读取 R2 对象列表，不下载图片、不逐张调用 `HeadObject`。只缓存目标文件大小，全部找到后停止对应目录扫描；相同对象在不同白底图版本间复用大小。**2000 限制计算样本，不限制列表返回的对象数量**，缺失目标可能导致扫描整个目录。大小仅显示 KiB／MiB／GiB／TiB，保留两位小数，不输出逐张生成图明细或最大／最小大小。统计基于现存任务结果和 R2 文件，不能恢复已清除的历史结果。

默认全部公司，可使用 `--company-id`、`--creator-id`、`--template-id`、`--white-image-id` 筛选；创作人筛选指白底图所属人员，白底图 ID 筛选包含该 ID 的各历史版本。进度写入 stderr，不混入 CSV；`--no-progress` 关闭进度，但缺少来源的任务提醒仍保留。数据库连接在 R2 扫描前关闭；数据库或 R2 请求失败返回非零退出码，不输出部分报告。

腾讯云环境（`haitorok`，新版 API 镜像部署后，在服务器项目目录执行）：

```bash
sudo ./deploy/tencent.sh exec -T api python scripts/white_image_generation_statistics.py

# 只统计指定公司的指定白底图（含历史版本）
sudo ./deploy/tencent.sh exec -T api python scripts/white_image_generation_statistics.py \
  --company-id 3 --white-image-id 12

# 导出汇总，进度仍显示在终端
sudo ./deploy/tencent.sh exec -T api python scripts/white_image_generation_statistics.py \
  --format csv > white-image-generation-statistics.csv
```

本机测试环境（`haitoo-test`）：

```bash
./deploy/local.sh exec -T api python scripts/white_image_generation_statistics.py
```

## R2 图片文件大小统计

独立脚本 `backend/scripts/r2_image_statistics.py` 使用已有 R2 配置，按对象 key 前缀分页调用 `ListObjectsV2`，每页最多返回 1000 个对象及其大小，直接累加列表里的 `Size`，不逐张调用 `HeadObject` 或 `GetObject`，不下载图片、不查询数据库、不修改或删除 R2 对象。对象列表接口不提供文件夹数量和总大小的汇总值，因此需要读取目标前缀的所有列表页。凭据需要具备目标桶的对象列表读取权限。

默认统计 `R2_BUCKET` 图片桶的全部现存对象，分别输出全部对象、图片合计、非图片对象，以及按图片 key 第一段目录（如 `generated/`、`material/`）的图片统计。每行包含文件数量、总大小、平均大小。终端与 CSV 中所有大小只显示 KiB／MiB／GiB／TiB，按 1024 自动换算并保留两位小数；不足 1 KiB（包括零值）仍使用 KiB，超过 TiB 范围仍以 TiB 展示，不输出原始字节大小列。可用 `--prefix` 限定对象 key 前缀，前缀直接传给 R2，不会自动添加斜杠。

默认在开始扫描、每页读取完成和扫描完成时向 stderr 打印进度，包含已读取页数、已扫描对象数、累计大小、图片数量和大小以及耗时，并立即刷新输出。对象总数事先未知，不展示百分比。CSV 重定向到文件时进度仍显示在终端，不混入 CSV；可用 `--no-progress` 关闭进度。失败时保留已经打印的扫描进度和错误信息，不打印“扫描完成”或最终汇总。

图片按不区分大小写的扩展名识别：JPG、JPEG、PNG、WebP、GIF、AVIF、BMP、TIF、TIFF、SVG；无扩展名或其他扩展名的对象计入非图片。数据反映扫描期间的现存对象，不代表累计上传量；扫描时若仍有上传或删除，结果可能随之变化。中途读取失败时返回非零退出码，不输出部分汇总。

腾讯云环境（`haitorok`，脚本随新版 API 镜像部署后，在服务器项目目录执行；容器内路径不带 `backend/`）：

```bash
sudo ./deploy/tencent.sh exec -T api python scripts/r2_image_statistics.py

# 只统计 AI 生成图片目录
sudo ./deploy/tencent.sh exec -T api python scripts/r2_image_statistics.py --prefix generated/

# 导出 UTF-8 CSV，保存在当前服务器目录
sudo ./deploy/tencent.sh exec -T api python scripts/r2_image_statistics.py \
  --format csv > r2-image-statistics.csv
```

本机测试环境（`haitoo-test`，使用该环境配置的 R2 图片桶）：

```bash
./deploy/local.sh exec -T api python scripts/r2_image_statistics.py
```

## 清理产品库数据

`backend/scripts/clear_product_library.py` 无需参数，运行即清空所有公司的产品库相关 9 张表（产品、来源店铺、订单及关联、SKU 数量、快照及明细、统计任务），同一事务提交，失败回滚。保留其他业务表、表结构与自增序列。清理期间暂停 API 和产品库统计 worker，避免并发写入。

本机测试环境（`haitoo-test`）：

```bash
./deploy/local.sh build api
./deploy/local.sh stop api product-library-rankings-worker
./deploy/local.sh run --rm --no-deps api python scripts/clear_product_library.py
./deploy/local.sh start api product-library-rankings-worker
```

腾讯云环境（`haitorok`，在服务器项目目录执行）：

```bash
./deploy/tencent.sh build api
./deploy/tencent.sh stop api product-library-rankings-worker
./deploy/tencent.sh run --rm --no-deps api python scripts/clear_product_library.py
./deploy/tencent.sh start api product-library-rankings-worker
```

## 历史 Cloudflare Tunnel 配置

仓库保留 Cloudflare Tunnel 的历史配置。当前本机只使用 `haitoo-test` 隔离测试环境，
服务器只使用 `haitorok` 腾讯云环境，不在这两套环境启用 `cloudflare` profile。
Cloudflare R2 图片存储可继续使用，与 Tunnel 无关。

## 通过腾讯域名部署到腾讯云

腾讯云使用额外的 `docker-compose.tencent.yml` 启动边缘 Nginx。应用容器继续只在
Docker 内部网络开放端口，只有边缘 Nginx 映射宿主机的 80 和 443。

1. 首次部署时创建腾讯云环境配置并填写实际域名、随机密钥和 R2 配置；已有部署保留原 `.env` 和密钥，不重复初始化：

   ```bash
   cp deploy/env/tencent.env.example .env
   credential_key=$(openssl rand -hex 32)
   printf 'MYSQL_ROOT_PASSWORD=%s\nMYSQL_PASSWORD=%s\nSECRET_KEY=%s\nCREDENTIAL_ENCRYPTION_KEY=%s\n' \
     "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" \
     "$credential_key" "$credential_key" >> .env
   chmod 600 .env
   ```

2. 在腾讯 DNS 为 `.env` 中的 `ERP_DOMAIN`、`ADMIN_DOMAIN`、`API_DOMAIN` 创建 A
   记录，全部指向服务器公网 IP。

3. 从腾讯云 SSL 下载包含这三个域名的 SAN 或通配符证书，在服务器保存为：

   ```text
   /opt/haitoo/certs/fullchain.pem
   /opt/haitoo/certs/private.key
   ```

   私钥权限应设为 `600`。如使用其他目录，在 `.env` 中修改 `TLS_CERT_DIR`。

4. 启动腾讯云部署：

   ```bash
   ./deploy/tencent.sh up -d --build
   ```

   如果重建 `web`、`admin-web` 或 `api` 后入口返回 502，先查看入口日志，
   再重新加载入口，让现有配置重新解析容器地址以恢复当前访问：

   ```bash
   ./deploy/tencent.sh logs --tail=80 edge
   ./deploy/tencent.sh exec edge nginx -t
   ./deploy/tencent.sh exec edge nginx -s reload
   ```

   新版入口配置通过 Docker DNS 动态解析上游容器。模板只在容器创建时生成
   Nginx 配置，首次部署此配置时需重建 `edge`：

   ```bash
   ./deploy/tencent.sh up -d --no-deps --force-recreate edge
   ```

5. 腾讯云安全组只开放 80、443，以及仅限管理员固定 IP 的 22。不要开放 3306、
   5173、5174 或 8001。如果服务器位于中国大陆，公开访问前还需要完成 ICP 备案。

`VITE_API_URL` 会在前端构建阶段写入产物，因此两套环境切换 API 域名后都必须带
`--build` 重建前端。Cloudflare R2 与 Tunnel 相互独立；腾讯云入口仍可继续使用 R2。

## 印花贴合模型配置

超级管理员登录后可在“AI 模型管理”中启用并切换印花贴合模型，并为每个平台模型设置“单个任务印花图数量”。批量快捷操作会按该数量创建多条独立任务；只有服务商保证输出顺序与输入一致时才能把数量设为大于 1，否则必须保持默认值 1。

默认生产模型为 Grsai 的 `nano-banana-fast`，可在后台启用并选择同平台的 `gpt-image-2`。两个模型共用同一份 Grsai API Key。MySQL 中的任务记录就是队列状态源，`submit-worker` 按创建时间串行提交第三方 API，`result-worker` 独立持续查询异步结果，默认最多并发处理 5 项（包括查询、图片转存和落库），空位立即补入下一项。提交失败最多再重试 2 次，查询未完成或临时失败时重新排到队尾。启动生产服务时需要同时运行 `api`、两个 Worker 和 MySQL；任务提交间隔、全局查询启动间隔和结果并发数（1～20）可由超级管理员在线配置，结果配置通常在 1 秒内生效；原有毫秒间隔在升级中保留。每个新任务会记录实际使用的提供方、模型版本和创建人。模型平台密钥由公司管理员在“成员管理”中为每位员工单独配置，经加密保存后仅由后端按任务创建人读取，不再使用平台级共享模型密钥。

结果查询在单个 `result-worker` 内并发，复用 HTTP 连接；不要扩容此服务的容器数量，本期没有多实例领取锁。查询启动间隔限制所有查询的相邻启动时间，不代表每条任务固定多久重查一次。HTTP 429 按员工的平台凭据冷却，两个 Grsai 模型共享该凭据的冷却状态；有效 `Retry-After` 限制为 1～300 秒，缺失时 5 秒，其他员工可继续查询。

日志每 60 秒输出“结果查询统计”：请求数、结果计数、吞吐量、队列与执行中数量，以及 `queue_wait_ms`（入队至请求启动）、`query_ms`（第三方响应）、`persist_ms`（图片转存）、`processing_ms`（槽位占用）、`poll_gap_ms`（同任务两次查询启动间隔）的平均值和 P95。P95 取窗口内最近最多 10,000 个样本，总次数和平均值完整累计；首次查询没有重查间隔，未转存时不计转存样本。普通 pending 明细为 DEBUG，超过 10 秒的查询会告警。正在执行的查询可能跨越统计窗口，因此窗口请求数和完成结果数不要求相等。统计只能反映本系统处理速度，不能精确推算第三方生成完成时间。

本次版本要求数据库迁移 `20261025_44`。部署时先备份数据库，构建相关服务，停止后端进程后迁移，再更新服务；所有携带数据库版本检查的后端镜像均需包含新迁移文件。以下流程仅适用于已在正常使用版本化迁移和图片文件索引的环境；较早版本仍按前述历史图片升级流程处理。

本机测试环境：

```bash
./deploy/local.sh build migrate api submit-worker result-worker product-library-rankings-worker supply-worker admin-web
./deploy/local.sh stop api submit-worker result-worker product-library-rankings-worker supply-worker
./deploy/local.sh run --rm migrate
./deploy/local.sh up -d api submit-worker result-worker product-library-rankings-worker supply-worker admin-web
./deploy/local.sh logs --since=10m result-worker
```

腾讯云环境（在服务器项目目录执行）：

```bash
sudo ./deploy/tencent.sh build migrate api submit-worker result-worker product-library-rankings-worker supply-worker admin-web
sudo ./deploy/tencent.sh stop api submit-worker result-worker product-library-rankings-worker supply-worker
sudo ./deploy/tencent.sh run --rm migrate
sudo ./deploy/tencent.sh up -d api submit-worker result-worker product-library-rankings-worker supply-worker admin-web
sudo ./deploy/tencent.sh logs --since=10m result-worker
```

迁移失败时停止流程，修复后再启动；不要直接执行后续启动命令。发布后观察至少 10 分钟，重点检查 429、查询 P95、轮询间隔、转存耗时和数据库连接异常。需要降低负载时，在后台把并发降为 1，必要时增大查询启动间隔，无需降级数据库；本期不自动调整并发，也不单独拆分转存队列。


模型服务地址、标题生成服务及 R2 存储仍由部署环境配置：

```bash
# 可选，默认 https://grsaiapi.com；国内节点可使用 https://grsai.dakka.com.cn
export GRSAI_BASE_URL='https://grsaiapi.com'
export DEEPSEEK_API_KEY='...'
export R2_ACCOUNT_ID='...'
export R2_ACCESS_KEY_ID='...'
export R2_SECRET_ACCESS_KEY='...'
export R2_BUCKET='haitoro-images-prod'
export R2_ENDPOINT='https://<account-id>.r2.cloudflarestorage.com'
export R2_PUBLIC_BASE_URL='https://img.haitoro.com'
# 是否复制模型生成结果到 R2；默认 true，建议生产环境保持 true。
export AI_GENERATED_IMAGE_UPLOAD_TO_R2='true'
```

## 商品草稿图片制作

任务中心按 `SKU图`、`轮播图`、`首图` 三个子 Tab 展示任务。内部稳定值分别为 `sku_image`、`carousel`、`main_image`；历史任务和缺少类型的任务会迁移为 `sku_image`。每个 Tab 独立保留状态、创作人、日期和分页条件，当前条件同步到 URL。三类任务中的失败项均可多选后批量重试。

SKU 图任务支持批量审核：弹窗默认选中全部结果图，可全选或取消选择；确认后只将采用的图片加入素材库，全部不采用的任务也会完成。未采用图片仍保留在任务中，已有素材不受影响；部分失败时只重试失败任务。

新创建的商品草稿默认进入“待处理”。在待处理 Tab 选择一条或多条草稿后，可统一分发到“待制作轮播图”“待制作主图”或“待发布”；分发到图片制作阶段后，可进入对应工作台：

- 选择最多 9 个 SKU，每个 SKU 创建一条独立轮播图任务；每个 SKU 最多采用一张结果。
- SKU 图是商品规格的原始图片；没有自定义轮播图时，系统自动以 SKU 图顺序作为轮播图，并把第 1 张作为首图。
- 轮播图与首图的采用、拖拽排序和移除先在弹窗本地暂存，点击最终确认后一次写入草稿。
- 轮播图生成可跳过；首图可从已采用轮播图或原始 SKU 图随机参考最多 3 张，也可从两类图片中手动混选 1–9 张。随机轮播图模式遇到空轮播图时自动改用 SKU 图；单条和批量入口采用相同规则。
- 首图就是最终轮播列表第 1 张。重新生成的首图会放在第 1 位，商品最终仍最多 9 张。
- 相关任务由用户手动刷新，刷新只更新任务列表，不覆盖当前弹窗暂存的图片编排。
- 最终预览确认后才更新草稿正式发布图片；未进入新版流程的历史草稿继续沿用原图片。
- 已发布到妙手或 TikTok 的草稿仍可继续编辑、生成并重新编排本地图片；保存不会自动同步已发布的外部商品。

发布和 TikTok 表格导出均使用同一套正式轮播顺序，第 1 张即首图；SKU 规格关联始终继续使用原 SKU 图，不会被轮播图覆盖。部署本版本前需运行数据库迁移：

```bash
python -m app.db_migrate
```

用户上传的图片不经过 API 容器，直接上传至 Cloudflare R2，数据库保存完整公网 URL；单图上限 5MB，签名同时绑定文件大小、类型、公司目录和 15 分钟有效期。AI 模型、DeepSeek 标题生成和妙手均通过该地址读取图片。无需配置或持久化本地 `uploads` 目录。模板“AI生成标题要求”为选填，可保存商品品类、功能与默认写法，留空时仍可根据首图生成英文标题；单条或批量生成可展开“补充要求（选填）”，每个草稿独立填写，仅作用于对应商品，不写回模板，关闭弹窗或重新分组后清空。标题生成固定使用 `deepseek-flash`，显式关闭思考，仅输出 25～255 字符的英文标题，除非模板标题要求或本次补充要求明确要求，否则禁止提及材质、面料、纺织品名称或成分；明确要求时仅使用提示词提供的材质信息，不从图片推断。公司管理员在“成员管理”为每位员工（含管理员自己）单独配置 DeepSeek 标题密钥；密钥加密保存，调用时只使用当前用户自己的密钥，不再读取全局 `DEEPSEEK_API_KEY`。升级后须先配置个人密钥；旧环境文件中的全局密钥或标题模型配置不再生效。

标题请求由系统规则、标题要求、本次补充要求和一张首图组成，不发送商品确认信息、商品描述或其他图片。功能特性只能来自要求中的明确描述；品类未指定时可参考图片，可见颜色、印花和版型参考首图。补充要求在写法和侧重点上优先于默认要求，所有输入均受系统规则约束，冲突或不明确的商品属性应省略。请求参数固定为 `max_tokens=512`、`temperature=0.4`，图片使用 `detail=high`，超时为 45 秒。仅接受 `finish_reason=stop` 的完整响应；后端校验长度、ASCII 英文字符范围和部分格式错误，英文语义、功能真实性和条件式材质规则仍依赖模型遵循提示词，模拟测试不证明模型实际输出准确率。

素材库和产品库的“组合创建草稿”均支持“一键 AI 生成所有标题”，会覆盖已有及手动填写的标题，最多并发 10 个请求，并显示逐组状态和本次进度。失败保留原标题，可“重试未完成”；“停止生成”保留已回填结果、停止后续请求并忽略晚返回结果。生成期间锁定分组、排序、标题编辑和创建操作，仍可预览图片；标题检查通过后由用户确认创建，不自动保存或创建草稿。关闭弹窗后不恢复生成任务。前端模拟测试在 `frontend` 目录执行 `npm test`，需要 Node.js 22.6 或更新版本，不调用真实 AI。

直传分两步：前端先换取预签名地址，再并发 PUT 到 R2，最后提交保存。三个入口：

| 场景 | 入口 | 并发 |
| --- | --- | --- |
| 素材库批量上传 | `POST /material-assets/presign` → PUT → `POST /material-assets/commit` | 8 路 |
| 新增模板的模板图 + 尺码图 | `POST /uploads/presign`（category 为 `template` / `template-size-chart`）→ PUT → 随模板提交 | 两张并行 |
| 产品白底图 | `POST /uploads/presign`（category 为 `template-white`）→ PUT → 随白底图提交 | 单张 |
| AI 创作页印花图 | `POST /uploads/creative-asset/presign` → PUT | 4 路 |

单张失败只重试该张，素材库已成功的地址会保留，重新提交时不会重复上传。

**商品草稿没有独立的尺码图上传。** 草稿一律沿用所选产品模版的 `size_chart_url`，由 `POST /drafts/from-material-assets` 在服务端从模板取值写入，前端不再提交该字段；如需更换尺码图，请修改产品模版。

商品标题去除首尾空白后必须为 25-255 个字符。创建商品草稿只保存本地记录，不会自动调用妙手；用户需要在商品草稿列表点击“发布至妙手”，系统才会创建妙手公共草稿箱商品并继续认领到 TikTok 采集箱。任一步失败时本地草稿都会保留，可从列表重试。

发布至妙手及导出 TikTok、Shopee 表格时，Color 属性值按草稿原始 SKU 图顺序使用 `Color 1`、`Color 2` 等名称，每个商品从 1 开始；同一 SKU 图的所有尺码共用一个 Color 值。规格图片继续关联原始 SKU 图，最终货号/卖家 SKU 仍为 `基础 SKU-尺码`（例如 `M05LRKJLCUYC-S`）；无尺码时只使用基础 SKU。首图和轮播图的编排不影响 Color 编号。此规则用于新建妙手采集箱商品和新导出的表格，不会自动修改已有外部商品。

直传后图片地址由前端提交，服务端在落库处兜底校验：`/material-assets/commit` 校验地址落在当前公司 `material/company/{id}/` 下；模板新增/更新校验 `cover_url`、`size_chart_url` 落在当前公司 `template/` 或 `template-size-chart/` 下。为兼容 R2 之前的历史地址，更新时若字段值与库中现有值一致则直接放行，不强制回溯改造。

`POST /uploads/presign` 的 `category` 走服务端白名单（当前为 `template`、`template-size-chart`、`template-white`），签名本身始终绑定调用方公司。

部署前需在 R2 Bucket 的 **Settings → CORS Policy** 配置前端域名的 PUT 跨域权限，例如：

```json
[
  {
    "AllowedOrigins": [
      "https://erp.haitoro.com",
      "http://localhost:5173"
    ],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["Content-Type", "Content-Length"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

生产环境删除 `http://localhost:5173`；如果 Cloudflare 控制台拒绝 `Content-Length`，可将 `AllowedHeaders` 改为 `["*"]`。修改 CORS 后需要重新生成预签名 URL 再测试，旧签名不要复用。

超级管理员后台“平台概览”会显示待处理、运行中、重试中、最终失败、最早排队时长、每模型积压、近一小时吞吐和近 15 分钟失败率。默认在待处理超过 200 个任务、最早排队超过 10 分钟或近 15 分钟失败率超过 10% 时标红。

R2 不会自动删除对象。可在 Bucket 的 **Settings → Object Lifecycle Rules** 创建生命周期规则：使用前缀 `generated/` 可只清理 AI 生成图，例如设置“创建 90 天后删除”；模板、素材和尺码图使用其他前缀，不受该规则影响。`AI_GENERATED_IMAGE_UPLOAD_TO_R2=false` 时，结果直接保存 Grsai 临时 URL，这些 URL 可能过期。

> Docker Compose 中的密码仅用于本地开发。生产环境必须通过密钥管理服务配置数据库密码、JWT 密钥和妙手凭据加密密钥。

HubStudio 自动上品 XLSX 已改为独立私有 R2 桶，数据库仅保存链接、校验信息和 7 天有效期。需要配置 `R2_HUB_EXPORT_BUCKET` 并迁移至 `20261007_30`，详见 [执行器部署说明](hub_agent/README.md#自动上品-excel-的-r2-存储)。
