# Haitoro AI 工作台

多公司、多成员的 TikTok POD 运营系统 MVP。当前版本包含：

- FastAPI + MySQL 8 后端，包含 JWT 登录、公司/角色/店铺授权边界。
- 产品模板、印花贴合模拟任务、人工选图和商品草稿 API。
- Vue 3 运营端工作台，覆盖模板库、POD 工作台、任务与草稿。

数据库标准：MySQL 不使用外键；关联字段以普通 ID 和索引保存，所有权限、存在性及删除限制由应用层校验。

妙手接入标准：妙手 App ID 和 App Secret 归属公司级妙手账号，密钥加密后存储；店铺是通过该账号 API 同步的资源，上架也使用公司级妙手账号调用 API。

## 本地启动

```bash
docker compose up --build
```

Compose 会先运行一次 `migrate` 服务，将数据库升级到代码要求的 Alembic 版本；成功后才启动 API。API 和 Worker 自身只检查版本，不会在启动时建表或执行 DDL。生产部署应在迁移前完成数据库备份，也可显式执行并检查迁移结果：

```bash
docker compose run --rm migrate
docker compose run --rm api alembic current
```

从旧版启动期自动建表流程升级时，迁移服务会拒绝直接接管没有 `alembic_version` 的既有数据库。确认数据库备份可恢复后，显式执行一次：

```bash
docker compose run --rm migrate python -m app.db_migrate --adopt-legacy
```

成功后再正常执行 `docker compose up -d`。不要对全新数据库或已纳入 Alembic 的数据库使用 `--adopt-legacy`。

以后每次修改 ORM 表结构，都必须创建新的版本文件，禁止继续修改已有基线迁移：

```bash
docker compose run --rm api alembic revision --autogenerate -m "变更说明"
```

API 文档：`http://localhost:8001/docs`。

系统启动时不会创建公司、演示账号或默认超级管理员。首次部署后，通过容器内的一次性命令创建平台超级管理员；密码将在终端中安全输入两次，不会进入命令历史或环境变量：

```bash
docker compose exec api python -m app.admin_cli create-super-admin \
  --email owner@example.com \
  --name "平台管理员"
```

超级管理员后台是独立前端项目，启动后访问 `http://localhost:5174`。登录后可开通公司及其首位公司管理员，公司管理员再从运营端创建普通成员。

平台超级管理员的其他运维命令：

```bash
# 查看全部平台超级管理员
docker compose exec api python -m app.admin_cli list-super-admins

# 重置密码；成功后该账号原有登录令牌立即失效
docker compose exec api python -m app.admin_cli reset-super-admin-password \
  --email owner@example.com

# 启用或停用；系统禁止停用最后一个有效的超级管理员
docker compose exec api python -m app.admin_cli disable-super-admin \
  --email owner@example.com
docker compose exec api python -m app.admin_cli enable-super-admin \
  --email owner@example.com
```

超级管理员密码至少 12 个字符，并且必须包含字母、数字和特殊字符。已有数据库升级时，应用不会自动删除历史演示账号或公司；应先创建并验证正式超级管理员，再人工停用历史演示账号，确认其没有业务数据后另行清理。

## 通过 Cloudflare Tunnel 暴露 ERP（无需公网 IP）

这适合当前在本机 Docker 中运行、域名已托管在 Cloudflare 的场景。Tunnel 是本机主动连到 Cloudflare 的出站连接，因此不需要开放路由器端口或配置动态 DNS。

1. 在 Cloudflare Dashboard 中选择 `haitoro.com`，进入 **Zero Trust → Networks → Tunnels**，创建一个 **Cloudflared** tunnel。安装方式选择 Docker，复制其 token（`eyJ...`）。
2. 在 Zero Trust 的该 Tunnel 中创建两个 **Public Hostname**：

   | Public hostname | Service type | URL |
   | --- | --- | --- |
   | `erp.haitoro.com` | HTTP | `http://web:5173` |
   | `admin.haitoro.com` | HTTP | `http://admin-web:5174` |
   | `api.haitoro.com` | HTTP | `http://api:8000` |

   不需要在 DNS 页面手动添加记录；保存 Public Hostname 时 Cloudflare 会自动创建指向 Tunnel 的记录。
3. 将 `.env.example` 中的三项加入本机未提交的 `.env`，并填入实际 token：

   ```dotenv
   CLOUDFLARE_TUNNEL_TOKEN=eyJ...
   VITE_API_URL=https://api.haitoro.com
   CORS_ORIGINS=https://erp.haitoro.com,https://admin.haitoro.com
   ```

4. 重新创建前端以让 Vite 读取公网 API 地址，并启动 Tunnel：

   ```bash
   docker compose --profile tunnel up -d --build
   ```

5. 用手机蜂窝网络访问 `https://erp.haitoro.com` 验证；接口文档可访问 `https://api.haitoro.com/docs`。

不要将 `3306`、`6379` 或 `8001` 配成 Cloudflare Public Hostname。它们无需对外公开。此方式未配置 Cloudflare Access；在正式给他人使用前，至少应为 `erp.haitoro.com` 添加 Access 登录策略，并更换默认 Docker 密码和 `SECRET_KEY`。

## 印花贴合模型配置

超级管理员登录后可在“AI 模型管理”中启用并切换印花贴合模型，并为每个平台模型设置“单个任务印花图数量”。批量快捷操作会按该数量创建多条独立任务；只有服务商保证输出顺序与输入一致时才能把数量设为大于 1，否则必须保持默认值 1。

默认生产模型为 Grsai 的 `nano-banana-fast`。MySQL 中的任务记录就是队列状态源，`submit-worker` 按创建时间串行提交第三方 API，`result-worker` 独立串行查询异步结果。提交失败最多再重试 2 次，查询未完成或临时失败时留到下一轮。启动生产服务时需要同时运行 `api`、两个 Worker 和 MySQL；任务间隔可由超级管理员在线配置。每个新任务会记录实际使用的提供方、模型版本和创建人。模型平台密钥由公司管理员在“成员管理”中为每位员工单独配置，经加密保存后仅由后端按任务创建人读取，不再使用平台级共享模型密钥。

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
# 是否复制 Seedream/千问的生成结果到 R2；默认 true，建议生产环境保持 true。
export AI_GENERATED_IMAGE_UPLOAD_TO_R2='true'
```

## 商品草稿图片制作

任务中心按 `SKU图`、`轮播图`、`首图` 三个子 Tab 展示任务。内部稳定值分别为 `sku_image`、`carousel`、`main_image`；历史任务和缺少类型的任务会迁移为 `sku_image`。每个 Tab 独立保留状态、创作人、日期和分页条件，当前条件同步到 URL。

在商品草稿列表中单选一条草稿后，可进入“制作商品图片”：

- 选择最多 9 个 SKU，每个 SKU 创建一条独立轮播图任务；每个 SKU 最多采用一张结果。
- SKU 图是商品规格的原始图片；没有自定义轮播图时，系统自动以 SKU 图顺序作为轮播图，并把第 1 张作为首图。
- 轮播图与首图的采用、拖拽排序和移除先在弹窗本地暂存，点击最终确认后一次写入草稿。
- 轮播图生成可跳过；首图可基于当前有效轮播图（包括 SKU 回退图）随机参考最多 3 张，或手动选择 1–9 张。
- 首图就是最终轮播列表第 1 张。重新生成的首图会放在第 1 位，商品最终仍最多 9 张。
- 相关任务由用户手动刷新，刷新只更新任务列表，不覆盖当前弹窗暂存的图片编排。
- 最终预览确认后才更新草稿正式发布图片；未进入新版流程的历史草稿继续沿用原图片。
- 已发布到妙手或 TikTok 的草稿图片会锁定，需要复制为新版后继续制作。

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

R2 不会自动删除对象。可在 Bucket 的 **Settings → Object Lifecycle Rules** 创建生命周期规则：使用前缀 `generated/` 可只清理 AI 生成图，例如设置“创建 90 天后删除”；模板、素材和尺码图使用其他前缀，不受该规则影响。`AI_GENERATED_IMAGE_UPLOAD_TO_R2=false` 时，Seedream/千问结果不再复制到 R2，而直接保存供应商 URL；这些 URL 可能过期，Gemini 因只返回内嵌图片仍必须上传 R2。

> Docker Compose 中的密码仅用于本地开发。生产环境必须通过密钥管理服务配置数据库密码、JWT 密钥和妙手凭据加密密钥。
