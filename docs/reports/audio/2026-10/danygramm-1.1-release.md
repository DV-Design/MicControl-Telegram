# Danygramm 1.1: опубликованная пробная сборка

20 октября 2026. [Предварительный релиз](https://github.com/DV-Design/MicControl-Telegram/releases/tag/danygramm-1.1)
и [прямое скачивание APK](https://github.com/DV-Design/MicControl-Telegram/releases/download/danygramm-1.1/Danygramm-arm64.apk)
проверены полным анонимным скачиванием. Исходники:
`b02cb2172140f1d931fa0bbdac105da9b250c7cf`.

- Пакет `org.miccontrol.messenger.web`, версия `13.0.2-danygramm-1.1`, code `71809`.
- APK: 58 298 300 байт, SHA-256 `06d0f2043070a1fe92bf49ed1d7a269885b535fbb4f8977550d679bc954c1a3c`.
- Прежний сертификат: `59e104c1d8b66e20c47119aed387993df655475cdd3153fb21bfb3752d85debe`, подписи v1/v2 проверены.
- Android min 23 / target 36, три библиотеки arm64 с ELF LOAD 16 КиБ. Изменённые аудиофайлы перекомпилированы, `libtmessages` отличается от 1.0.
- Собственная API-конфигурация совпадает со стабильной 1.0, sample/debug-флаги выключены. Прототипы TSE и ONNX-модели в APK не включены.
- Опубликованные APK, SHA-файл и update JSON совпали с локальными. GitHub сообщает тот же digest; перенаправление скачивания — `release-assets.githubusercontent.com`.
- Релиз помечен prerelease; стабильный `/releases/latest` по-прежнему возвращает 1.0.

Изменён коэффициент спектрального подавления RNNoise: 1.3 → 1.6. Девять
реальных PCM-сценариев, сохранение legacy-выходов, native ASan/UBSan и 400
переключений прошли. [Аудиоизмерения и ограничения](ambient-noise-spectral-evaluation.md):
шум тише, но отдельные тихие начала слов ослабляются. Прослушивание и физический
звонок остаются задачей `miccontrol-6w0`. UI, adb и AndroidTest этой версии не
запускались по просьбе пользователя.

Доказательства: `artifacts/qa/1.1-candidate.json`, `1.1-build.log`,
`1.1-native-build-evidence.json`, `1.1-public-download/verified.json`.
