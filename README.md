# API按量余额查询工具
可以快速查询你在各大网站的按量余额，也可以小挂件的方式显示。

ps.后续应该会添加各种形式的显示，如按次，计时等

也可以自己用ai工具添加不同站点及余额获取方式

点展示键就会变成可爱鲸鱼娘，自动置顶、可变大小、点击刷新。

<img width="411.5" height="481" alt="1" src="https://github.com/user-attachments/assets/75181fbe-42dd-4deb-bf8c-5751964e60df" />
<img width="369" height="361.5" alt="3" src="https://github.com/user-attachments/assets/17f80799-12b1-4023-992c-b6ce8b048152" />

<img width="194" height="206" alt="2" src="https://github.com/user-attachments/assets/fdf45962-1175-43ed-85e1-8b20cd05bcc3" />

-

点击下载👉[![最新版本](https://img.shields.io/github/v/release/lihua89006-netizen/AI-API-BalanceInquiryTool?label=最新版本&color=blue)](https://github.com/lihua89006-netizen/AI-API-BalanceInquiryTool/releases/latest)



---

以下为AI生成👇

独立运行的 Windows 桌面小工具：把各网站的大模型 API 剩余额度集中显示在一个窗口里。


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
    deepseek.py / max66.py / openai_compat.py / oneapi_newapi.py
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

[GPL-3.0](LICENSE)
