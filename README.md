# ManyYasuo 文件工作台

ManyYasuo 是一个面向 Windows 的批量文件处理桌面工具。它基于 CustomTkinter 和 7-Zip，在同一窗口中整合压缩、预处理、解压和重命名四个模块。

## 功能

- **批量压缩**：读取标签目录或编号名称后的标签，恢复纯编号、重建标签目录，并批量生成加密 7z 文件；标签来源冲突时可在列表中确认。
- **预处理**：默认保留原名，也可启用顺序编号；支持整理嵌套目录、添加标签和复制文件夹大小。
- **批量解压**：读取标签、保护特殊目录名，并将内容安全输出到目标文件夹。
- **文件夹重命名**：预览由标签生成的目标名称，检查冲突后批量改名。

四个模块分别保存设置并维护各自的队列。默认标签前缀为 `AAA_`；修改某个模块的前缀后，该模块只识别对应前缀。执行任务期间仍可切换页面和准备其他队列，但同一时间只能运行一个文件任务。

## 环境要求

- Windows 10/11
- Python 3.13 或更高版本
- [uv](https://docs.astral.sh/uv/)
- [7-Zip](https://www.7-zip.org/) 控制台程序 `7z.exe`

## 从源码运行

```powershell
uv sync
uv run python app.py
```

首次使用时，请在界面中确认 `7z.exe` 的路径。程序设置保存在源码目录（打包后为可执行文件目录）旁的 `config.json` 中；该文件包含本机路径等本地配置，不应提交到 Git。

## 测试

```powershell
uv run python -m unittest discover -s tests -v
uv run python tests/ui_smoke.py
uv run python tests/performance_smoke.py
```

GUI 冒烟测试需要可用的 Windows 桌面会话。

## 构建

```powershell
uv run pyinstaller --noconfirm --clean main_fast.spec
```

构建结果位于 `dist\ManyYasuoFast`。发布时应保留整个目录，入口程序为 `ManyYasuo.exe`，其余运行依赖位于 `_internal` 中。

## 项目结构

```text
app.py              统一桌面入口与页面导航
main.py             压缩模块
preprocessing.py    预处理模块
批量解压/            解压模块
重命名/              重命名模块
core.py             共享文件处理与命名规则
config_store.py     统一配置存储
job_coordinator.py  全局任务互斥协调
tests/              单元测试与冒烟测试
main_fast.spec      PyInstaller 构建配置
```
