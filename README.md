# Касса Control

Кликабельный MVP интерфейса операционного центра для удалённого обслуживания кассовых систем. Прототип собран вокруг сценариев из плана: мультисессионность, SSH/SFTP, SQL, VNC, туннели и определение оборудования.

## Что реализовано

- тёмный адаптивный интерфейс с панелью активных сессий и лимитом в 10 слотов;
- экран обзора с состоянием кассы, ресурсами, сервисами, туннелями и журналом событий;
- вкладки терминала, файлового менеджера, базы данных, VNC и сканера оборудования;
- интерактивный mock SSH-терминал с выполнением безопасных демонстрационных команд;
- тестовые SQL-запросы, выбор таблиц и экспорт результата в CSV;
- модальное окно нового подключения с добавлением сессии в боковую панель;
- быстрый поиск `Ctrl/⌘ K`, горячие клавиши открытия модулей, toast-уведомления и адаптивная мобильная навигация;
- статические файлы без внешних CDN и зависимостей — прототип запускается офлайн.

## Локальный запуск

```bash
python3 -m http.server 4173 --bind 0.0.0.0
```

Открыть `http://localhost:4173`.

## Desktop shell

Добавлен настоящий PySide6 shell поверх этого ядра: боковая панель сессий, вкладки обзора, терминала, файлов, SQL, VNC и оборудования, диалог нового подключения и горячие клавиши `Ctrl+1..6`.

Подключение новой кассы теперь проходит через `qasync + AsyncSSH`: поддерживаются SSH-agent/private key, ссылка на пароль в keyring, jump hosts, удалённые команды, SFTP-клиент и SSH port forwarding. Демонстрационные кассы остаются локальным mock-транспортом, чтобы приложение можно было открыть без оборудования.

Запуск после установки desktop-зависимостей:

```bash
python3 -m pip install -e ".[qt,ssh,secure]"
python3 -m cashdesk_control
```

Без PySide6 core и тесты остаются работоспособными — UI импортируется безопасно и сообщает, какую optional-зависимость установить.

### Windows 10/11

Для целевой Windows-сборки подготовлены `scripts/build_windows.ps1` и PyInstaller spec. Keyring использует Windows Credential Manager, а настройки и логи хранятся в `%APPDATA%`.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build_windows.ps1
```

Результат появится в `dist\CashdeskControl\CashdeskControl.exe` и архиве `dist\CashdeskControl-windows-x64.zip`. Подробности находятся в `packaging/windows/README.md`.

Тот же onedir-архив автоматически собирается GitHub Actions workflow `Windows application` на `windows-latest` по ручному запуску или при push тега `v*`.

## Python core

В `cashdesk_control/` появился независимый от GUI слой для следующего этапа разработки:

- `SessionManager` с ограничением до 10 сессий и событиями lifecycle;
- `KassSession` с инъекцией транспорта, состояниями `connecting/connected/degraded/error` и безопасным snapshot;
- `TunnelManager` и `SSHTunnel` с локальным/удалённым forward, конфликтами портов и автопереподключением;
- `ConnectionProfile` и `ProfileStore` без хранения паролей, `SettingsStore` для несекретных настроек;
- необязательные адаптеры `asyncssh` и `keyring`, которые подключаются только при установке соответствующих зависимостей.

Опциональные интеграции устанавливаются отдельно:

```bash
python3 -m pip install -e ".[ssh,secure]"
```

Проверка без внешних зависимостей:

```bash
python3 -m unittest discover -s tests -v
```

## Kubernetes

`simple-web.yaml` содержит ConfigMap с актуальными `index.html`, `styles.css` и `app.js`, Deployment Nginx и LoadBalancer Service:

```bash
kubectl apply -f simple-web.yaml
```

Исходники интерфейса лежат отдельно в корне репозитория. После их изменения обновить блок ConfigMap можно одной командой:

```bash
python3 scripts/sync_manifest.py
```
