# 赫晨抢单

基于 Playwright 的订单监听页面工具：按价格、关键词和派单方式筛选页面上的订单，符合规则时自动执行抢单确认。

## 技术栈

- **Python 3.11+**：程序主体、订单解析、筛选规则与任务循环。
- **Playwright for Python**：驱动浏览器、读取订单卡片并执行页面点击操作。
- **Google Chrome**：通过 Playwright 的 Chrome 通道启动，使用独立的本地浏览器资料目录保存登录会话。
- **Python 标准库**：`dataclasses` 用于订单模型、`re` 用于文本解析、`pathlib` 管理本地资料目录。

## 环境要求

- Python 3.11 或更高版本
- 已安装 Google Chrome

## 安装

在项目目录中执行：

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install playwright
```

如果 Playwright 提示缺少浏览器组件，可额外执行：

```bash
playwright install
```

## 配置规则

编辑 `config.py` 中的以下选项：

- `SCAN_INTERVAL_SECONDS`：页面扫描间隔，单位为秒。
- `MIN_TOTAL_PRICE`：可抢订单的最低总价；`0` 表示不限制。
- `REQUIRED_KEYWORDS`：商品或备注必须命中的关键词列表；空列表表示不抢任何订单，防止误抢。
- `ALLOWED_DISPATCH_METHODS`：允许的派单方式；空列表表示不限制。

`config.py` 是个人规则文件，已被 Git 忽略；请勿将其提交到公开仓库。

## 运行

```bash
python h.py
```

首次运行会打开 Chrome。请在浏览器中完成目标网站登录，然后保持该浏览器资料目录供后续使用。按 `Ctrl + C` 停止程序。

## GitHub 安全说明

以下本地文件不会被 Git 提交：

- `playwright-profile/`：包含浏览器 Cookie、会话及可能的登录状态。
- `config.py`：包含个人抢单规则。
- Python 缓存、虚拟环境、测试产物和 IDE 配置。

提交前建议执行 `git status`，确认暂存区中没有浏览器资料或其他个人信息。
