---
name: haitoo-erp-python-runtime
description: 在 haitoo-erp 项目中运行 Python 命令、后端脚本或测试时，使用项目已有的虚拟环境运行时，避免误用系统 Python。
---

# Haitoo ERP Python 运行时

在 `/Users/rock/codespace/haitoo-erp` 项目中执行任何 Python 命令时，始终使用：

```text
/Users/rock/codespace/haitoo-erp/.venv/bin/python
```

包括运行后端、测试、模块、维护脚本和安装或检查 Python 包。例如，运行模块时使用该解释器加 `-m`。

不要直接调用系统 `python` 或 `python3`。如果命令因缺少 Python 依赖而失败，先确认使用的是上述项目运行时，再判断项目环境是否确实缺少依赖。
