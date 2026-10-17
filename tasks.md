# MicControl: первый APK

Все пункты отмечаются выполненными только после проверки результата.

Первый APK и отправка исходников завершены (`miccontrol-2c2`), но **работоспособность Telegram пока не подтверждена**: реальный вход в dev2 отклонён с `API_ID_PUBLISHED_FLOOD`. Исправление конфигурации и проверка успешного входа отслеживаются отдельно ниже.

- [x] `miccontrol-qxv` — **completed**: отдельный Android пакет, локальная подпись, сборка arm64 и инструкция; проверены manifest, подпись и содержимое APK.
  → Artifacts: [Gradle](gradle/miccontrol.gradle), [скрипт сборки](scripts/build-apk.sh), [инструкция](README_MICCONTROL_RU.md), [пример локальных настроек](local.properties.example), [иконка](TMessagesProj/src/main/res/drawable/miccontrol_launcher.xml).
- [x] `miccontrol-r98` — **completed**: управление обработкой микрофона в аудиозвонках, сохранение настроек и мост в WebRTC; сборка и native-тесты с ASan/UBSan прошли.
  → Artifacts: [экран звонка](TMessagesProj/src/main/java/org/telegram/ui/VoIPFragment.java), [сервис звонков](TMessagesProj/src/main/java/org/telegram/messenger/voip/VoIPService.java), [native bridge](TMessagesProj/jni/voip/org_telegram_messenger_voip_Instance.cpp).
- [x] **completed**: установить Android toolchain, собрать APK, проверить подпись/manifest/arm64 и сохранить результат; первая и повторная сборки успешны, SHA-256 совпал.
  → Artifacts: [APK](artifacts/MicControl-arm64-dev.apk), [SHA-256](artifacts/MicControl-arm64-dev.apk.sha256), [отчёт проверки](docs/reports/code-reviews/2026-10/CR-2026-10-17-miccontrol-first-apk.md).
- [x] `miccontrol-y9n` — **completed**: отключить вход через официальные OAuth/SMS-подписи, сохранить ручной ввод кода; изменения проверены в review и сборке.
  → Artifacts: [BuildVars](TMessagesProj/src/main/java/org/telegram/messenger/BuildVars.java), [экран входа](TMessagesProj/src/main/java/org/telegram/ui/LoginActivity.java).
- [x] `miccontrol-7f9` — **completed**: устранить утечку RNNoise при переключении режима; ошибка воспроизведена, исправление прошло ASan/UBSan и проверку счётчиков выделений.
  → Artifacts: [жизненный цикл RNNoise](TMessagesProj/jni/voip/miccontrol/VoiceIsolationDenoiser.cpp), [native-тесты](tests/miccontrol/voice_isolation_test.cpp).
- [ ] `miccontrol-usj` — **blocked**: 16 Android-проверок прошли на dev2 (20,155 с), включая production MTProto, но успешный вход они не проверяют. Пользователь подтвердил production-отказ `API_ID_PUBLISHED_FLOOD` скриншотом; нужны собственные API credentials и доступный авторизованный тестовый аккаунт. Переписка, файлы, поиск и сохранение сессии пока не проверены.
  → Artifacts: [Android-тесты](TMessagesProj_AppStandalone/src/androidTest/java/org/miccontrol/test), [запуск тестов](tests/miccontrol/ANDROID_RUNTIME_TESTS.md).
- [x] `miccontrol-6kp` — **completed**: исправлены скрытые ошибки `auth.sendCode`, включая RPC-код 406; воспроизведены пять падений на dev1, все 16 проверок прошли на dev2. Отмена и обработка посторонних запросов сохранены.
  → Artifacts: [обработка ошибок](TMessagesProj/src/main/java/org/telegram/ui/Components/AlertsCreator.java), [регрессионные тесты](TMessagesProj_AppStandalone/src/androidTest/java/org/miccontrol/test/MicControlLoginErrorsTest.java), [инструкция входа](README_MICCONTROL_RU.md), [отчёт dev2](docs/reports/code-reviews/2026-10/CR-2026-10-17-miccontrol-login.md).
- [x] `miccontrol-b4y` — **completed**: GitHub CLI авторизован как DV-Design, исходники успешно отправлены в `origin/main` (`8ea0d62`). Начальный commit пользователя сохранён; дерево исходников после переноса из shallow-клона совпало побайтно. Локальный ключ подписи сохранён в Actions Secret, ключи и APK в Git не добавлялись.
  → Artifacts: [исходники на GitHub](https://github.com/DV-Design/MicControl-Telegram), [описание исходного upstream](README_MICCONTROL_RU.md).
- [ ] `miccontrol-t4v` — **in_progress**: устранить подтверждённый отказ входа из-за sample API. Manual CI для dev3 подготовлен: обязательные собственные `api_id`/`api_hash` из GitHub Secrets, запрет sample API и проверка прежней подписи. Actionlint/ShellCheck, синтаксис и 11 отрицательных сценариев preflight прошли; основной агент независимо проверил код и 6 сценариев, включая восстановление правильного ключа. Новый APK ещё не собирался: собственные Telegram API credentials отсутствуют. Функциональный результат принимается только после успешного входа и проверки переписки.
  → Artifacts: [workflow](.github/workflows/build-apk.yml), [preflight](scripts/ci-preflight.py), [добавление API credentials](README_MICCONTROL_RU.md), [критерии функциональной проверки](tests/miccontrol/ANDROID_RUNTIME_TESTS.md).
- [ ] `miccontrol-6w0` — **open**: проверить личные звонки на vivo X200 Ultra с AirPods 3.
- [ ] `miccontrol-7vi` — **open**: настроить собственные API credentials, Firebase при необходимости и release-подпись перед повседневным использованием/распространением.

Проверка на vivo X200 Ultra (вход, обычный/видеозвонок, Bluetooth, переключение обработки микрофона) выполняется при наличии устройства; результат сборки сам по себе не подтверждает качество звука на телефоне.
