# Danygramm: APK и проверки

Все пункты отмечаются выполненными только после проверки результата.

## Текущая работа: основа, три режима и перевод на экране

- [x] `miccontrol-bn0` — **completed**: фоновое соединение и настройки уведомлений, подписанная сборка без debug, проверка и установка обновлений из GitHub Releases с сохранением пакета и сертификата.
  → Artifacts: [обновления](TMessagesProj/src/main/java/org/telegram/messenger/DanygrammUpdater.java), [служба](TMessagesProj/src/main/java/org/telegram/messenger/NotificationsService.java), [релиз 1.0](https://github.com/DV-Design/MicControl-Telegram/releases/tag/danygramm-1.0), [28 проверок](tests/miccontrol/ANDROID_RUNTIME_TESTS.md).
- [x] `miccontrol-1ir` — **completed**: три режима микрофона — изоляция голоса, шумоподавление, без эффектов; миграция настроек и проверка реальной обработки.
  → Artifacts: [обработка микрофона](TMessagesProj/jni/voip/miccontrol/VoiceIsolationProcessor.cpp), [меню](TMessagesProj/src/main/java/org/telegram/ui/Components/voip/MicrophoneModeSheet.java), [проверки](tests/miccontrol/ANDROID_RUNTIME_TESTS.md).
- [x] `miccontrol-9ci` — **completed**: локальный перевод входящих сообщений и подписей на экране чата, выбор языка и возврат оригинала. Исходящие сообщения сохраняются без изменений.
  → Artifacts: [локальный перевод](TMessagesProj/src/main/java/org/telegram/messenger/LocalChatTranslation.java), [чат](TMessagesProj/src/main/java/org/telegram/ui/ChatActivity.java), [проверки](tests/miccontrol/ANDROID_RUNTIME_TESTS.md).
- [x] `miccontrol-agy` — **completed**: подтверждён бумажный самолётик в стиле Telegram с маленькими красными звёздами на крыльях; согласовать launcher и уведомления.
  → Artifacts: [самолётик](TMessagesProj/src/main/res/drawable/danygramm_plane.xml), [иконка уведомлений](TMessagesProj/src/main/res/drawable/danygramm_notification.xml), [отчёт](docs/reports/code-reviews/2026-10/CR-2026-10-19-danygramm-1.0.md).

## Следующая задача после релиза 1.0

- [ ] `miccontrol-adn` — **in_progress**: выделять именно голос владельца, в том числе при чужой речи рядом. RNNoise эту задачу не решает. Исследуется потоковое нейросетевое выделение целевого говорящего; прототип пока не включён в приложение.
- [x] `miccontrol-ulk` — **completed**: диагностический C++-прототип, 3/3 точных Mac golden, ASan/UBSan/reset/flush/lifetime, реальный native Android arm64/16 КиБ, проверка 1/2/4 потоков, выноса неизменных вычислений и длинной регистрации. Исследование воспроизводится; этот результат не означает готовность owner-only режима.
  → Artifacts: [native](TMessagesProj/jni/voip/miccontrol/TargetVoiceInference.cpp), [методика](tests/miccontrol/TARGET_VOICE_TESTS.md), [измерения и отрицательные случаи](docs/reports/audio/2026-10/target-voice-model-evaluation.md).
- [ ] `miccontrol-m1b` — **in_progress**: VoxLock с некоторыми образцами пропускает чужой голос при отсутствии владельца и выбирает чужого говорящего при наложении речи. Проверяется причина, точность модели и независимая проверка говорящего; это препятствует включению owner-only режима в APK.
  → Artifacts: [проект настройки голоса](docs/reports/audio/2026-10/target-voice-enrollment-design.md).
- [ ] `miccontrol-wse` — **in_progress**: проверить отдельную causal WeSep модель с глобальным speaker embedding вместо TF-map/context; сначала реальные отрицательные случаи, затем решение об экспорте и интеграции.
- [ ] `miccontrol-1i8` — **in_progress**: подготовить отдельный диагностический APK с публичной тестовой записью для измерения на vivo; без аккаунта Telegram, микрофона, сети и изменения основного приложения.

## Выполнено ранее и отдельные проверки устройства

Первый APK и отправка исходников завершены (`miccontrol-2c2`). 18 октября пользователь подтвердил, что dev3 работает; проблема личного входа с sample API закрыта. 19 октября выпущен Danygramm dev4 с новым меню микрофона и иконкой истребителя. Сборка, обновление без сброса данных, пять целевых проверок и полное скачивание APK подтверждены. Переписка/файлы и качество реальных звонков остаются в прежнем объёме без новых утверждений.

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
- [x] `miccontrol-t4v` — **completed**: dev3 с добавленными пользователем API Secrets собран в CI и опубликован. SHA-256, v1/v2, прежний сертификат, arm64/16 КиБ и полное скачивание из GitHub Release проверены. Sample API ID 4 отключён в фактическом APK. Пользователь сообщил «Работает» 18 октября, подтвердив исправление личного входа; исторический отказ кодов TestDC не считается результатом production-входа.
  → Artifacts: [workflow](.github/workflows/build-apk.yml), [preflight](scripts/ci-preflight.py), [добавление API credentials](README_MICCONTROL_RU.md), [критерии функциональной проверки](tests/miccontrol/ANDROID_RUNTIME_TESTS.md).
  → Artifacts: [dev3 APK и SHA-256](https://github.com/DV-Design/MicControl-Telegram/releases/tag/miccontrol-dev3), [успешная CI-сборка](https://github.com/DV-Design/MicControl-Telegram/actions/runs/39156162098).
- [ ] `miccontrol-6w0` — **open**: проверить личные звонки на vivo X200 Ultra с AirPods 3, включая расположение кнопки, скрытие/показ управления, PiP и качество звука.
- [x] `miccontrol-7vi` — **completed**: собственные API, прежняя подпись, non-debug/logging и фоновое соединение проверены в релизе 1.0; для выбранного native MTProto способа свой Firebase не нужен. Остальные отключённые интеграции перечислены в README, физическая проверка остаётся в `miccontrol-6w0`.
- [x] `miccontrol-bx8` — **completed**: кнопка «Микрофон» перенесена вниз справа, режимы открываются нижней панелью по нажатию. Четыре проверки реальных компонентов прошли за 6,867 с: обе темы и оба состояния, минимальный контраст 5,77:1, нажатия, радиовыбор, доступность и закрытие. Интеграция в экран звонка проверена по исходникам; живой звонок остаётся в `miccontrol-6w0`.
  → Artifacts: [экран звонка](TMessagesProj/src/main/java/org/telegram/ui/VoIPFragment.java), [нижняя панель](TMessagesProj/src/main/java/org/telegram/ui/Components/voip/MicrophoneModeSheet.java), [четыре UI-теста](TMessagesProj_AppStandalone/src/androidTest/java/org/miccontrol/test/MicControlMicrophoneModeSheetTest.java), [результаты и ограничения](tests/miccontrol/ANDROID_RUNTIME_TESTS.md).
- [x] `miccontrol-a2j` — **completed**: имя Danygramm во всех 10 standalone-локалях; собственный белый истребитель на голубом фоне, legacy/adaptive/monochrome. Фактический launcher и installed metadata проверены. Dev4 установлен поверх dev3 без сброса данных; пакет, подпись и собственная API-конфигурация сохранены. APK опубликован, полностью скачан повторно; размер и SHA-256 совпали.
  → Artifacts: [SVG иконки](TMessagesProj_AppStandalone/branding/danygramm-icon.svg), [legacy-иконка](TMessagesProj/src/main/res/drawable/miccontrol_launcher.xml), [manifest](TMessagesProj/config/release/AndroidManifest_standalone.xml), [APK и SHA-256](https://github.com/DV-Design/MicControl-Telegram/releases/tag/danygramm-dev4), [исходники dev4](https://github.com/DV-Design/MicControl-Telegram/commit/88e1822557ba78eb6cd928f1751a19e961752fb5).

Проверка на vivo X200 Ultra (вход, обычный/видеозвонок, Bluetooth, переключение обработки микрофона) выполняется при наличии устройства; результат сборки сам по себе не подтверждает качество звука на телефоне.

- [x] `miccontrol-vnu` — **completed**: главный README описывает официальные исходники Telegram Android как основу Danygramm и изоляцию голоса как единственную добавленную пользовательскую функцию. Уточнён статус неофициальной сборки, сохранены ссылки на upstream commit, лицензию и технические особенности. Формулировки, локальные ссылки, якорь и whitespace проверены; APK не менялся.
  → Artifacts: [главный README](README.md), [подробности сборки](README_MICCONTROL_RU.md).
