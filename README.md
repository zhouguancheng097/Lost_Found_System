# 拾光 · 失物招领系统

中文失物招领网站，使用 **Spring + Spring MVC + MyBatis**，SQLite 本地数据库，BGE 中文模型辅助语义检索。项目采用显式 SSM 配置，不依赖 Spring Boot。

## 先看文档

三份主要文档在编写项目代码前完成，随后按实际实现修订：

- [需求分析](docs/需求分析.md)：角色权限、功能、申领流程、检索规则和验收标准。
- [详细设计](docs/详细设计.md)：SSM 架构、数据库、接口、事务、页面和排序算法。
- [AI 辅助说明](docs/AI辅助说明.md)：模型选型、本地部署、调用、评测和 AI 辅助开发记录。
- [测试与部署记录](docs/测试与部署记录.md)：真实测试结果、模型校验与已知限制。

## 本机使用

2026-11-19 已完成第一轮优化：登录与注册后自动登录增加成功提示；登录态过期时提示重新登录并保留当前表单；有关键词的搜索过滤低于 30 分及不符合明确特征的结果；页面改为暖色，增大正文字号并调整窄屏布局。需求、详细设计、AI 辅助说明已同步更新为 1.1，验收证据见 `docs/测试与部署记录.md`。

项目已编译，模型已下载。网站启动后访问 **http://127.0.0.1:8080**。

1. 双击根目录的 **启动系统.cmd**，等待显示 Website ready，默认浏览器会自动打开网站。
2. 系统已经正常运行时再次双击，也会直接打开网站。普通用户点击“登录 / 注册”创建账号。
3. 管理员用户名为 `admin`，随机初始密码保存在 **data/admin-credentials.txt**。不把该文件分享或提交到仓库。
4. 发布信息后，管理员在“管理工作台 → 信息审核”通过，记录才出现在广场。
5. 不同用户可申请同一招领物品；管理员核验后批准一人交接，线下交接完成后再“确认已交接”。
6. 双击 **停止系统.cmd** 停止本项目服务；需要重启服务时，先停止再启动。

已按测试需求额外创建 5 个虚构普通用户、16 条带“【测试】”前缀的物品、7 条申请，初始密码统一为 `Demo123456!`。账号为 demo_finder、demo_owner、demo_claimant、demo_banned、demo_delete，其中 demo_banned 初始处于封禁状态。管理员仍沿用原 admin 和原密码。

详见 [手工测试用例](docs/手工测试用例.md) 和 [测试账号与实际编号](data/测试账号与数据.md)。根目录 **初始化测试数据.cmd** 可生成测试清单；重复执行不会重置你操作后的数据。追加数据前自动创建 SQLite 备份，保留原有账号和业务。此前自动验收脚本生成的临时数据仍保持逻辑删除和匿名化。

## 部署位置

| 内容 | 本机目录 |
|---|---|
| 项目源码与页面 | `D:\Lost_Found_System` |
| 三份文档及验收记录 | `D:\Lost_Found_System\docs` |
| 中文模型 | `D:\Lost_Found_System\models\bge-small-zh-v1.5` |
| SQLite 数据库及管理员凭据 | `D:\Lost_Found_System\data` |
| 公开图片 / 私有证明图片 | `data/uploads` / `data/proofs` |
| 模型运行环境 | `D:\Lost_Found_System\.venv` |
| Java 依赖 | `D:\Lost_Found_System\.m2` |
| 服务日志与进程记录 | `D:\Lost_Found_System\runtime` |

网站只监听本机 8080，模型只监听本机 8765；不会自动对公网开放。模型下载自原始 Hugging Face 仓库并校验 safetensors SHA-256；来源、revision、各文件哈希在模型目录 manifest.json 中。

## 功能

- 寻物、招领发布，图片，内容审核；用户管理本人信息，管理员管理所有信息。
- 关键词 + 中文语义 + 类别/地点/日期的混合排序，严格筛选、分页、可确认的建议条件。
- 双向推荐、多人申请、单人交接、最终领取状态、申请撤回、驳回与取消。
- 个人中心、消息通知、封禁、解锁、注销和管理员操作记录。
- 私密联系方式分级可见、隐藏核验特征、私有证明图片、服务端权限与 CSRF 验证。
- 模型不可用时自动退回关键词检索。

## 开发与重建

需要 JDK 21、Maven 3.9+、Python 3.13。当前机器直接使用已安装的 JDK 和 IDEA 自带 Maven；脚本也优先识别 PATH 中的 mvn.cmd。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stop.ps1
```

构建产物是 `target/lost-found-1.0.0.jar` 和 `target/dependency/`，Java 主类 `cn.campus.lostfound.Server`，数据库自动初始化。数据库路径用 JVM 参数 `-Dapp.data=绝对目录`，端口用 `-Dapp.port=8080`，模型地址用 `-Dapp.ai=http://127.0.0.1:8765`；启动脚本支持 `-Port`、`-AiPort`、`-WithoutAI`、`-NoBrowser`（不自动打开浏览器）。

本机 `.venv` 使用 `--system-site-packages` 只读复用现有 CPU PyTorch 等依赖，未改动全局包。迁移到其他电脑建议使用独立环境安装 `ai/requirements.txt`；依赖与硬件兼容性需重新验证，不直接复制当前虚拟环境。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ai\requirements.txt
.\.venv\Scripts\python.exe ai\download_model.py
```

若原站仅通过现有代理可访问，可在当前终端设置 `HTTP_PROXY` 和 `HTTPS_PROXY` 后运行下载脚本；脚本不修改系统代理设置。仅在确需镜像时显式传入 `--endpoint https://hf-mirror.com`，记录来源与校验信息。

## 验证

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build.ps1
.\.venv\Scripts\python.exe scripts\smoke_test.py
.\.venv\Scripts\python.exe ai\evaluate.py
node --check src\main\resources\static\app.js
node scripts\test_frontend.cjs
```

构建命令运行 Java 集成测试；smoke_test.py 和 ai/evaluate.py 需要网站及模型已经启动；JavaScript 语法与前端行为检查无需启动服务。联调会创建临时测试数据并在成功后结束其业务、逻辑删除和匿名化账号；异常中断时可由管理员按 `smoke_` 前缀清理。运行脚本前请不要在测试账号中填写真实个人信息。本轮独立环境的搜索验收结果见 docs/优化联调结果.json，相关运行范围见测试与部署记录第 9 节。

检索评测为 18 条人工构造物品、15 条查询，对比词片段基线与原始语义排序；并非真实业务准确率。混合检索规则另有集成和真实 HTTP 联调验证。详细结果见 docs 下的 JSON 与测试记录。

## 数据备份与限制

停止服务后复制整个 `data` 目录，包含数据库及附件；不能只在运行中复制主 `.db` 文件而忽略 WAL。模型可以按 manifest 重新下载。

第一版支持 SQLite，未实现 MySQL 适配；图片支持 JPEG/PNG，不支持 WebP。未提供邮件短信、密码找回、地图距离和生产级向量数据库。1000 条候选的完整性能目标尚未验收；大量新文本首次编码可能超时并降级。网页响应式样式已编写，但本次自动浏览器环境无法完成可视化验收；实际浏览器和移动端外观仍需人工确认。上线需补充 HTTPS、部署配置、备份、附件保留策略和真实数据检索评测。
