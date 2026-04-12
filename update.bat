@echo off
cd %~dp0
git add .
git commit -m "update %date% %time%"
git push
echo Done! Changes will be live in ~30 seconds.
pause
