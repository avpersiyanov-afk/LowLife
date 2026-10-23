@echo off
rem Сборка LowLifeMail.exe (Windows, Python 3.12): результат — dist\LowLifeMail.exe в корне репозитория
chcp 65001 >nul
cd /d "%~dp0\..\.."
python -m pip install -r apps\mail\requirements-build.txt || exit /b 1
python -m PyInstaller --noconfirm --clean apps\mail\lowlife_mail.spec || exit /b 1
rem Окно у программы своё, без консоли — start /wait дожидается проверки
start "" /wait dist\LowLifeMail.exe --self-test build\self-test
if errorlevel 1 (type build\self-test\self-test.log & exit /b 1)
echo Готово: dist\LowLifeMail.exe
