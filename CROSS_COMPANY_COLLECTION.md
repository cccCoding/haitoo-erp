# 素材采集

## 使用方式

平台管理员在 Admin「公司管理 → 采集 → 设置」开启权限后，该公司的公司管理员可在 ERP「素材库 → 采集」中选择其他已启用公司的素材库或产品库。新公司自动纳入来源范围。

Admin 公司列表的采集列仅显示「已开启 / 未开启」与「设置」按钮；授权变更记录保留在后台。

勾选图片后，选择本公司产品模板，确认采集。每批最多 100 条不同记录；支持跨页选择。采集只引用原链接，不下载或复制图片，创建新的本公司素材和永久 SKU。原链接失效会影响新素材图片。目标模板名称和采集人用户代码沿用现有 SKU 校验规则。

已存在的图片默认不选中，主动重复采集需要明确确认。素材来源标记为「采集」，素材详情可查看来源信息。素材库页面不再显示采集记录按钮，采集页面仍保留采集记录页签，后台历史数据与接口保留。撤销权限后停止新的浏览和采集，本公司素材与历史保留。

没有采集权限时，素材库的类型筛选不显示「采集」选项。采集素材的来源详情使用图标入口；来源弹窗不显示关闭按钮，可按 Escape 或点击遮罩关闭。

采集页的筛选先编辑、后搜索：修改来源公司、来源库、模板等条件或重置筛选时保留当前结果，点击「搜索」才应用新条件并清空选图。分页、重试及采集提交继续使用已搜索的条件。采集记录页支持按本公司目标模板搜索，也在点击「搜索」后更新结果。

产品库使用原有公司内 SKU 聚合、销量和快照榜单，仅返回选品字段，不返回订单明细、店铺销售拆分、员工账号和个人创作配置。

## 接口与事务

- `PUT /admin/companies/{company_id}/cross-company-collection`：超级管理员提交 `{enabled: boolean}`，记录变更人、时间和原状态。
- `GET /cross-company-collection/capability`：当前账号能力；非获授权公司管理员返回 `enabled: false`。
- `GET /cross-company-collection/companies`、`/filters`、`/items`：授权检查后的来源列表、模板筛选和分页选图。
- `POST /cross-company-collection/collect`：提交 `source_company_id`、`source_library`（`material` / `product`）、`record_ids`、`template_id`、`allow_recollect`，必须携带 `Idempotency-Key` 请求头。目标公司取登录账号，不接受客户端图片链接。
- `GET /cross-company-collection/history`：本公司管理员查看来源快照、操作人和生成素材记录；可传 `template_id` 筛选本公司目标模板，授权关闭后仍可查阅。

记录 ID 先去重、排序再校验。相同公司和请求标识返回原批次结果；同标识不同内容返回 409。整批入库和日志使用同一事务，任一错误整批回滚。

MySQL 中按公司 ID 顺序锁定目标和来源公司，避免相互采集的死锁。授权和重复检测使用锁定后的当前读，避免 REPEATABLE READ 的旧快照漏掉并发入库或权限撤销。图片是否已存在使用原 URL 精确匹配，不进行内容相似度识别。

## 迁移与部署

迁移版本为 `20261013_34`，新增默认关闭的公司权限字段、采集批次、明细与授权变更日志。历史素材不改写。

本机测试已使用固定入口构建、迁移和启动。腾讯云发布需先迁移，再启动对应的新 API、Worker 和前端镜像：

```sh
# 本机
./deploy/local.sh build api migrate web admin-web submit-worker result-worker product-library-rankings-worker
./deploy/local.sh run --rm migrate
./deploy/local.sh up -d --no-build api web admin-web submit-worker result-worker product-library-rankings-worker

# 腾讯云（本次未执行）
./deploy/tencent.sh build api migrate web admin-web submit-worker result-worker product-library-rankings-worker
./deploy/tencent.sh run --rm migrate
./deploy/tencent.sh up -d --no-build api web admin-web submit-worker result-worker product-library-rankings-worker
```

ERP TypeScript 已设置 `noEmit`，移除旧生成的 `router.js`，防止 Vite 优先使用过期路由。

## 验证记录（2026-10-13）

- 新功能 HTTP 测试 8 项通过，覆盖角色、公司隔离、字段白名单、素材和产品入库、新 SKU、去重、幂等、原子回滚、来源删除、榜单筛选及创建草稿。
- 迁移测试 17 项通过，包括默认关闭、升级保留历史与降级。
- 真实 MySQL 并发测试 4 项通过：同标识八路请求只生成一个批次和素材；不同标识并发重复采集被拒绝；执行中撤销按行锁顺序生效；等待加锁前已撤销的请求被拒绝。
- 后端全量测试仍存在 5 个标题校验断言失败；在原版本独立复现，属于既有问题。其余测试通过；MySQL 专项仅在显式设置 `HAITOO_MYSQL_COLLECTION_TEST=1` 时执行。
- Admin 与 ERP 构建通过。真实浏览器验证桌面 1440、中屏 960、手机 390：授权保存、键盘关闭、跨页采集 25 张、已采集项跳过、主动再次采集、销量榜单与产品入库、筛选重置、授权撤销、历史保留和素材来源详情。
- 截图保存在 `output/playwright/collection-admin-{1440,960,390}.png`、`collection-erp-{1440,960,390}.png`、`collection-confirm-390.png`、`collection-product-390.png`、`collection-history-390.png`。
- 本机迁移与镜像验证完成，腾讯云尚未部署；测试公司和测试素材完成验证后清理。
- 文案调整后，Admin、ERP 及接口提示统一使用「采集」；仅移除素材库页面的「采集记录」按钮，采集页面的记录页签仍可查看历史。两端构建与现有 8 项采集接口测试通过；浏览器验证 1440、960、390 三种宽度的入口、类型筛选、授权弹窗和记录页签，页面无横向溢出。新增截图使用 `output/playwright/collection-copy-{admin,materials,erp}-{1440,960,390}.png`，临时验证数据已清理。
- 筛选交互调整后，ERP 构建与 9 项采集接口测试通过，新增目标模板查询及公司隔离覆盖。真实浏览器验证未授权类型隐藏、详情图标、无关闭按钮的来源弹窗、Escape/遮罩关闭和焦点回位、搜索前保持列表、分页沿用已搜索条件、历史目标模板搜索及重置、采集沿用显示记录的来源；来源弹窗、采集页和记录页检查 1440、960、390 三种宽度，页面无横向溢出。截图保存在 `output/playwright/collection-{source-dialog,history-filter,filter-applied}-{1440,960,390}.png`。
