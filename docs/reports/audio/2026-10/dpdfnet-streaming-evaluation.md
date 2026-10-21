# DPDFNet 48 кГц: сильное подавление, неприемлемые потери начала речи

21 октября 2026. Проверены два официальных варианта, DPDFNet2-48HR и DPDFNet8-48HR. Код Danygramm 1.2, карты, ключи и интерфейс не менялись; Android и UI не запускались.

Оба варианта очень сильно подавили шум, но практически стёрли первые 100–200 мс двух чистых фраз. Это прямой отрицательный результат для требования сохранять речь. Полные 43-case прогоны остановлены после пяти заранее выбранных случаев на вариант: средняя таблица не исправит уже обнаруженный дефект. Более тяжёлая модель здесь не оказалась пригодной заменой.

## Закрепления и доступность

[Официальный исходник Ceva](https://github.com/ceva-ip/DPDFNet/tree/9bd9844a227bb6aa57e55588d8d0e961fcff1c46), commit `9bd9844a227bb6aa57e55588d8d0e961fcff1c46`, [Apache-2.0](https://github.com/ceva-ip/DPDFNet/blob/9bd9844a227bb6aa57e55588d8d0e961fcff1c46/LICENSE). Веса взяты из [официального HF](https://huggingface.co/Ceva-IP/DPDFNet/tree/dd6818d00f50c836fed43a6243ebe49116de5964), revision `dd6818d00f50c836fed43a6243ebe49116de5964`; model card явно указывает Apache-2.0. Веса и PCM не добавлены в Git.

| Официальный ONNX | Размер | SHA256 |
|---|---:|---|
| [DPDFNet2-48HR](https://huggingface.co/Ceva-IP/DPDFNet/resolve/dd6818d00f50c836fed43a6243ebe49116de5964/onnx/dpdfnet2_48khz_hr.onnx) | 10 493 337 B | `7f0575a5cec0ba4ffd8f8bd657e06d007e4ccdd955d76faab922b9d3291dc14b` |
| [DPDFNet8-48HR](https://huggingface.co/Ceva-IP/DPDFNet/resolve/dd6818d00f50c836fed43a6243ebe49116de5964/onnx/dpdfnet8_48khz_hr.onnx) | 14 857 107 B | `7b3afbb260a08fe9af3d16e3bda992971be1e7e951d1dee7c2d235f5c43f5631` |

Безопасно прочитаны соответствующие HF checkpoints через `torch.load(weights_only=True,map_location="cpu")`. Их SHA: 2HR `f4eb984dc80d66d6e417a8d6ad8855b4fd0b559452db1e68950f028234109d5c`; 8HR `7ade8f393e6b845a7f7e8e42b6c7cf169f6821e8489faf8f7fe0792b30482abe`. После официального `correct_state_dict` выполнен strict load: 613/853 исходных ключа, 2 582 907 / 3 633 531 параметр. На 12 последовательных спектральных кадрах сравнение с ONNX дало maxAbs выхода `1.26e-7 / 1.25e-7`, state `7.63e-6` для обоих. Нового экспорта, обучения и unsafe pickle не было. В официальном exporter имеется fallback к `weights_only=False`; этот путь не использовался.

Обнаружены две проблемы поставки:

- Sherpa release asset `dpdfnet2_48khz_hr.onnx`, SHA `0b399f8a58dc4d70d8cd97541f5c39869406145193b957d00a03b66070944928`, отличается от текущего HF checkpoint: на тех же 12 кадрах maxAbs выхода 0.0492, state 1.94. Его не использовали для PCM. Это разные поставки, а не побайтно одинаковый mirror.
- HF файл **8HR** имеет ошибочный metadata `profile=dpdfnet2_48khz_hr`. Размер state 90 228 и strict checkpoint parity подтверждают восемь блоков; 2HR имеет state 56 436. Asset оставлен неизменным, выбор проверяется полным SHA и state size. GitHub URL 8HR из Sherpa documentation вернул 404; официальный pinned HF URL доступен.

По [официальной таблице](https://github.com/ceva-ip/DPDFNet/blob/9bd9844a227bb6aa57e55588d8d0e961fcff1c46/README.md) 2HR требует 2.42 GMAC/s, 8HR — 7.17 GMAC/s. Это заявленные MAC, не телефонный benchmark. Сначала проверен более лёгкий вариант, затем flagship, чтобы сравнить и более мощную конфигурацию.

## Реальный потоковый путь

Использован готовый `sherpa_onnx.OnlineSpeechDenoiser` **1.13.8**, [официальная реализация DPDFNet](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/online-speech-denoiser-dpdfnet-impl.h). Модель получает спектр `[1,1,481,2]`, единый state `[56436]` или `[90228]`; возвращает спектр и следующий state. Native rate 48 кГц, FFT/window 960, hop 480, Vorbis window, opset 17. State инициализируется metadata normalization values и нулями остальных элементов; перед каждым независимым файлом вызывается reset.

Это причинная обработка с буферами; DPRNN bidirectional только по частоте, temporal GRU однонаправленный. В waveform-тракте есть дополнительные frame delays. Официальный streaming source содержит двухкадровый mask buffer и двухкадровый coefficient buffer. Фактически **одна clean A calibration** дала задержку **1920 samples / 40 мс** у обоих вариантов. Она снята одинаково со всех пяти выходов. На noisy inputs задержка не подбиралась. После этого общий scorer подтвердил lag 0. Первые 480 samples библиотека возвращает после двух входных hop, то есть 20 мс буферизации; это другая величина, чем 40 мс сдвига waveform. Фраза README о first output 20 мс не описывает всю задержку модели.

Передано по 480 normalized float samples / 10 мс, включая паузы. Добавлен только 100 мс zero-tail для drain, затем `flush`; исходная длина восстановлена фиксированным trim, все значения конечны. Нет PCM16 writer или нормализации выхода.

Использован **полный** шумодав. В online Sherpa `attenuation_limit_db=0`; [официальная документация](https://k2-fsa.github.io/sherpa/onnx/speech-enhancement/dpdfnet.html#offline-attenuation-limit) объясняет, что ограничитель вообще применяется только offline. Пример README с 12 дБ dry mix не является настройкой этого online прогона и не ограничивает его подавление.

Фактическая ORT внутри Sherpa wheel — **1.28.2**; отдельная Python ORT **1.31.0** используется только для spectral checkpoint parity. CPU session — один intra/inter thread. Через поддерживаемый Sherpa provider config реально переданы `session.intra_op.allow_spinning=0` и `session.inter_op.allow_spinning=0`; разбор конфигурации есть в логах. Нативная математика FFT/OLA и NN взята из библиотеки, новый neural inference engine не написан.

## Одинаковые PCM и результаты

Входы — неизменённый `artifacts/qa/gtcrn/matrix-43/inputs.json`, SHA `c4bca5c8a8bf23b654dd96ca180660aaae3fe5f3f19a85c90e0c4ba198a48877`. Взяты существующие `input48.f32` FloatS16 / 32768, без новой интерполяции. Это те же public LibriSpeech A/B и ESC vacuum/rain, паузы, общий input headroom и уровни, что в [GTCRN/DFN3 исследовании](gtcrn-streaming-evaluation.md). После фиксированного trim выполнен тот же Torch Kaiser 48→16. Все методы и reference оценены в одной полосе до 8 кГц; это не отдельная оценка исходной full-band речи.

[Общий scorer](../../../../tests/miccontrol/gtcrn_streaming_probe.py) получил минимальный `--case` фильтр и оценил те же пять случаев, без повторной RNNoise/GTCRN/DFN3 inference. SI-SDR и raw reference gain рассчитаны на одинаковых clean-defined масках. Onset 20/40/100/200 мс и post-burst recovery сохранены полностью. Низкий gain — подавление/искажение, не утверждение о packet dropout или субъективной разборчивости.

| Случай | SI-SDR RN / DFN3 / DPDF2 / DPDF8, дБ | Speech gain DPDF2 / DPDF8 |
|---|---:|---:|
| Clean A | 16.75 / 15.32 / 16.67 / 16.61 | 0.961 / 0.959 |
| Clean B | 13.59 / 28.76 / 21.93 / 22.22 | 0.968 / 0.964 |
| A + vacuum bursts | 2.65 / 5.70 / 10.40 / 12.19 | 0.904 / 0.918 |
| B + rain, −10 дБ SNR | −12.92 / 6.34 / 7.58 / 7.86 | 0.803 / 0.823 |

На noise-only vacuum attenuation: **RNNoise 45.19 дБ**, **DFN3 39.63 дБ**, **DPDF2 96.38 дБ**, **DPDF8 106.48 дБ**. В этих трудных условиях подавление фона у DPDFNet сильное; общий gain большей части фразы также высок.

Но начало речи провалено даже без шума:

| Первые 100 мс чистой фразы, raw gain | RNNoise 1.6 | GTCRN | DFN3 | DPDF2 | DPDF8 |
|---|---:|---:|---:|---:|---:|
| A | 0.687 | 0.967 | 0.033 | `7.49e-8` | `3.56e-6` |
| B | 0.510 | 0.853 | 0.178 | `1.50e-7` | `2.13e-6` |

У A reference RMS этих 100 мс **0.01698**, выход DPDF2 **2.07e-8**, DPDF8 **2.18e-7**; у B reference **0.01038**, выход **1.40e-8 / 1.03e-7**. Это практически исчезнувший участок, а не лишь низкий положительный gain из-за смены фазы. Первые 200 мс также сильно подавлены. После первого vacuum-burst у A gain первых 100 мс DPDF2 0.040, DPDF8 0.468; второй burst восстанавливается лучше. Причина потерь конкретного onset внутри модели/нормализации этим экспериментом не выделена; они не объясняются простым постоянным сдвигом.

## Время и Android

Функциональное host-время измерено вокруг каждого Sherpa `run`; construction исключён. На этом Mac ARM64, CPU one thread / no spinning:

| Вариант | p50 / p95 / p99 / worst блока, мс | RTF | Init отдельно |
|---|---:|---:|---:|
| DPDF2-48HR | 1.65 / 1.69 / 1.73 / 4.35 | 0.165 | 85.95 мс |
| DPDF8-48HR | 3.82 / 3.89 / 3.94 / 10.48 | 0.375 | 120.69 мс |

Это диагностический замер host library call, включая её DFT и обработку; общей тишины остальных host workloads не резервировали. Он не доказывает Android latency, battery или thermal stability. Нельзя назвать эту модель «самой мощной на рынке Android» только по числу параметров или этой таблице.

Официальный Sherpa static JNI/AAR содержит DPDFNet config; [Android feasibility](sherpa-android-1.13.8-static-feasibility.md) уже проверила API 23 symbol closure и 16 KiB ELF. Это не выполненный Android DPDF inference. Готовый полный bundle включает также TTS/eSpeak с отдельными лицензионными обязательствами; minSDK приложения не менялся. Из-за quality failure эти два варианта не переходят к продуктовой интеграции. APM NS/AGC/AEC, Bluetooth и телефон не проверялись; UI-тесты не запускались.

## Артефакты и воспроизведение

Скрипт [dpdfnet_streaming_probe.py](../../../../tests/miccontrol/dpdfnet_streaming_probe.py) проверяет pinned model/input SHA, запрещает перезапись raw-manifest, сохраняет raw 48 кГц и aligned 16 кГц float. Требуются существующие Torch и Sherpa venv; дополнительных пакетов и библиотек здесь не устанавливалось.

```bash
.local/tse-baseline-venv/bin/python tests/miccontrol/dpdfnet_streaming_probe.py --variant 2 --smoke --output-dir artifacts/research/dpdfnet/reproduction-2-new
.local/tse-baseline-venv/bin/python tests/miccontrol/dpdfnet_streaming_probe.py --variant 8 --smoke --output-dir artifacts/research/dpdfnet/reproduction-8-new
```

Модели заранее скачиваются по pinned HF URL из таблицы в `.local/target-voice/<model_name>-hf.onnx`. Доказательства: `artifacts/research/dpdfnet/{smoke-2hr,smoke-8hr-verified}/{raw-manifest.json,manifest.json}`, соответствующие логи; `dpdfnet{2,8}-safe-audit.json`, `dpdfnet{2,8}-torch-parity.npz`, `dpdfnet{2,8}-parity.json`. Начальный guard отказал mislabeled 8HR до inference; этот лог сохранён как `smoke-8hr.log`. Общая оценка пяти методов: `artifacts/qa/gtcrn/matrix-43/result-dpdfnet-smoke5.json`.

**Итог gate: оба default/full-suppression DPDFNet 48HR отклонены для текущей замены.** Параметры и dry mix после результата не подбирались. Отрицательный результат сохраняется; полные 43-case таблицы для этих вариантов не заявляются.
