# MicControl: первый APK

Все пункты отмечаются выполненными только после проверки результата.

Первый APK и отправка исходников завершены (`miccontrol-2c2`). 18 октября собран и опубликован dev3 с собственными API credentials и прежней подписью. **Успешный вход и переписка пока не подтверждены**: тестовый сервер отклонил документированный код и в приложении, и в независимом клиенте. Личный production-вход ожидает проверки пользователем.

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
- [ ] `miccontrol-usj` — **blocked**: dev3 установлен обновлением; собственная конфигурация подтверждена непосредственно из APK, запуск 2,620 с. Один реальный MTProto-тест прошёл за 1,817 с: `test_mode=true`, 9 endpoints. Запрос кода в TestDC2 принят, ввод документированного кода отклонён `PHONE_CODE_INVALID`; Telethon с теми же собственными API credentials воспроизвёл отказ. Переписка, файлы, поиск и сохранение авторизованной сессии не запускались. Исторические 16 проверок относятся к dev2.
  → Artifacts: [Android-тесты](TMessagesProj_AppStandalone/src/androidTest/java/org/miccontrol/test), [запуск тестов](tests/miccontrol/ANDROID_RUNTIME_TESTS.md).
- [x] `miccontrol-6kp` — **completed**: исправлены скрытые ошибки `auth.sendCode`, включая RPC-код 406; воспроизведены пять падений на dev1, все 16 проверок прошли на dev2. Отмена и обработка посторонних запросов сохранены.
  → Artifacts: [обработка ошибок](TMessagesProj/src/main/java/org/telegram/ui/Components/AlertsCreator.java), [регрессионные тесты](TMessagesProj_AppStandalone/src/androidTest/java/org/miccontrol/test/MicControlLoginErrorsTest.java), [инструкция входа](README_MICCONTROL_RU.md), [отчёт dev2](docs/reports/code-reviews/2026-10/CR-2026-10-17-miccontrol-login.md).
- [x] `miccontrol-b4y` — **completed**: GitHub CLI авторизован как DV-Design, исходники успешно отправлены в `origin/main` (`8ea0d62`). Начальный commit пользователя сохранён; дерево исходников после переноса из shallow-клона совпало побайтно. Локальный ключ подписи сохранён в Actions Secret, ключи и APK в Git не добавлялись.
  → Artifacts: [исходники на GitHub](https://github.com/DV-Design/MicControl-Telegram), [описание исходного upstream](README_MICCONTROL_RU.md).
- [ ] `miccontrol-t4v` — **blocked**: dev3 с добавленными пользователем API Secrets собран в CI (29 мин 13 с, 300 tasks) и опубликован. SHA-256, v1/v2, прежний сертификат, arm64/16 КиБ и полное скачивание из GitHub Release проверены. Sample API ID 4 отключён в фактическом APK. Тестовая авторизация остановлена на серверном отказе кода, воспроизведённом независимым клиентом; причина неизвестна. Пользователь получил APK и запрос на проверку личного production-входа с Test Backend OFF; ответ пока не получен.
  → Artifacts: [workflow](.github/workflows/build-apk.yml), [preflight](scripts/ci-preflight.py), [добавление API credentials](README_MICCONTROL_RU.md), [критерии функциональной проверки](tests/miccontrol/ANDROID_RUNTIME_TESTS.md).
  → Artifacts: [dev3 APK и SHA-256](https://github.com/DV-Design/MicControl-Telegram/releases/tag/miccontrol-dev3), [успешная CI-сборка](https://github.com/DV-Design/MicControl-Telegram/actions/runs/39156162098).
- [ ] `miccontrol-6w0` — **open**: проверить личные звонки на vivo X200 Ultra с AirPods 3.
- [ ] `miccontrol-7vi` — **open**: настроить собственные API credentials, Firebase при необходимости и release-подпись перед повседневным использованием/распространением.

Проверка на vivo X200 Ultra (вход, обычный/видеозвонок, Bluetooth, переключение обработки микрофона) выполняется при наличии устройства; результат сборки сам по себе не подтверждает качество звука на телефоне.
