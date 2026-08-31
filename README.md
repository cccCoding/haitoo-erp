# Haitoro AI 工作台

多公司、多成员的 TikTok POD 运营系统 MVP。当前版本包含：

- FastAPI + MySQL 8 后端，包含 JWT 登录、公司/角色/店铺授权边界。
- 产品模板、印花贴合模拟任务、人工选图、商品草稿和积分预冻结/按实结算 API。
- Vue 3 运营端工作台，覆盖模板库、POD 工作台、任务、草稿与积分中心。

数据库标准：MySQL 不使用外键；关联字段以普通 ID 和索引保存，所有权限、存在性及删除限制由应用层校验。

妙手接入标准：妙手 App ID 和 App Secret 归属公司级妙手账号，密钥加密后存储；店铺是通过该账号 API 同步的资源，上架也使用公司级妙手账号调用 API。

## 本地启动

```bash
docker compose up --build
```

打开 `http://localhost:5173`。以下演示账号的密码均为 `ChangeMe123!`：

| 角色 | 账号 |
| --- | --- |
| 超级管理员 | `owner@haitoro-demo.com` |
| 公司管理员 | `admin@haitoro-demo.com` |
| 运营成员 | `operator@haitoro-demo.com` |

API 文档：`http://localhost:8001/docs`。

超级管理员后台是独立前端项目，启动后访问 `http://localhost:5174`，使用 `owner@haitoro-demo.com` 登录。

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

超级管理员登录后可在“AI 模型管理”中启用并切换印花贴合模型。默认生产模型为 Grsai 的 `nano-banana-fast`：后端将模板图与印花图 URL 提交为异步任务，并轮询结果接口直至完成。每个新任务会记录其实际使用的提供方和模型版本。密钥只由后端读取：

```bash
export SEEDREAM_API_KEY='...'
export QWEN_API_KEY='...'
export GEMINI_API_KEY='...'
export GRSAI_API_KEY='...'
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

用户上传的图片会直接上传至 Cloudflare R2，数据库保存完整公网 URL；AI 模型、DeepSeek 标题生成和妙手均通过该地址读取图片。无需配置或持久化本地 `uploads` 目录。默认使用 DeepSeek 图像理解模型 `deepseek-v4-flash-vision-exp`，可通过 `DEEPSEEK_TITLE_MODEL` 覆盖。

R2 不会自动删除对象。可在 Bucket 的 **Settings → Object Lifecycle Rules** 创建生命周期规则：使用前缀 `generated/` 可只清理 AI 生成图，例如设置“创建 90 天后删除”；模板、素材和尺码图使用其他前缀，不受该规则影响。`AI_GENERATED_IMAGE_UPLOAD_TO_R2=false` 时，Seedream/千问结果不再复制到 R2，而直接保存供应商 URL；这些 URL 可能过期，Gemini 因只返回内嵌图片仍必须上传 R2。

> Docker Compose 中的密码仅用于本地开发。生产环境必须通过密钥管理服务配置数据库密码、JWT 密钥和妙手凭据加密密钥。
