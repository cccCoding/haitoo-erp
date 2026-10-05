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

## HubStudio 本土店自动上品

跨境店管理已移至“妙手管理 → 店铺管理”，可配置妙手 API Key、同步店铺并分配管理人员。“妙手管理 → 公共采集箱”展示妙手公共采集箱商品。

独立的“HubStudio管理”页面管理本土店。公司管理员可手工新增本土店、绑定 HubStudio `containerCode` 与本地执行器，并在导出 TikTok 表格时将其作为“自动上品”目标店铺。

升级到该功能前，必须执行迁移至 `20260917_09`：

```bash
./deploy/local.sh run --rm migrate
./deploy/local.sh restart api submit-worker result-worker
```

管理员操作顺序：在“HubStudio管理”配置公司 HubStudio API、新增本土店、绑定对应 HubStudio 环境与已在线的本地执行器；随后在商品草稿的“导出 TikTok 批量上传表格”中选择该本土店并点击“生成并自动上品”。本地执行器会领取任务、启动该环境、下载不可变 XLSX 快照并提交。

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

默认生产模型为 Grsai 的 `nano-banana-fast`，可在后台启用并选择同平台的 `gpt-image-2`。两个模型共用同一份 Grsai API Key。MySQL 中的任务记录就是队列状态源，`submit-worker` 按创建时间串行提交第三方 API，`result-worker` 独立串行查询异步结果。提交失败最多再重试 2 次，查询未完成或临时失败时留到下一轮。启动生产服务时需要同时运行 `api`、两个 Worker 和 MySQL；任务间隔可由超级管理员在线配置。每个新任务会记录实际使用的提供方、模型版本和创建人。模型平台密钥由公司管理员在“成员管理”中为每位员工单独配置，经加密保存后仅由后端按任务创建人读取，不再使用平台级共享模型密钥。

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

用户上传的图片不经过 API 容器，直接上传至 Cloudflare R2，数据库保存完整公网 URL；单图上限 5MB，签名同时绑定文件大小、类型、公司目录和 15 分钟有效期。AI 模型、DeepSeek 标题生成和妙手均通过该地址读取图片。无需配置或持久化本地 `uploads` 目录。默认使用 DeepSeek 图像理解模型 `deepseek-v4-flash-vision-exp`，可通过 `DEEPSEEK_TITLE_MODEL` 覆盖。

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
