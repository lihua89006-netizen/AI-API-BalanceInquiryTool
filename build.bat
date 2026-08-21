@echo off
rem 一键打包脚本：把程序打包成独立的 API余额查询程序.exe
chcp 65001 >nul
cd /d %~dp0

echo [1/2] 安装打包依赖（清华镜像）...
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller PySide6 requests -q

echo [2/2] 开始打包...
pyinstaller --noconfirm --clean --onefile --windowed --name "API余额查询程序" ^
    --icon assets\app.ico ^
    --version-file version_info.txt ^
    --add-data "assets\app.ico;assets" ^
    --add-data "assets\background.png;assets" ^
    --add-data "assets\fonts;assets/fonts" ^
    main.py

echo.
echo 打包完成：dist\API余额查询程序.exe
echo 把 exe 单独拷走即可运行，config.json 会生成在 exe 同目录。
pause
