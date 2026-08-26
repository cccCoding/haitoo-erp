# HAITOO ERP

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
| 超级管理员 | `owner@haitoo-demo.com` |
| 公司管理员 | `admin@haitoo-demo.com` |
| 运营成员 | `operator@haitoo-demo.com` |

API 文档：`http://localhost:8001/docs`。

超级管理员后台是独立前端项目，启动后访问 `http://localhost:5174`，使用 `owner@haitoo-demo.com` 登录。

## 印花贴合模型配置

超级管理员登录后可在“AI 模型管理”中启用 Seedream、千问图像编辑、Gemini 图像生成并切换默认模型；每个新任务会记录其实际使用的提供方和模型版本。Gemini 默认模型为 `gemini-2.5-flash-image`，输入的模板图和印花图会由后端转为 Gemini 所需的内嵌图片，生成结果会保存至本地媒体库。密钥只由后端读取：

```bash
export SEEDREAM_API_KEY='...'
export QWEN_API_KEY='...'
export GEMINI_API_KEY='...'
export DEEPSEEK_API_KEY='...'
export PUBLIC_MEDIA_BASE_URL='https://pod.example.com'
```

`PUBLIC_MEDIA_BASE_URL` 必须能让模型服务通过 HTTPS 读取 `/media` 下的模板、印花图和商品首图；DeepSeek 的商品标题生成同样依赖该地址。若使用支持视觉输入的 DeepSeek 兼容模型，可通过 `DEEPSEEK_TITLE_MODEL` 覆盖默认模型。

> Docker Compose 中的密码仅用于本地开发。生产环境必须通过密钥管理服务配置数据库密码、JWT 密钥和妙手凭据加密密钥。
