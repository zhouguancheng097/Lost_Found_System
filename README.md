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

以下步骤适用于当前开发电脑（已编译并下载模型）；从 GitHub 下载的源码需先按“开发与重建”配置，或使用文末的 Windows 离线安装版。网站启动后访问 **http://127.0.0.1:8080**。

1. 双击根目录的 **启动系统.cmd**，等待显示 Website ready，默认浏览器会自动打开网站。
2. 系统已经正常运行时再次双击，也会直接打开网站。普通用户点击“登录 / 注册”创建账号。
3. 管理员用户名为 `admin`，全新数据库的默认密码为 `123456`，初始凭据保存在 **data/admin-credentials.txt**。不把该文件分享或提交到仓库。
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

## Windows 离线安装版（1.1.2，2026-11-21）

普通使用者可使用 `dist/v1.1.2/Shiguang-Setup-1.1.2-x64.exe`，安装后通过桌面“拾光失物招领系统”启动。该安装包面向 Windows 10 1809 及以上的 x64 系统，内置 Temurin Java 21、CPython 3.13.3、CPU AI 依赖和 BGE 中文模型，运行时无需再下载这些环境。GitHub 的“Download ZIP”提供源码，安装包需单独上传至 Releases。

安装包只包含程序、依赖和模型，首次启动自动创建新数据库，管理员账号 `admin`、默认密码 `123456`。开始菜单提供停止服务、查看管理员账号、打开数据目录和卸载入口。安装版的数据及日志位于 `%LOCALAPPDATA%\\ShiguangLostFound`；更新和卸载默认保留该目录。每台电脑的数据相互独立，网站仅在本机访问。

本地制作安装包的程序、专用验证脚本、安装说明及历史验收资料统一保存在 `安装包制作/`，该目录仅供本机维护，已排除 Git 提交及源码上传范围。制作入口为本机 `安装包制作/制作安装包.cmd`，开发机需要 Python 3.13、AI 依赖、JDK 21 和 Maven；首次打包需联网获取官方运行环境与编译工具。

后续每个版本的源码更新说明、安装包、校验文件、安装说明和发行说明统一放在 `dist/v版本号/`。源码仅提供一份说明文档，写明实际改动、要上传的本地路径和需移除的旧文件，不再额外复制源码目录。源码仓库保留网站、AI 服务、通用开发脚本和项目文档；安装包及其使用说明通过 Releases 单独提供。打包程序不随源码上传副本提供。

1.1.1 修复首次启动时进度窗口不退出：启动器仅等待启动脚本结束，不等待后台服务继承的输出管道关闭；进度窗口关闭后由启动器打开浏览器。开始菜单新增“初始化测试数据”，安装目录也提供同名入口。先启动一次系统，再初始化，即可追加与开发版相同的 5 个虚构测试账号、16 条物品和 7 条申请，密码为 `Demo123456!`，其中 `demo_banned` 初始封禁。初始化先备份，保留安装版管理员、原业务和已修改过的演示状态；不复制开发数据库。安装版清单位于 `%LOCALAPPDATA%\ShiguangLostFound\data\测试账号与数据.md`，编号与开发版可能不同。

## 1.1.2 账号与个人信息（2026-11-21）

登录后点击右上角昵称，可进入“个人信息”“修改密码”“我的发布”“我的申领”，或退出登录。个人信息单独显示在 `/#profile`，修改密码在 `/#profile-password`，支持刷新及浏览器前进、后退。

基本资料包含登录账号、显示昵称、可留空的电话号码和默认地址。普通用户修改登录账号需要验证当前密码；管理员登录账号固定为 `admin`，昵称可修改。默认地址仅预填新发布的地点，可在发布前修改；个人电话不会自动写入公开内容。修改密码需填写当前密码、新密码和确认密码，新密码为 8～128 位；成功后所有旧会话失效，使用新密码重新登录。

全新数据库默认管理员密码为 `123456`，可通过 `LOSTFOUND_ADMIN_PASSWORD` 覆盖；已有数据库升级、重启均保留密码。初始凭据文件不会跟随个人信息页面的密码修改而更新。开发版与安装版数据独立，须使用对应数据目录的账号。需要显式本机恢复默认密码时，运行 `python scripts/reset_admin.py --data <实际数据目录>`；该工具先备份数据库和旧凭据，仅恢复管理员密码，不由启动流程调用。
