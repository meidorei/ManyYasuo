# AGENTS.md

## 项目简介
ManyYasuo 是 Windows 下的批量文件处理工作台，统一整合四个模块：压缩、预处理、解压、重命名。项目提供统一的 CustomTkinter 界面入口，并通过共享核心模块复用文件系统操作与命名规则。

## 技术栈与运行环境
- Python 3.13+
- CustomTkinter
- tkinterdnd2
- PyInstaller
- uv
- 7-Zip（命令行版 `7z.exe`）

## 常用命令
- 安装依赖：`uv sync`
- 运行程序：`uv run python app.py`
- 单元测试：`uv run python -m unittest discover -s tests -v`
- GUI 冒烟测试：`uv run python tests/ui_smoke.py`
- 性能冒烟测试：`uv run python tests/performance_smoke.py`
- 打包：`uv run pyinstaller --noconfirm --clean main_fast.spec`

## 目录结构概览
- `app.py`：统一桌面入口与页面导航。
- `main.py`：压缩模块页面。
- `preprocessing.py`：预处理模块页面。
- `core.py`：共享核心逻辑，包括命名规则、标签识别、预处理、重命名、解压和文件大小计算。
- `config_store.py`：统一配置存储。
- `job_coordinator.py`：全局任务互斥协调。
- `批量解压/`：解压模块。
- `重命名/`：重命名模块。
- `tests/`：单元测试、GUI 冒烟测试和性能冒烟测试。
- `dist/`：PyInstaller 构建产物。

## 架构约定
- 统一入口是 `app.py`。
- 所有模块共享 `core.py`、`ConfigStore` 和 `JobCoordinator`。
- 同一时间只允许一个文件任务运行。
- 耗时工作放后台线程，通过 `queue.Queue` + Tk `after` 回传 UI 事件。
- 新增业务规则优先放入 `core.py`，并配套单元测试。

## UI 与文案约定
- 界面文案使用中文。
- 保持现有蓝色主题与卡片式布局。