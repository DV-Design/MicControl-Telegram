# MicControl: первый APK

Все пункты отмечаются выполненными только после проверки результата.

Основная задача `miccontrol-2c2` остаётся **in_progress** до отправки исходников в репозиторий пользователя.

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
- [ ] `miccontrol-usj` — **in_progress**: тесты возобновлены по просьбе пользователя. Все восемь runtime-проверок прошли (6,594 с), включая реальный production MTProto-запрос; продолжается проверка входа и чатов в тестовой среде Telegram.
  → Artifacts: [Android-тесты](TMessagesProj_AppStandalone/src/androidTest/java/org/miccontrol/test), [запуск тестов](tests/miccontrol/ANDROID_RUNTIME_TESTS.md).
- [x] `miccontrol-6kp` — **completed**: исправлены скрытые ошибки `auth.sendCode`, включая HTTP/RPC-код 406; воспроизведены пять падений на dev1, все 16 проверок прошли на dev2. Отмена и обработка посторонних запросов сохранены.
  → Artifacts: [обработка ошибок](TMessagesProj/src/main/java/org/telegram/ui/Components/AlertsCreator.java), [регрессионные тесты](TMessagesProj_AppStandalone/src/androidTest/java/org/miccontrol/test/MicControlLoginErrorsTest.java), [инструкция входа](README_MICCONTROL_RU.md).
- [ ] `miccontrol-b4y` — **open**: отправить исходники в `DV-Design/MicControl-Telegram`; URL получен, но GitHub API возвращает 404 и Git-доступ отсутствует. Успешный push пока не выполнен.
- [ ] `miccontrol-6w0` — **open**: проверить личные звонки на vivo X200 Ultra с AirPods 3.
- [ ] `miccontrol-7vi` — **open**: настроить собственные API credentials, Firebase при необходимости и release-подпись перед повседневным использованием/распространением.

Проверка на vivo X200 Ultra (вход, обычный/видеозвонок, Bluetooth, переключение обработки микрофона) выполняется при наличии устройства; результат сборки сам по себе не подтверждает качество звука на телефоне.
