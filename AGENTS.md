# AGENTS.md

## 项目简介

ManyYasuo 是 Windows 10/11 x64 批量文件工作台，包含压缩、预处理、解压、重命名四个模块。新入口为 `cmd/manyyasuo`，使用 Go 与 MyGo 原生 UI，无 HTTP 服务或 WebView。

## 技术栈与环境

- Go 1.27.3+；当前复用本机 Go 1.27.4。
- `github.com/egoist/mygo` v0.8.3，使用 `ui` 包。
- 外部 `7z.exe`，不安装或捆绑。
- 安装 SDK、下载依赖或修改环境前，必须先说明版本、来源、完整路径、缓存、影响和撤销方法，获得明确同意后执行。优先复用已有工具。
- `tools/go.ps1` 使用已有 SDK 和模块缓存，禁用自动下载；构建缓存、临时文件集中在 `build/`，不修改持久环境。

## 常用命令

- 运行：`./tools/go.ps1 run ./cmd/manyyasuo`
- 单元与 UI 测试：`./tools/test.ps1`
- 静态检查：`./tools/go.ps1 vet ./...`
- MyGo 检查：`./tools/go.ps1 run github.com/egoist/mygo/cmd/mygo vet`
- 构建：`./tools/build.ps1`，产物 `dist/ManyYasuo/ManyYasuo.exe`。
- 真实 7-Zip、性能和原生消息循环测试的启用方式见 README。

## 架构约定

- `internal/core`：命名、标签、目录整理、改名和解压整理，不依赖 MyGo。
- `internal/config`：保留原四个分区、字段和默认值，原子写入。
- `internal/jobs`：全局单任务互斥、任务与条目标识。
- `internal/sevenzip`：参数数组启动外部进程、隐藏控制台、进度、暂停与取消；不记录密码或完整命令行。
- `internal/workbench`：四页面独立状态，后台 goroutine 和 context，使用 channel + `Window.Update` 回到 UI 线程。耗时文件操作不能放在渲染回调。
- 任务使用参数快照；扫描结果携带代次标识，旧结果不能覆盖新状态；进度最多每秒刷新十次。
- 循环改名先暂存再落位，失败回滚并报告实际位置；跳过目录链接；只删除空标签目录；解压失败保留部分文件。
- 发布版配置在 EXE 同目录，开发版在项目根目录。不得提交密码、本机配置、缓存或构建产物。

## 界面约定

- 沿用旧 Python 界面的米白色柔和立体样式；左侧四模块导航，压缩页左右双队列与底部折叠配置，其他模块顶部配置、中央虚拟化队列，底部操作与进度。
- 默认 1360×820，最小 1080×680，系统中文字体，明确焦点和文字状态。
- 压缩维持整理确认、压缩队列两阶段；标签冲突必须先明确来源。
- 任务期间可以切换页面并准备其他队列；退出确认后等待任务停止和必要恢复。

## 迁移边界

- 旧 Python 实现与 PyInstaller 配置暂留作对照，完成性能与 Windows 人工验收后再移除。不得把模拟 UI 测试等同于真实 IME、Explorer 拖放和系统 DPI 验收。
- 旧版可复用现有 `.venv` 执行 `python -m unittest discover -s tests -v`。未经安装授权不要运行会下载依赖的 `uv sync`。
- 不清理已有 `.venv`、缓存、本机配置或旧 dist，不推送或发布。
