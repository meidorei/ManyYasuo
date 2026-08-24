# ManyYasuo 文件工作台

一个基于 CustomTkinter 和 7-Zip 的 Windows 文件处理工具，在同一窗口中提供四个独立模块：

- 批量压缩：自动读取标签目录或编号名称后的标签，恢复纯编号、重建标签目录并批量生成加密 7z 文件；两种来源冲突时需在列表中确认。
- 预处理：默认保留原名，可手动开启顺序编号；支持整理嵌套目录、添加标签和点击复制文件夹大小。
- 批量解压：读取标签、保护特殊目录名并安全输出文件夹。
- 文件夹重命名：预览标签生成的目标名称，检查冲突后批量改名。

四个模块拥有独立设置和队列。默认标签前缀都是 `AAA_`；如果手动设置为不同值，读取模块只识别本页设置的前缀。任一模块运行时可以继续切换页面和准备其他队列，但不能同时开始第二项文件任务。

## 运行源码

安装控制台版 7-Zip 后执行：

```powershell
uv sync
uv run python app.py
```

## 测试

```powershell
uv run python -m unittest discover -s tests -v
uv run python tests/ui_smoke.py
uv run python tests/performance_smoke.py
```

## 构建快速启动版

```powershell
uv run pyinstaller --noconfirm --clean main_fast.spec
```

生成目录为 `dist\ManyYasuoFast`。发布时保留整个目录，用户运行其中的 `ManyYasuo.exe`，依赖统一位于 `_internal` 中。
