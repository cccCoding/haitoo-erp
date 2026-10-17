# 图片文件去重与素材创建

图片与素材分开保存：`image_files` 仅记录已经校验且成功写入 R2 的文件，`image_addresses` 保存原始链接和历史链接映射；没有图片健康或入库状态。

## 使用规则

- 同公司按实际文件字节的 SHA-256 去重，跨模板、用户和来源生效。
- 默认跳过已有图片素材。用户明确选择“仍创建新素材/SKU”后创建独立记录，复用同一文件和 R2 地址。
- 没有现存素材时允许复用文件重新创建素材。删除素材不删除文件。
- 每次明确创建操作使用新请求键；同一操作重试沿用原键，包括强制创建。
- 外链、本地上传、AI 领取和跨公司采集共用素材创建服务。不同公司独立保存文件。
- 页面最多并发处理四项。关闭页面后停止发起剩余请求，已发送请求可能完成；可重新导入或上传，重复文件会复用。
- 重复提示不返回其他操作人无权查看的 SKU、模板或创建人。

## 上传和导入

本地素材继续浏览器直传，单张最多 3 MiB、每次最多 100 张。浏览器指纹只用于提前查询；未命中的文件上传 `image-upload-tmp/`，提交时后端读取实际字节，核对指纹、大小和实际格式，生成正式内容地址。正式对象不向浏览器签发 PUT 授权。

外链 Excel 每次最多 1,000 条。页面逐条提交；新链接下载、验证并转存，单张最多 3 MiB，支持 JPEG/PNG/WebP。响应声明大小和实际下载字节均执行上限校验。保留公网 DNS 固定连接、重定向目标和实际连接校验。临时网络错误最多三次尝试，间隔 2、5 秒。记录过的来源默认复用已保存版本。

产品库订单导入只保存表格里的原始图片链接，不下载、不转存 R2、不创建图片文件索引；图片源或 R2 不可用不会阻止订单导入。由订单产品创建草稿时，在 SKU JSON 中保留 `product_library_image_url` 来源快照，重新导入更新产品图片不影响已有草稿的导出。

AI 制作输入印花图也按文件 SHA-256 在公司内去重：已有文件直接复用此前的正式 R2 链接；未命中时直传 `image-upload-tmp/`，随后调用 `/uploads/complete` 校验并保存正式文件。同批并发选择的相同内容共用一次上传；任务只接受本公司已登记的图片。新的印花上传不再写入 `creative/`。

通过外链导入本公司 R2 图片时，历史正式对象可保留原路径；`image-upload-tmp/` 和历史浏览器直传的 `creative/` 对象必须复制到正式内容路径后登记。源对象过期、删除或被覆盖，不影响已经保存的正式文件。

素材提交返回逐项 `created / duplicate / error` 结果，这是当前操作结果，不是图片状态。重复项附当前用户的短时文件授权，随后强制创建不必重新下载或上传。

通用模板、白底、尺码图上传增加 `/uploads/complete`：成功后返回正式地址。AI 输出保存不再允许通过配置跳过 R2。

## 导出

内部 TikTok、Shopee 和货盘不下载图片、不探测 HTTP、不执行图片重试。已保存图片通过数据库地址映射写入正式 R2 地址；订单产品原图允许使用本公司的产品记录或草稿来源快照中的原始链接。其他缺少登记的图片会明确阻止导出。货盘不再自动换图，保留商品组数量、SKU 去重、标题、尺码和行数校验。

## 部署与历史整理

迁移版本：`20261017_40`，增加文件索引、地址映射、素材文件关联和创建请求唯一约束，删除 `supply_image_health`。迁移本身不读取外链、不操作 R2。回退会重建空健康表，无法恢复被删除的旧健康记录。

几万张历史图片使用两阶段流程，避免停机后才开始下载全部外链：

1. 旧系统保持运行，构建新版 API 镜像，用 `--prepare --cache-dir` 预下载、校验图片到磁盘。此模式只读取数据库已有字段，兼容 `20261013_36` 至当前版本，不执行迁移、不写数据库、不写 R2；已有 R2 图片通过 S3 API 读取。可以重复执行，完整缓存自动复用。
2. 维护窗口内停止 API、前端入口及相关 Worker，备份数据库，迁移至 `20261017_40`，再用 `--apply --cache-dir` 登记文件索引、地址映射及素材关联。正式回填重新扫描数据库，不依赖预缓存时的引用清单；期间新增或改过链接的图片会按当前 URL 从网络补齐，已删除引用不再处理。
3. 全量应用无错误后同时切换前后端并启动 Worker。缓存只省去外链下载；正式 R2 写入、核验及数据库登记仍在停机窗口内，耗时应以小批量实测为准，不能保证几分钟完成。

旧 API/Worker 不兼容迁移后的版本，不能在迁移后恢复旧程序；旧前端也不兼容新上传接口。未完成全量回填时不能开放新素材写入，否则可能漏查历史重复。预缓存保存的是该 URL 当时通过校验的文件字节；同一 URL 后续内容改变不会自动刷新缓存，若需新版内容，停写后移除对应地址缓存再预缓存。

本机只使用 `./deploy/local.sh`；腾讯云只使用 `./deploy/tencent.sh`。构建和更新 `api`、`web`、`submit-worker`、`result-worker`、`supply-worker`、`product-library-rankings-worker` 及迁移服务。统计 Worker 也检查数据库版本，不能遗留旧镜像。不覆盖环境文件或数据库卷，不清理镜像缓存。原 `SUPPLY_IMAGE_CONCURRENCY` 和 `AI_GENERATED_IMAGE_UPLOAD_TO_R2` 环境变量已不参与逻辑，可在后续维护时移除。

### 并发、进度与恢复

- 命令行默认 8 个并行任务，同一来源域名最多 4 个，可通过 `--workers`（1–32）和 `--per-host` 调整。相同公司、相同 URL 合并处理，再关联全部历史素材；不同公司独立登记，保留所有原 SKU。不要同时启动多个正式回填进程。
- 每 5 秒向标准错误输出 JSON 进度，包括不同公司/地址总数、已完成数、失败数、缓存/网络来源、每秒速率和剩余时间估算。多个记录共用一张图片时，总引用数大于不同地址数。完整逐项 JSONL 保存在 `--report`；`--verbose` 可同时输出逐项结果。
- `--limit 100` 用于小批量测速，按不同公司/地址计数；进度中 `limited: true` 不代表全量完成。上线前必须去掉 `--limit` 和 `--retry-from` 再跑一次全量应用检查。只使用 `--company-id` 时也只验证该公司。
- 预缓存中断后重跑原命令，完整缓存会跳过下载；原子落盘未完成的条目重新处理。正式回填中断后也可全量重跑，数据库索引是完成依据，已登记文件不再下载或上传，并继续补齐素材关联。报告不是跳过成功条目的唯一依据，避免报告与数据库恢复状态不一致。
- `--retry-from` 只重试旧报告中最后一次结果为 `error` 的地址，支持旧版报告。失败会返回非零退出码。被中断的报告可能缺少尾部或在途结果，只重试报告不足以补齐未执行记录，最终仍应全量运行。修改了原 URL 的引用以新扫描结果为准。
- 缓存按公司隔离、按 SHA-256 保存文件；正式登记再次验证哈希和图片格式。损坏缓存明确报错，不跳过校验。可删除 `<缓存目录>/<公司ID>/addresses/<URL的SHA-256>.json`，再重跑预缓存修复。缓存不应在本机/生产环境之间混用。
- 缓存和报告必须持久化挂载，并限制目录访问。单张最多 3 MiB，3 万张不同文件的容量上限约 88 GiB；实际通常更小，相同公司同内容共用缓存文件。先检查磁盘空间，保留数据库备份空间；上线验收完成后再按需清理缓存。中断可能遗留无引用文件或隐藏临时文件，重复执行不依赖它们。

### 腾讯云命令

以下在服务器项目根目录、同一个终端执行；假定已有数据库和 `.env`，各阶段成功后再继续。需要先同步含新版脚本的代码。

```sh
umask 077
mkdir -p deploy-image-cache deploy-reports deploy-backups
df -h .

# 构建不会重启运行中的旧容器。
./deploy/tencent.sh build migrate api web submit-worker result-worker product-library-rankings-worker supply-worker

# 阶段一：旧系统仍在线，先处理 100 个地址评估速度和磁盘用量。
./deploy/tencent.sh run --rm -T --no-deps \
  -v "$PWD/deploy-image-cache:/image-cache" -v "$PWD/deploy-reports:/reports" \
  api python -m scripts.backfill_image_files --prepare --cache-dir /image-cache \
  --workers 8 --per-host 4 --limit 100 --report /reports/images-sample.jsonl

# 去掉数量限制完成预缓存；中断后可重复运行。
./deploy/tencent.sh run --rm -T --no-deps \
  -v "$PWD/deploy-image-cache:/image-cache" -v "$PWD/deploy-reports:/reports" \
  api python -m scripts.backfill_image_files --prepare --cache-dir /image-cache \
  --workers 8 --per-host 4 --report /reports/images-prepared.jsonl
```

确认预缓存无错误并安排维护窗口后执行；任何一步失败都应保持停写，不继续启动服务：

```sh
(
  set -e
  umask 077
  ./deploy/tencent.sh stop edge api submit-worker result-worker product-library-rankings-worker supply-worker
  backup_file="deploy-backups/pre-image-backfill-$(date +%Y%m%d-%H%M%S).sql"
  ./deploy/tencent.sh exec -T mysql sh -c \
    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --routines --triggers --events --no-tablespaces --set-gtid-purged=OFF haitoro' \
    > "$backup_file"
  test -s "$backup_file"
  ./deploy/tencent.sh run --rm --no-deps migrate
  ./deploy/tencent.sh run --rm --no-deps api alembic current
  ./deploy/tencent.sh run --rm -T --no-deps \
    -v "$PWD/deploy-image-cache:/image-cache" -v "$PWD/deploy-reports:/reports" \
    api python -m scripts.backfill_image_files --apply --cache-dir /image-cache \
    --workers 8 --per-host 4 --report /reports/images-applied.jsonl
)
```

应用失败时修复原因后重跑上一条正式应用命令即可，已成功地址自动复用。若只需集中处理失败项，可临时加 `--retry-from /reports/images-applied.jsonl --report /reports/images-retry.jsonl`（替换原 `--report`）；随后去掉 `--retry-from` 再做全量检查。

确认全量完成、`errors: 0` 且 `limited: false` 后恢复新版服务：

```sh
./deploy/tencent.sh up -d --no-deps --no-build api web submit-worker result-worker product-library-rankings-worker supply-worker
./deploy/tencent.sh logs --tail=80 api submit-worker result-worker product-library-rankings-worker supply-worker
./deploy/tencent.sh up -d --no-deps --no-build edge
./deploy/tencent.sh ps
```

### 本机命令

本机使用独立测试数据库和测试 R2 桶。相同的两个阶段全部使用 `./deploy/local.sh`，停写时停止 `web admin-web` 而非 `edge`。核心命令如下；备份和迁移成功后再正式应用：

```sh
umask 077
mkdir -p deploy-image-cache deploy-reports deploy-backups
./deploy/local.sh build migrate api web submit-worker result-worker product-library-rankings-worker supply-worker

# 迁移前预缓存；若本机已迁移，也可直接执行此命令。
./deploy/local.sh run --rm -T --no-deps \
  -v "$PWD/deploy-image-cache:/image-cache" -v "$PWD/deploy-reports:/reports" \
  api python -m scripts.backfill_image_files --prepare --cache-dir /image-cache \
  --workers 8 --per-host 4 --report /reports/images-prepared.jsonl

./deploy/local.sh stop web admin-web api submit-worker result-worker product-library-rankings-worker supply-worker
```

停写后先完成本机数据库备份，再执行：

```sh
(
  set -e
  ./deploy/local.sh run --rm --no-deps migrate
  ./deploy/local.sh run --rm -T --no-deps \
    -v "$PWD/deploy-image-cache:/image-cache" -v "$PWD/deploy-reports:/reports" \
    api python -m scripts.backfill_image_files --apply --cache-dir /image-cache \
    --workers 8 --per-host 4 --report /reports/images-applied.jsonl
)
```

全量成功后启动：

```sh
./deploy/local.sh up -d --no-deps --no-build api web submit-worker result-worker product-library-rankings-worker supply-worker
./deploy/local.sh start admin-web
./deploy/local.sh ps
curl --fail http://127.0.0.1:8001/health
```

脚本覆盖素材、产品模板图片和尺码图、个人白底图、草稿最终图和 SKU 图、AI 结果及历史输入印花图；产品库订单图片及草稿中保留的订单原图不转存。历史 `creative/` 输入图经回填登记后，可参与后续上传去重。旧 URL 通过地址映射解析，不强制重写历史业务 JSON。失败项需修复后重跑，不能当成成功。

## R2 保留策略

正式图片长期保留，不应用 Excel 七天过期规则，也不自动删除旧重复对象。必须核对现有桶规则，确保正在引用的 `generated/`、`material/`、`template/` 等旧图片前缀未被自动清理。

临时区清理可由维护脚本增加，保留桶内其他规则，仅对 `image-upload-tmp/` 配置一天后删除：

```sh
# 本机
./deploy/local.sh exec -T api python -m scripts.backfill_image_files --apply --configure-temp-lifecycle --report /tmp/images-applied.jsonl
# 腾讯云
./deploy/tencent.sh exec -T api python -m scripts.backfill_image_files --apply --configure-temp-lifecycle --report /tmp/images-applied.jsonl
```

该配置需要 R2 凭据具备桶生命周期管理权限；无法配置时脚本明确失败，不会自动扩大权限或修改其他规则。

已转存图片不再依赖第三方链接有效期，访问依赖 R2、公开域名和保留策略正常运行。订单产品保留的原图仍依赖来源链接有效。

## 本次验证

2026-10-18 规则调整：外链 3 MiB 上限、订单导入保留原链接、AI 输入印花去重，以及订单换图后草稿来源快照等受影响的 180 项后端回归全部通过；前端 22 项测试及生产构建通过。存储和下载使用测试替身，未操作实际 R2。

全量后端回归共 469 项，460 项通过、9 项因专用测试配置缺失而跳过；后续受影响的 197 项专项回归全部通过。另在本机独立 MySQL 临时库实际运行 6 项迁移、并发去重、旧事务当前读和强制创建幂等测试并通过，数据库及临时授权已删除。前端 21 项测试和生产构建通过。浏览器以独立会话验证重复默认跳过、强制创建新请求键、四项并发、关闭停止及 Escape 关闭，并完成会话清理。

没有操作业务数据库迁移、历史图片转存、生产部署或实际 R2 生命周期配置。上线仍需按上文暂停写入、迁移、回填并核对存储保留规则。
