# Admin 审查与样式验证

日期：2026-10-09（香港时间）。范围：本机 Admin 的登录、概览、公司管理、模型管理、数据管理、弹窗与响应式布局。沿用现有 Vue 项目、蓝色主色与深色侧栏，本次属于现有界面的样式和交互完善，不是外部设计稿的像素复刻。

## 审查结果与修复

| 步骤 | 页面或操作 | 原始问题 | 当前状态 |
| --- | --- | --- | --- |
| 1 | 登录 | 与后台控件、间距不统一；普通容器未使用表单提交 | 布局通过；统一控件、使用实际 form 和必填校验。新样式下没有重复执行登录写入，已登录会话用于内部验证 |
| 2 | 概览 | 管理入口只有说明文字；尚未加载的数据可被误认为正常零值 | 布局通过；增加可操作入口，核心未加载指标显示破折号，队列状态显示尚未加载 |
| 3 | 公司管理与开通弹窗 | 列表、按钮和弹窗的密度与焦点行为不统一 | 列表及打开/关闭通过；必填属性、邮箱类型和 form 语义已检查，未提交创建公司或修改密码 |
| 4 | 模型列表与修改弹窗 | 模型名称列拥挤，移动端强制1080px宽表；非默认模型按钮被空字符串误判为禁用 | 通过；列表自适应，只有默认模型的设为默认按钮禁用。未写入模型设置 |
| 5 | 数据筛选、素材预览、产品与订单 | 无统一重置入口；长标题造成行高不稳定；弹窗无统一键盘行为 | 查询与重置、预览、订单读取及关闭通过；长标题最多三行，完整文本保留于 title 提示 |
| 6 | 手机与中屏 | 1000px下导航字号为零；620px下导航完全消失 | 通过；390px模型和数据页的 document.scrollWidth 都为390，960px模型页为960；所有文字导航保留 |

原有优势：四个主要模块划分清楚，业务接口、数据筛选和分页能力已具备；因此本次保留原有业务流程，集中整理界面与交互。

## 视觉规范

统一设计变量、40px常规控件、按钮层级、标题字号、页面边距、表格密度、焦点环、禁用和错误状态。删除模型页失效的旧卡片样式，保留列表结构。桌面维持深色侧栏；手机改为顶部文字导航，数据表在面板内滚动。

新增 `DESIGN.md` 和本目录 `AGENTS.md`，供后续前端修改沿用本次规范。TypeScript 设置 noEmit，避免构建时生成源文件旁的 JavaScript。

## 验证与限制

- `npm run build --prefix frontend-admin`：TypeScript 检查与 Vite 生产构建通过。
- `git diff --check`：通过。
- 使用 Codex 内置浏览器与真实本机数据，核对默认桌面1255×954、960×800、390×844。
- 实测：模块导航、数据筛选与重置、素材预览、产品库切换、订单明细读取；弹窗初始焦点、Tab和Shift+Tab循环、Escape关闭与焦点回位。
- 看到一次初始化请求失败，原会话保留，概览刷新后真实数据恢复。修复了数据页在初始化失败时只刷新空公司数据的问题。
- 本轮浏览器捕获的 error/warn 日志为空；这不等于对所有运行状态或第三方资源作保证。
- 未提交创建账号、修改密码、设置默认模型或保存模型参数。保存接口与全部异常分支未做端到端验证。
- 已补充弹窗语义、键盘焦点与减少动画偏好；未做屏幕阅读器及完整WCAG合规审计。
- 本机Admin镜像重建因镜像仓库连接超时失败；通过固定入口 `./deploy/local.sh cp frontend-admin/dist/. admin-web:/usr/share/nginx/html` 更新已有测试容器进行预览。镜像本身未重建成功，重建容器后临时复制的预览会丢失。源码改动已保留。腾讯云未部署。
- 改前数据页桌面截图中的部分图片仍在加载，因此不将07号截图作为完整视觉证据；窄屏08号截图和改后稳定截图用于数据页判断。

## 截图与对应观察

以下截图均来自本轮实际浏览器，并已打开本地文件检查。截图目录：
/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review

### 1. 登录：控件、间距与阴影统一

![改后登录页](/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review/22-login-after.jpg)

### 2. 概览：信息层级、指标与操作入口

![改后概览](/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review/14-overview-after.jpg)

### 3. 公司管理：账号列表与开通表单

![改后公司列表](/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review/12-companies-after.jpg)

### 3a. 公司弹窗：清楚的关闭入口与初始焦点

![改后开通公司弹窗](/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review/13-company-modal-after.jpg)

### 4. 模型列表：名称可读，修改操作降低视觉权重

![改后模型列表](/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review/10-models-after.jpg)

### 4a. 模型弹窗：统一焦点环、表单宽度与操作区

![改后模型弹窗](/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review/11-model-modal-after.jpg)

### 5. 数据管理：筛选重置与稳定表格密度

![改后素材数据](/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review/09-data-after.jpg)

### 5a. 产品库：长标题三行截断；截图处于表格右侧滚动位置

![产品表格右侧与长标题](/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review/20-products-after.jpg)

### 5b. 订单详情：加载完成的真实明细；内容可滚动

![订单详情](/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review/19-orders-after.jpg)

### 6. 手机：修复前导航消失

![改前手机数据页](/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review/08-mobile-before.jpg)

### 6a. 手机：导航完整，筛选与重置保持可用

![改后手机数据页](/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review/18-mobile-data-after.jpg)

### 6b. 手机：模型参数和列表自适应

![改后手机模型页](/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review/16-mobile-models-after.jpg)

### 6c. 中屏：模型列表重排，页面无横向溢出

![改后中屏模型页](/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review/21-tablet-models-after.jpg)

本次范围内的布局与上述只读交互验证完成。未解决的低优先级事项：原有公司路由拼写 `/conpanies` 及大型App组件结构仍保留，可在单独的维护任务处理。

## 页脚布局跟进

根据左下角空白的截图反馈，将已登录页面的备案页脚移入右侧内容区，侧栏背景延伸至页面底部。内容较长时自然滚动，侧栏与页脚底边保持对齐。登录页仍保留独立页脚。

构建通过；桌面与 960px 验证底边对齐，390px 验证导航完整、页脚宽度正常且页面无横向溢出。本机测试容器已复制最新构建产物，未重建镜像或部署腾讯云。

![侧栏与右侧页脚对齐](/Users/rock/.codex/visualizations/2026/10/09/01a11fdf-e3c8-7a30-987b-ed218473e435/admin-review/23-footer-aligned.jpg)

final result: passed
