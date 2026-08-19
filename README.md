# HAITOO ERP

多公司、多成员的 TikTok POD 运营系统 MVP。当前版本包含：

- FastAPI + MySQL 8 后端，包含 JWT 登录、公司/角色/店铺授权边界。
- 产品模板、印花贴合模拟任务、人工选图、商品草稿和积分预冻结/按实结算 API。
- Vue 3 运营端工作台，覆盖模板库、POD 工作台、任务、草稿与积分中心。

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

> Docker Compose 中的密码仅用于本地开发。生产环境必须通过密钥管理服务配置数据库密码、JWT 密钥和妙手凭据加密密钥。
