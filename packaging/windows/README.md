# Windows build

Приложение рассчитано на Windows 10/11 x64 и использует системный Windows Credential Manager через `keyring`.

## Требования

- Python 3.10+;
- OpenSSH client или ключи, доступные AsyncSSH;
- для сборки — PowerShell 5+.

## Сборка

Из корня репозитория в PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build_windows.ps1
```

Результат:

```text
dist\CashdeskControl\CashdeskControl.exe
```

Это onedir-сборка: рядом с exe находятся Qt DLL и плагины. Такой формат быстрее запускается и надёжнее диагностируется, чем onefile-сборка.

## Запуск из исходников

```powershell
py -3 -m venv .venv-windows
.\.venv-windows\Scripts\Activate.ps1
python -m pip install -e ".[qt,ssh,secure]"
python -m cashdesk_control
```

Настройки и логи не попадают в каталог установки:

- `%APPDATA%\Cashdesk Control\settings.json`;
- `%APPDATA%\Cashdesk Control\profiles.json`;
- `%APPDATA%\Cashdesk Control\logs\cashdesk-control.log`;
- `%LOCALAPPDATA%\Cashdesk Control\cache`.
