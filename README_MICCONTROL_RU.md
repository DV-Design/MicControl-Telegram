# MicControl для Android

Экспериментальный неофициальный клиент на основе Telegram Android **13.0.2 (7175)**, исходный commit `f32ffeec763f0bdbf4bec25b52d654f77bff733d`. Первый вариант предназначен для проверки обработки микрофона в личных звонках на **vivo X200 Ultra / arm64-v8a**, включая гарнитуру AirPods 3.

Имя приложения — **MicControl**, Android application ID — **`org.miccontrol.messenger.web`**. У приложения своя иконка микрофона, тип системного аккаунта и локальная подпись. Его можно установить рядом с официальным клиентом. Аккаунт Telegram нужно добавить в MicControl отдельно.

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

Создайте в корне **`local.properties`** по примеру [local.properties.example](local.properties.example). Укажите свой `sdk.dir`, `TELEGRAM_API_ID` и `TELEGRAM_API_HASH`. Файл исключён из Git. Альтернативный способ — передать переменные окружения `TELEGRAM_API_ID` и `TELEGRAM_API_HASH`; окружение имеет приоритет.

Без своих credentials обычная сборка остановится с объяснением. Для первого тестового APK разрешён **явный** запуск с публичными sample-credentials upstream:

```bash
./scripts/build-apk.sh --allow-sample-api
```

Это developer sample API, а не собственные credentials MicControl. Telegram ограничивает его на сервере; вход может завершиться `API_ID_PUBLISHED_FLOOD`. Перед передачей приложения конечным пользователям нужны собственные `api_id`/`api_hash`. Значения попадают в APK, поэтому `api_hash` нельзя считать секретом, надёжно скрытым внутри приложения.

## Сборка APK

Из корня репозитория:

```bash
git submodule update --init --recursive --depth=1
./scripts/build-apk.sh
```

При отсутствии собственных API credentials используйте явно указанный выше `--allow-sample-api`. Скрипт создаёт `.local/miccontrol-debug.keystore`, собирает только **arm64-v8a** с двумя Gradle workers и heap 4 GB, проверяет подпись и сохраняет:

- `artifacts/MicControl-arm64-dev.apk`
- `artifacts/MicControl-arm64-dev.apk.sha256`

Исходный результат Gradle: `TMessagesProj_AppStandalone/build/outputs/apk/afat/debug/app.apk`. Вариант сборки — `AfatDebug`; приложение допускает отладку. Это тестовый APK, не подписанный production-ключом. Сохраните `.local/miccontrol-debug.keystore`, если хотите устанавливать следующие сборки как обновление без удаления приложения. При новой подписи Android потребует удалить прежнюю установку или использовать прежний ключ.

Для ручного запуска Gradle после создания локального ключа:

```bash
export MICCONTROL_ABIS=arm64-v8a
./gradlew :TMessagesProj_AppStandalone:assembleAfatDebug \
  --max-workers=2 --no-parallel --console=plain \
  '-Dorg.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g'
```

При необходимости sample API также явно задайте `MICCONTROL_ALLOW_SAMPLE_API=true` в окружении. `.local/`, `local.properties`, `artifacts/` и файлы APK исключены из Git. Upstream dummy `release.keystore` не используется для debug APK; release/публикация требуют отдельной настройки production-подписи.

## Native-тесты

Для проверки аудиообработки на компьютере нужны Python 3 и Clang/Clang++:

```bash
python3 tests/miccontrol/run_native_tests.py --sanitize
```

Тесты компилируют включённые в проект RNNoise и WebRTC sinc resampler. Проверяются mono/stereo при 8/16/32/48 кГц, точный bypass в режиме «Стандартный», 50 переключений на каждой частоте, конечность и допустимый диапазон амплитуды, тишина, изоляция каналов и баланс выделения/освобождения памяти. `--sanitize` включает AddressSanitizer и UndefinedBehaviorSanitizer; временные результаты сборки удаляются автоматически.

Проверки исходников и APK прошли; физические звонки на vivo/AirPods ещё не проверены. Результаты первой и повторной сборок, SHA-256 и исправленные замечания review приведены в [отчёте первого APK](docs/reports/code-reviews/2026-10/CR-2026-10-17-miccontrol-first-apk.md).

## Установка и проверка

Подключите телефон с включённой USB-отладкой, подтвердите доступ на экране телефона и выполните:

```bash
"$ANDROID_HOME/platform-tools/adb" devices
"$ANDROID_HOME/platform-tools/adb" install -r artifacts/MicControl-arm64-dev.apk
```

Либо перенесите APK на телефон, откройте его в файловом менеджере и разрешите установку этому файловому менеджеру. После запуска разрешите доступ к микрофону и уведомлениям, затем добавьте аккаунт Telegram. Если код приходит в официальный Telegram, введите его вручную в MicControl.

### Если код входа не приходит

Для личного аккаунта **выключите «Test Backend» / «Тестовый сервер»** на экране номера. Это отдельная среда Telegram: сообщения и аккаунты обычного Telegram там недоступны. Выбор сервера сохраняется после перезапуска; вернитесь к вводу номера и снимите галочку вручную.

Экран «Проверьте сообщения в Telegram» означает, что сервер выбрал доставку кода в служебный чат Telegram на уже авторизованных устройствах. Способ доставки выбирает сервер; приложение не может гарантировать переключение на SMS. См. [описание авторизации Telegram](https://core.telegram.org/api/auth).

В dev2 исправлена скрытая обработка ошибок запроса кода: отказ сервера теперь показывается диалогом. Например, `API_ID_PUBLISHED_FLOOD` означает ограничение публичного sample API; для такой ошибки нужна сборка со своими API credentials, а не включение тестового сервера. Подтверждение этого отказа для конкретного аккаунта требует фактического ответа сервера.

## Выбор обработки микрофона

Откройте **личный голосовой или видеозвонок** и нажмите кнопку **«Микрофон: Стандартный»** под статусом звонка/таймером. В диалоге доступны **«Стандартный»** и **«Изоляция голоса»**. Выбор применяется сразу, отмечается галочкой и сохраняется для следующих личных звонков.

«Стандартный» использует штатную обработку личных звонков Telegram. «Изоляция голоса» добавляет RNNoise к исходящему звуку перед отправкой. Используется существующий выбор аудиоустройства Telegram: встроенный, проводной или Bluetooth-микрофон. В групповых звонках и конференциях кнопка скрыта, сохраняется штатная обработка Telegram.

Эта настройка работает внутри MicControl и не переключает системные режимы AirPods или OriginOS. Режима Full Spectrum в первой версии нет.

Проверка сборки и подписи не заменяет проверку на устройстве. На vivo X200 Ultra нужно отдельно проверить вход, личные голосовые и видеозвонки, выбранный Bluetooth-микрофон и сравнить звук у собеседника при одинаковом фоне. Изменения обработки не могут восстановить частоты или детали, уже потерянные при передаче звука по Bluetooth.

## Ограничения первого варианта

- Firebase push и Google Maps не настроены: upstream dummy-конфигурация не используется. Своевременное получение фоновых звонков/уведомлений при ограничениях батареи требует отдельной проверки и настройки своего Firebase-проекта.
- Google Sign-in, passkeys, SMS Retriever с хешами официальной подписи и Google Play Billing отключены. Доступен обычный вход по номеру с ручным вводом кода; способы доставки кода определяет Telegram.
- Проверка обновлений официального Telegram отключена, включая ручной запрос из debug menu. Следующий APK устанавливается вручную с той же локальной подписью.
- Поддержка остальных архитектур, production-подпись и публикация в магазинах не входят в первый APK.

## Исходники и лицензия

Сохраняются [лицензия upstream](LICENSE) и уведомления об авторских правах. При распространении изменённого клиента нужно предоставлять соответствующие исходники по условиям GPL; требования к собственному API ID и названию также описаны в [upstream README](README.md).

Состояние задач и пути к изменениям: [tasks.md](tasks.md).
