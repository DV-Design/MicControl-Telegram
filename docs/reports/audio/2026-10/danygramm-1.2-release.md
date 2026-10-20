# Danygramm 1.2: карты и основа для следующих изменений звука

20 октября 2026. Опубликованы [предварительный релиз 1.2](https://github.com/DV-Design/MicControl-Telegram/releases/tag/danygramm-1.2) и [APK для arm64](https://github.com/DV-Design/MicControl-Telegram/releases/download/danygramm-1.2/Danygramm-arm64.apk).

Исходники: `1adbb1d8af08e4849da9cdc40e5a941a46d97a7f`. Файл получен из [успешной CI-сборки 39420257389](https://github.com/DV-Design/MicControl-Telegram/actions/runs/39420257389).

- Пакет `org.miccontrol.messenger.web`, версия `13.0.2-danygramm-1.2`, code `71819`, отладка выключена.
- APK: 58 298 398 байт, SHA-256 `5b88981df7fd835539a8885d048cbaf57b3dc46f3c45e5d8aceef964e9976d42`.
- Прежний сертификат: SHA-256 `59e104c1d8b66e20c47119aed387993df655475cdd3153fb21bfb3752d85debe`, SHA-1 `47b997830c0498bf3d4d618a3955fbca1d280e69`. Подписи v1/v2 проверены.
- Android min 23 / target 36, три библиотеки arm64 с ELF LOAD 16 КиБ. Прототипы TSE и ONNX/ORT-модели в APK не включены.
- Собственная конфигурация Telegram API совпадает с проверенной 1.0; sample/debug-флаги выключены. Значения API сравнивались в памяти.
- Metadata `com.google.android.geo.API_KEY` находится непосредственно в `application`. Хеш ключа совпал с CI proof для этого APK и source commit. Значение ключа в отчёты не выводилось.
- Опубликованный APK полностью скачан без авторизации. Размер, SHA-256, checksum и update JSON совпали с CI-артефактом; перенаправление скачивания ведёт на `release-assets.githubusercontent.com`.
- Релиз отмечен prerelease. Стабильный `/releases/latest` и автоматическое обновление остаются на 1.0.

Статическая проверка APK прошла независимо от сборочного скрипта. UI, adb и AndroidTest для 1.2 не запускались по просьбе пользователя. Пользователь 20 октября подтвердил рабочие карты на телефоне; это отдельное физическое подтверждение, а не результат автоматического теста. [Статический аудит карт](../../code-reviews/2026-10/CR-2026-10-20-google-maps.md).

Обработка звука осталась как в 1.1, с коэффициентом спектрального подавления RNNoise 1,6. Пользователь сообщил, что на громком фоне шум остаётся, а речь прерывается. Исправление ведётся отдельно в `miccontrol-8sd`, на основе рабочей 1.2 с картами. Версия 1.2 не содержит исправления этой проблемы. [Измерения RNNoise 1.1 и ограничения](ambient-noise-spectral-evaluation.md).

Доказательства: `artifacts/qa/maps-1.2/ci-39420257389/`,
`artifacts/qa/maps-1.2/ci-independent/candidate.json`,
`artifacts/qa/1.2-candidate.json`,
`artifacts/qa/1.2-public-download/verified.json`.
