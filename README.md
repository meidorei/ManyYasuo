# ManyYasuo 文件工作台

Windows 10/11 x64 批量文件处理工具，使用 Go 和 MyGo v0.8.3 原生界面，统一提供压缩、预处理、解压和重命名。运行便携版无需 Python、Node 或 WebView。

## 使用

运行 `dist\ManyYasuo\ManyYasuo.exe`。压缩和解压页面需选择已有的控制台版 `7z.exe`，程序不安装或捆绑 7-Zip。

- **压缩**：先确认名称与标签，再进入压缩队列；标签来源冲突必须先解决。支持加密、暂停、继续、取消及失败重试。
- **预处理**：保留原名或启用顺序编号，整理单层嵌套目录，写入标签，显示和复制文件夹大小。
- **解压**：在暂存目录执行，成功后整理输出；失败或取消时保留部分文件并显示位置。
- **重命名**：预览标签生成的名称，处理占名冲突，保护符合关键词规则的目录。

四个页面分别保留队列、选择和参数；支持多路径拖放、文件选择、自然排序、去重及移除。运行任务时可以切换页面和准备其他队列，同一时间只执行一个文件任务。任务使用启动时的参数快照。

默认标签前缀为 `AAA_`，各模块独立设置。配置兼容旧版 `compression`、`preprocessing`、`extraction`、`renaming` 四个分区。开发运行读取项目根目录的 `config.json`；便携版读取 EXE 同目录的配置，以临时文件替换方式保存。配置包含本机路径及用户保存的密码，请勿提交到 Git。

## 开发与构建

最低 Go 版本为 1.27.3，本机验证使用已有的 Go 1.27.4。依赖锁定于 `go.mod` / `go.sum`。下面脚本优先复用 PATH 中的 Go，当前机器还支持已有路径 `D:\SOFTWARE\Go\1.27.4\bin\go.exe`；其他机器可在当前 PowerShell 进程中将已有 SDK 加入 PATH。

```powershell
./tools/go.ps1 run ./cmd/manyyasuo
./tools/build.ps1
```

脚本使用 `GOTOOLCHAIN=local`、`GOPROXY=off`，不会自动安装 SDK 或下载依赖。若缺少缓存，应先确认安装来源、版本和目录，再另行获取依赖。构建缓存和临时文件位于项目 `build\go-cache`、`build\tmp`，模块缓存使用现有 Go 配置；只修改当前进程环境，不修改系统 PATH、注册表或服务。

便携版输出为 `dist\ManyYasuo\ManyYasuo.exe`，带图标、无控制台，嵌入 PerMonitorV2 高 DPI 清单。当前构建保留 Go 调试信息：本机 MyGo release/裁剪构建曾出现 `Access is denied`，原因尚未确认；构建脚本采用已验证的普通 GUI 链接和 Windows 资源写入，不需要额外安装资源编译器。

## 验证

```powershell
./tools/test.ps1
./tools/go.ps1 vet ./...
./tools/go.ps1 run github.com/egoist/mygo/cmd/mygo vet
./tools/go.ps1 mod verify
```

真实 7-Zip、性能和截图测试为显式启用项：

```powershell
$env:MANYYASUO_7Z = 'D:\SOFTWARE\7z\7-Zip\7z.exe' # 改为已有路径
$env:MANYYASUO_PERFORMANCE = '1'
$env:MANYYASUO_RENDER_DIR = "$PWD\build\ui"
./tools/test.ps1
```

测试覆盖命名和标签规则、顺序编号、循环改名与失败回滚、配置兼容、全局任务互斥、密码错误、损坏压缩包、输出失败、暂停后取消、队列隔离、过期扫描结果、中文组合输入、键盘操作和模拟 100% / 150% / 200% DPI。性能场景创建 100 个目录及 20,000 个文件，检测扫描时页面切换和结果回传，超过 500ms 则失败。Windows junction 保护测试必须在允许创建目录链接的环境执行，权限不足时会失败，不会静默跳过。

真实 Win32 消息循环与四模块端到端测试使用隐藏窗口，避免抢占桌面焦点；只操作 `build\tmp` 内自动创建的测试目录：

```powershell
./tools/go.ps1 build -tags smoke -o build/native-smoke.exe ./cmd/native-smoke
./build/native-smoke.exe 'D:\SOFTWARE\7z\7-Zip\7z.exe' "$PWD\build\tmp"
```

## 迁移验收状态

Go 核心、配置、任务、7-Zip 适配和四个原生页面已实现。自动化功能测试、真实 7-Zip 和原生消息循环测试已通过；已观察 Windows 主窗口、图标、中文显示和原生文件选择窗口。

最近一次完整验收有 36 个顶层测试通过、无失败或跳过，20,000 文件扫描约 2.98 秒，最大 UI 循环约 4.5ms，结果保存在 `build/go-acceptance.log`。随后新增的 Windows 图标资源及 Go 构建信息完整性回归测试也已通过。

此前整套运行曾出现超过 500ms 的间歇性延迟，根因仍未确认，不能仅凭最新一次通过关闭性能验收。真实中文输入法候选窗、资源管理器多路径拖放及不同系统 DPI 仍待人工补测，模拟 UI 测试不能替代这些检查。桌面工具已显示原生文件选择框并填入项目测试路径，但确认按钮发生缓存状态错误，未完成实际选择流程。本次按用户要求清理了旧 Python 应用、原 Python 测试、依赖声明及 PyInstaller 配置，历史保留在 Git；代码清理不代表上述人工验收已经完成。现有 `.venv`、缓存、本机配置和旧构建产物保留。

## 代码结构

```text
cmd/manyyasuo/       原生桌面入口
cmd/winresource/     Windows 图标与 DPI 清单写入
cmd/native-smoke/    带 smoke 标签的原生集成测试入口
internal/core/      文件与命名业务规则，不依赖 MyGo
internal/config/    兼容配置与原子保存
internal/jobs/      全局任务协调与事件类型
internal/sevenzip/  外部进程、进度、暂停与取消
internal/workbench/ 四页面 UI、后台扫描与事件派发
assets/             应用图标
tools/              离线运行、测试、打包脚本及图标维护工具
```
