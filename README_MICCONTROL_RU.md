# Danygramm для Android

Экспериментальный неофициальный клиент на основе Telegram Android **13.0.2 (7175)**, исходный commit `f32ffeec763f0bdbf4bec25b52d654f77bff733d`. Первый вариант предназначен для проверки обработки микрофона в личных звонках на **vivo X200 Ultra / arm64-v8a**, включая гарнитуру AirPods 3.

Новое имя приложения — **Danygramm**. Android application ID **`org.miccontrol.messenger.web`** и прежний ключ подписи сохраняются: новая версия предназначена для обновления установленного MicControl без удаления приложения. Клиент можно установить рядом с официальным Telegram; аккаунт в нём добавляется отдельно.

## Скачать Danygramm dev4

Собрана версия **`13.0.2-danygramm-dev4` / code `71789`**, Android 6+ (`minSdk 23`, `targetSdk 36`), arm64. Локальный APK — `artifacts/Danygramm-arm64-dev4.apk`, размер **65 658 828 байт**, SHA-256 **`c059f169bea7574e4556e4ed6dd66cfc8450e1d2448b957c9f3f70047f53b099`**.

[Скачать Danygramm dev4 — APK](https://github.com/DV-Design/MicControl-Telegram/releases/download/danygramm-dev4/Danygramm-arm64-dev4.apk) · [Страница prerelease](https://github.com/DV-Design/MicControl-Telegram/releases/tag/danygramm-dev4). Репозиторий **приватный**: для доступа нужно войти в GitHub под аккаунтом с доступом к нему.

Релиз опубликован из исходников `88e1822557ba78eb6cd928f1751a19e961752fb5`. После публикации APK и файл SHA-256 полностью скачаны с авторизацией GitHub: размер, хеш и контрольная сумма совпали с локальной проверенной сборкой. Подтверждение — `artifacts/qa/dev4-release-download/verified.json`.

В dev4 меняются название, иконка и меню микрофона: компактная кнопка находится внизу справа над управлением звонком, а выбор режима открывается нижней панелью только по нажатию. Для текста, фона и переключателей панели заданы собственные контрастные цвета, независимые от светлой или тёмной темы приложения. Собственные API credentials и ключ подписи остаются прежними.

Локальная повторная сборка приложения и Android test APK прошла за **1 мин 52 с**: 328 Gradle tasks, из них 44 выполнены и 284 не требовали пересборки. Проверены имя Danygramm в APK, версия, arm64-библиотеки и подпись v1/v2 прежним сертификатом. Собственная API-конфигурация совпала с dev3; sample API отключён. Имена приложения проверены во всех 10 локализациях standalone-модуля, варианты новой иконки просмотрены по превью. Лог сборки — `artifacts/qa/dev4-build.log`, метаданные APK — `artifacts/qa/dev4-candidate.json`.

На эмуляторе Android 16 arm64 с английской локализацией APK установился поверх dev3 без сброса данных. Проверка метаданных прошла, на экране приложений просмотрены название Danygramm и новая иконка. Все **4 проверки панели микрофона прошли за 6,867 с**: оба режима в светлой и тёмной теме, контраст шести текстовых элементов не ниже **5,77:1**, реальное нажатие, выбранное состояние, доступность и закрытие панели. Полный экран реального звонка, расположение кнопки и скрытие/повторный показ управления проверены по исходникам; тесты панели не запускали звонок. Подробные результаты и ограничения — в [отчёте Android-проверок](tests/miccontrol/ANDROID_RUNTIME_TESTS.md).

### История dev3: вход подтверждён пользователем

18 октября 2026 года пользователь сообщил **«Работает»** после версии dev3 с собственными API credentials. Это подтверждение личного production-входа со стороны пользователя. Оно не заменяет отдельные автоматические E2E-проверки сообщений, файлов, звонков или Bluetooth-аудио; таких результатов для dev3 нет.

[Исторический релиз MicControl dev3](https://github.com/DV-Design/MicControl-Telegram/releases/tag/miccontrol-dev3): версия `13.0.2-miccontrol-dev3` / code `71779`, размер 65 652 128 байт, SHA-256 `a4340f91518cabe3e8367965413784953676412c4823affd0511fd49337a8b70`. Он собран в [успешном GitHub Actions run](https://github.com/DV-Design/MicControl-Telegram/actions/runs/39156162098). Для него проверены подпись, обновление прежнего APK, запуск на Android 16 arm64 и один MTProto network-тест. Историческая автоматическая попытка входа с резервным номером на TestDC2 остановилась на `PHONE_CODE_INVALID`; отказ воспроизвёл независимый клиент. Полного повторного запуска 16 тестов на dev3 не было. Подробности и исторический PASS dev2 сохранены в [отчёте Android-проверок](tests/miccontrol/ANDROID_RUNTIME_TESTS.md).

Для личного аккаунта **выключите «Test Backend» / «Тестовый сервер»** на экране номера: настройка может сохраниться после обновления.

## Что нужно для сборки

| Компонент | Версия |
|---|---|
| JDK | 21 |
| Gradle | 8.13, загружается `gradlew` |
| Android Gradle Plugin | 8.13.2 |
| Android SDK | platform 36; platform 35 для модулей Media3 |
| Android Build Tools | 36.0.0; 35.0.0 для зависимых модулей |
| Android NDK | 27.2.12479018 |
| CMake | 3.22.1 |
| ABI первого APK | arm64-v8a |

Также нужны Git с submodules и доступ к Maven/Google Maven. Первоначальная загрузка SDK и native-сборка занимают несколько гигабайт. На Apple Silicon некоторые инструменты NDK используют Rosetta 2.

Для macOS с Homebrew:

```bash
brew install openjdk@21
brew install --cask android-commandlinetools
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
export ANDROID_HOME="$HOME/Library/Android/sdk"
export PATH="$JAVA_HOME/bin:$PATH"
sdkmanager --sdk_root="$ANDROID_HOME" --licenses
sdkmanager --sdk_root="$ANDROID_HOME" \
  'platform-tools' 'platforms;android-36' 'platforms;android-35' \
  'build-tools;36.0.0' 'build-tools;35.0.0' \
  'ndk;27.2.12479018' 'cmake;3.22.1'
```

На Intel Mac или Linux укажите `JAVA_HOME` для своей установки JDK 21 и `ANDROID_HOME` для Android SDK. Android Studio для командной сборки не требуется.

## Свои Telegram API credentials

Получите `api_id` и `api_hash` через [API development tools](https://my.telegram.org/apps), как описано в [документации Telegram](https://core.telegram.org/api/obtaining_api_id).

Для сборки в GitHub Actions:

1. Откройте [my.telegram.org/apps](https://my.telegram.org/apps), создайте API application и сохраните выданные `api_id` и `api_hash`.
2. В [репозитории MicControl](https://github.com/DV-Design/MicControl-Telegram) откройте **Settings → Secrets and variables → Actions → New repository secret**. Добавьте `TELEGRAM_API_ID` и `TELEGRAM_API_HASH`. Затем в **Actions → Build MicControl APK with own API → Run workflow** выберите ветку `main` и запустите сборку.

Собственные API secrets уже настроены; с ними dev3 успешно собран 18 октября 2026 года, исторический artifact — `MicControl-arm64-3`. Для Danygramm dev4 используется та же API-конфигурация. Существующий ключ подписи хранится отдельно в `MICCONTROL_DEBUG_KEYSTORE_B64`; workflow проверяет его fingerprint для установки поверх прежнего MicControl. В artifact входят только APK и SHA-256. Отсутствующие/некорректные secrets и публичный sample API останавливают workflow до загрузки submodules, SDK и native-сборки. Проверка формата credentials и успешная сборка сами по себе не подтверждают вход в Telegram.

Создайте в корне **`local.properties`** по примеру [local.properties.example](local.properties.example). Укажите свой `sdk.dir`, `TELEGRAM_API_ID` и `TELEGRAM_API_HASH`. Файл исключён из Git. Альтернативный способ — передать переменные окружения `TELEGRAM_API_ID` и `TELEGRAM_API_HASH`; окружение имеет приоритет.

Ранние APK dev1/dev2 собраны с публичным sample API upstream. На production-сервере подтверждён отказ `API_ID_PUBLISHED_FLOOD`; dev3 использует собственную конфигурацию без sample API. CI запрещает sample API и не делает попыток входа. Значения API попадают в APK, поэтому `api_hash` нельзя считать секретом, надёжно скрытым внутри приложения.

## Сборка APK

Из корня репозитория:

```bash
git submodule update --init --recursive --depth=1
./scripts/build-apk.sh
```

Для локальной сборки укажите собственные API credentials. Скрипт создаёт `.local/miccontrol-debug.keystore`, собирает только **arm64-v8a** с двумя Gradle workers и heap 4 GB, проверяет подпись и сохраняет:

- `artifacts/MicControl-arm64-dev.apk`
- `artifacts/MicControl-arm64-dev.apk.sha256`

Скрипт пока сохраняет историческое имя файла `MicControl-arm64-dev.apk`; название и версия установленного приложения берутся из текущей конфигурации. Для dev4 проверенный APK также сохранён как `artifacts/Danygramm-arm64-dev4.apk`.

Исходный результат Gradle: `TMessagesProj_AppStandalone/build/outputs/apk/afat/debug/app.apk`. Вариант сборки — `AfatDebug`; приложение допускает отладку. Это тестовый APK, не подписанный production-ключом. Сохраните `.local/miccontrol-debug.keystore`, если хотите устанавливать следующие сборки как обновление без удаления приложения. При новой подписи Android потребует удалить прежнюю установку или использовать прежний ключ.

Для ручного запуска Gradle после создания локального ключа:

```bash
export MICCONTROL_ABIS=arm64-v8a
./gradlew :TMessagesProj_AppStandalone:assembleAfatDebug \
  --max-workers=2 --no-parallel --console=plain \
  '-Dorg.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g'
```

`.local/`, `local.properties`, `artifacts/` и файлы APK исключены из Git. Upstream dummy `release.keystore` не используется для debug APK; release/публикация требуют отдельной настройки production-подписи.

## Native-тесты

Для проверки аудиообработки на компьютере нужны Python 3 и Clang/Clang++:

```bash
python3 tests/miccontrol/run_native_tests.py --sanitize
```

Тесты компилируют включённые в проект RNNoise и WebRTC sinc resampler. Проверяются mono/stereo при 8/16/32/48 кГц, точный bypass в режиме «Стандартный», 50 переключений на каждой частоте, конечность и допустимый диапазон амплитуды, тишина, изоляция каналов и баланс выделения/освобождения памяти. `--sanitize` включает AddressSanitizer и UndefinedBehaviorSanitizer; временные результаты сборки удаляются автоматически.

Исторические результаты проверок первой и повторной сборок, их SHA-256 и исправленные замечания review приведены в [отчёте первого APK](docs/reports/code-reviews/2026-10/CR-2026-10-17-miccontrol-first-apk.md). Это не результаты dev4; работа звонков на vivo/AirPods этим отчётом не подтверждена.

## Установка и проверка

Подключите телефон с включённой USB-отладкой, подтвердите доступ на экране телефона и выполните:

```bash
"$ANDROID_HOME/platform-tools/adb" devices
"$ANDROID_HOME/platform-tools/adb" install -r artifacts/Danygramm-arm64-dev4.apk
```

Либо перенесите готовый APK на телефон, откройте его в файловом менеджере и разрешите установку этому файловому менеджеру. При обновлении с прежней подписью удалять MicControl не нужно. После первого запуска разрешите доступ к микрофону и уведомлениям, затем добавьте аккаунт Telegram. Если код приходит в официальный Telegram, введите его вручную в Danygramm.

### Если код входа не приходит

Для личного аккаунта **выключите «Test Backend» / «Тестовый сервер»** на экране номера. Это отдельная среда Telegram: сообщения и аккаунты обычного Telegram там недоступны. Выбор сервера сохраняется после перезапуска; вернитесь к вводу номера и снимите галочку вручную.

Экран «Проверьте сообщения в Telegram» означает, что сервер выбрал доставку кода в служебный чат Telegram на уже авторизованных устройствах. Способ доставки выбирает сервер; приложение не может гарантировать переключение на SMS. См. [описание авторизации Telegram](https://core.telegram.org/api/auth).

В dev2 исправлена скрытая обработка ошибок запроса кода: отказ сервера теперь показывается диалогом. `API_ID_PUBLISHED_FLOOD` уже подтверждён при проверке dev2 в production; для такой ошибки нужна сборка со своими API credentials. Тестовый сервер не исправляет ограничение sample API.

## Выбор обработки микрофона

Во время **личного голосового или видеозвонка** нажмите кнопку **«Микрофон» внизу справа, над основными кнопками звонка**. Нижняя панель с вариантами **«Стандартный»** и **«Изоляция голоса»** открывается только по нажатию. Текущий вариант отмечен радиопереключателем и отдельным контрастным фоном. Нажатие на вариант сразу применяет его, закрывает панель и сохраняет выбор для следующих личных звонков.

«Стандартный» использует штатную обработку личных звонков Telegram и **не выключает микрофон**. «Изоляция голоса» добавляет RNNoise к исходящему звуку перед отправкой. Используется существующий выбор аудиоустройства Telegram: встроенный, проводной или Bluetooth-микрофон. Во входящем звонке до ответа, групповых звонках, конференциях и PiP кнопка режима скрыта. В группах и конференциях сохраняется штатная обработка Telegram.

Эта настройка работает внутри Danygramm и не переключает системные режимы AirPods или OriginOS. Режима Full Spectrum в первой версии нет.

Личный вход на dev3 подтверждён пользователем, обновление dev3 → dev4 проверено на эмуляторе. На vivo X200 Ultra отдельно проверьте личные голосовые и видеозвонки, выбранный Bluetooth-микрофон и сравните звук у собеседника при одинаковом фоне. Изменения обработки не могут восстановить частоты или детали, уже потерянные при передаче звука по Bluetooth.

## Ограничения первого варианта

- Firebase push и Google Maps не настроены: upstream dummy-конфигурация не используется. Своевременное получение фоновых звонков/уведомлений при ограничениях батареи требует отдельной проверки и настройки своего Firebase-проекта.
- Google Sign-in, passkeys, SMS Retriever с хешами официальной подписи и Google Play Billing отключены. Доступен обычный вход по номеру с ручным вводом кода; способы доставки кода определяет Telegram.
- Проверка обновлений официального Telegram отключена, включая ручной запрос из debug menu. Следующий APK устанавливается вручную с той же локальной подписью.
- Поддержка остальных архитектур, production-подпись и публикация в магазинах не входят в первый APK.

## Исходники и лицензия

Сохраняются [лицензия upstream](LICENSE) и уведомления об авторских правах. При распространении изменённого клиента нужно предоставлять соответствующие исходники по условиям GPL; требования к собственному API ID и названию также описаны в [upstream README](README.md).

Состояние задач и пути к изменениям: [tasks.md](tasks.md).
