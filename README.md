# API 余额查询程序（API 额度监控器）

独立运行的 Windows 桌面小工具：把各网站的大模型 API 剩余额度集中显示在一个窗口里。

支持**窗口置顶**、**深色/浅色/跟随系统主题**、**站点搜索与排序**、**单站点「展示」小窗**（自定义背景图 + 自动刷新）。

## 功能

- 📊 每个网站一张卡片，显示余额；卡片可搜索、可排序（↑↓）
- 🔄 全部刷新 / 单个刷新；启动自动刷新；网络错误自动重试；每个站点可单独设置刷新间隔
- 🖼 单站点「展示」窗口：独立贴纸小窗（自带动画背景图），单击刷新、每 60 秒自动刷新，可拖动缩放、可记住大小
- 🌗 深色 / 浅色 / 跟随系统 三档主题
- ✅ 添加/编辑站点时可先「测试连接」；每站点可配 HTTP 代理
- 🔧 配置保存在 exe 同目录的 `config.json`（可直接编辑备份）
- 🧩 适配器架构：每个网站一个适配器文件，新增网站只需加一个文件并注册

## 已内置的适配器

| 适配器 | 适用网站 |
| --- | --- |
| DeepSeek 官方 | DeepSeek 官方 API（`/user/balance`，余额 CNY，含赠送/充值明细） |
| MaxAI 中转站 (max66.xyz) | 账号密码登录查余额：剩余次数 + 按量余额（CNY）+ 今日已用 |
| 基元律动 (tokenrhythm.studio) | OpenSquilla 平台，用户名+密码登录查钱包：赠送/充值/欠费/冻结余额 + 用量 |
| Sub2API (api.muteki.site) | Sub2API AI API Gateway，邮箱+密码登录查余额（USD） |
| OpenAI 兼容计费接口 | OpenAI 官方，以及沿用 `/v1/dashboard/billing/credit_grants` 计费结构的中转站 |
| One-API / New-API 框架 | 国内主流中转站（one-api / new-api / uni-api 等部署的站） |

## 运行（源码方式）

需要 Python 3.10+：

```bash
pip install -r requirements.txt
python main.py
```

## 打包成 exe

双击 `build.bat`，或手动执行：

```bash
pyinstaller --noconfirm --clean --onefile --windowed --name "API余额查询程序" ^
    --icon assets\app.ico --version-file version_info.txt ^
    --add-data "assets\app.ico;assets" ^
    --add-data "assets\background.png;assets" ^
    --add-data "assets\fonts;assets/fonts" ^
    main.py
```

产物在 `dist\API余额查询程序.exe`，可单独拷到任何 Windows 机器运行（免 Python 环境）。

## 添加新网站的适配器

1. 在 `app/providers/` 下新建文件，继承 `base.Provider`：

   ```python
   class MySiteProvider(Provider):
       id = "my_site"
       name = "我的站点"
       description = "..."
       config_schema = [
           {"key": "api_key", "label": "API Key", "type": PASSWORD, "required": True},
       ]

       def fetch(self, session):
           data = self.get_json(session, "https://.../api/quota", headers={...})
           return QuotaInfo(ok=True, remaining=..., currency="CNY", raw=data)
   ```

2. 在 `app/providers/__init__.py` 的 `PROVIDERS` 字典里注册一行。

3. 重新打包即可，界面无需任何改动。

## 目录结构

```
main.py                    入口
app/
  main_window.py           主窗口（卡片、搜索排序、主题菜单、展示窗口入口）
  show_window.py           单站点展示窗（背景图 + 自动刷新）
  theme.py                 深/浅/跟随系统主题
  config.py                配置读写 config.json
  worker.py                后台线程刷新（含网络错误自动重试）
  providers/
    base.py                适配器基类（Provider / QuotaInfo）
    deepseek.py / max66.py / tokenrhythm.py / muteki.py
    openai_compat.py / oneapi_newapi.py
    __init__.py            适配器注册表
test_smoke.py              无界面自检（不依赖真实站点）
verify_live.py             真实环境验证（读取 config.json 逐一真实查询）
build.bat                  一键打包脚本
version_info.txt           exe 版本信息
config.example.json        配置模板
```

## 验证方式

- `python test_smoke.py`：无界面自检（本地假服务器模拟各网站响应，不依赖真实账号）
- `python verify_live.py`：读取 `config.json` 的站点，用真实账号/Key 逐一查询（网站改版时第一时间发现）

## ⚠️ 安全提醒

- `config.json` 里保存的是**明文 API Key / 账号密码**，请勿将它与他人共享、勿提交到 Git（已在 `.gitignore` 中排除）。
- 首次使用可复制 `config.example.json` 为 `config.json` 并按注释填写。

## 贡献

欢迎提交适配器、修复 Bug、改进界面。请先运行 `python test_smoke.py` 确保测试通过。

## 开源协议

[MIT](LICENSE)
