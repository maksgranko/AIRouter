@echo off
echo Очистка всех директорий __pycache__ ...

for /d /r %%i in (__pycache__) do (
    echo Удаляю %%i
    rmdir /s /q "%%i"
)

echo Очистка завершена.
pause
