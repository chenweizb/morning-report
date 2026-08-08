@echo off
echo 正在配置身份...
git config --global user.name "vicen"
git config --global user.email "929668265@qq.com"

echo 正在提交代码...
git add .
git commit -m "自动提交"

echo 正在推送到云端...
git push origin main

echo.
echo ==============================
echo 全部完成！按任意键关闭。
echo ==============================
pause