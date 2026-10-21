# DeepFilterNet и DTLN: альтернативы шумоподавления

20 октября 2026, `miccontrol-8sd`. Исследование официальных исходников и готовых
моделей; продукт не изменён. **DeepFilterNet3 — реальная full-band альтернатива,
но штатный вариант не рекомендован к немедленной замене RNNoise:** последующее
сравнение 43 PCM улучшило многие общие метрики, одновременно обнаружив сильное
ослабление некоторых начал речи. У DTLN выполнен только функциональный smoke.
Android, телефон, звонки и UI этим этапом не запускались.

## Сначала проверить существующую цепочку

В [VoiceIsolationProcessor.cpp](../../../../TMessagesProj/jni/voip/miccontrol/VoiceIsolationProcessor.cpp)
оба режима обработки включают WebRTC NS `kHigh`, HPF и AGC1 `kFixedDigital`;
AGC2 выключен. В поставляемом APM `kHigh` соответствует уровню `k18dB`.
Реальный порядок в
[audio_processing_impl.cc](../../../../TMessagesProj/jni/voip/webrtc/modules/audio_processing/audio_processing_impl.cc)
— NS/AEC около строк 1648–1672, AGC1 около 1686, затем `capture_post_processor`
около 1768. Следовательно, RNNoise получает уже обработанный сигнал.
Из этого **не следует**, что обрывы вызваны APM: причинная связь не проверена.

В [VoiceIsolationDenoiser.cpp](../../../../TMessagesProj/jni/voip/miccontrol/VoiceIsolationDenoiser.cpp)
добавляется RNNoise с показателем спектрального ослабления 1.6. Существующая
[оценка](ambient-noise-spectral-evaluation.md) измеряла RNNoise и его обёртку,
не всю цепочку APM; там уже отмечено дополнительное ослабление слабых начал речи.
Новой сети нельзя автоматически оставлять два последовательных NS и считать
результат проверкой одной модели. Нужна общая A/B-абляция NS и AGC по отдельности,
с сохранением AEC, одинаковыми PCM, уровнями, задержкой и метриками согласных.
В этом исследовании такая абляция не выполнялась.

## Что действительно доступно

| Параметр | DeepFilterNet3 | DTLN |
| --- | --- | --- |
| Закреплённый исходник | [`d375b2d`](https://github.com/Rikorose/DeepFilterNet/tree/d375b2d8309e0935d165700c91da9de862a99c31), 17.10.2024 | [`1de1f15`](https://github.com/breizhn/DTLN/tree/1de1f15a8b5b7e1c44905618ff2ef70ca8277fbc), 26.04.2022 |
| Готовая модель | Три ONNX-сети и config, официальный `DeepFilterNet3_onnx.tar.gz` | Официальные `model_1.onnx` + `model_2.onnx`; также FP32 и quantized TFLite |
| Размер | Архив 7 983 136 байт; распакованное содержимое 8 589 309 байт | ONNX вместе 3 968 247 байт; quantized TFLite вместе 1 027 232 байта |
| Частота | 48 кГц | Только 16 кГц; другой режим требует переобучения |
| Потоковый шаг | 480 отсчётов / 10 мс | 128 отсчётов / 8 мс |
| Задержка | 30 мс по формуле официального CLI: `(960−480)+2×480`; это задержка отсчётов, без Android I/O | Автор указывает 32 мс вход–выход при окне 512 и шаге 128; пример имеет 384 отсчёта начального сдвига плюс сбор очередного блока |
| Готовый нативный путь | Rust `libDF` + Tract, существующий C API обработки PCM | Два вызова ORT или LiteRT, внешние FFT/IFFT, LSTM states и overlap-add |

DFN3 имеет ограниченный lookahead: это потоковая обработка с буферизацией, а не
сеть с нулевым просмотром вперёд. Формула задержки и состояние находятся в
[официальном CLI](https://github.com/Rikorose/DeepFilterNet/blob/d375b2d8309e0935d165700c91da9de862a99c31/libDF/src/bin/enhance_wav.rs)
и [Tract runtime](https://github.com/Rikorose/DeepFilterNet/blob/d375b2d8309e0935d165700c91da9de862a99c31/libDF/src/tract.rs).
Отдельная готовая low-latency модель действительно имеет нулевой lookahead,
но это **другие веса**, архив 36 359 660 байт; её качество и исполнение здесь
не проверялись. У DTLN официальный
[ONNX-пример](https://github.com/breizhn/DTLN/blob/1de1f15a8b5b7e1c44905618ff2ef70ca8277fbc/real_time_processing_onnx.py)
возвращает LSTM states обратно во вход на каждом шаге. Не требуется обучать
или заново экспортировать модель для первого CPU-прототипа.

Полные SHA-256 загруженных файлов сохранены в ignored
`artifacts/research/neural-denoisers/deepfilter-models.json` и `dtln-models.json`.
Ключевые закрепления:

| Файл | SHA-256 |
| --- | --- |
| [DFN3 ONNX archive](https://github.com/Rikorose/DeepFilterNet/blob/d375b2d8309e0935d165700c91da9de862a99c31/models/DeepFilterNet3_onnx.tar.gz) | `c94d91f70911001c946e0fabb4aa9adc37045f45a03b56008cb0c8244cb63616` |
| [DTLN model_1.onnx](https://github.com/breizhn/DTLN/blob/1de1f15a8b5b7e1c44905618ff2ef70ca8277fbc/pretrained_model/model_1.onnx) | `22b91cae3855e5a0620e66a917ca6c82c58db0e842c770f58d86751c5e8d4ae3` |
| [DTLN model_2.onnx](https://github.com/breizhn/DTLN/blob/1de1f15a8b5b7e1c44905618ff2ef70ca8277fbc/pretrained_model/model_2.onnx) | `e20c92f9233fccf29cddf86970d0d0161a03aebccc26d6f4d5639c4d5ec2e639` |

## Лицензии

Код DeepFilterNet позволяет выбрать MIT или Apache-2.0:
[LICENSE](https://github.com/Rikorose/DeepFilterNet/blob/d375b2d8309e0935d165700c91da9de862a99c31/LICENSE).
Авторы [статьи DFN3](https://arxiv.org/abs/2305.08227) прямо называют framework
и pretrained weights открытыми. Веса находятся в том же официальном репозитории;
в проверенных ZIP/tar нет отдельного LICENSE или дополнительных условий для весов.
Отдельного model card с иным разрешением не найдено. Это точная граница проверки;
нельзя приписывать весам отдельную лицензию, которой автор не указал.

У DTLN [LICENSE MIT](https://github.com/breizhn/DTLN/blob/1de1f15a8b5b7e1c44905618ff2ef70ca8277fbc/LICENSE),
а README явно предоставляет pretrained модели как базу для других проектов.
Отдельных условий или отдельного LICENSE внутри `pretrained_model` не найдено.
При распространении нужно сохранить upstream notices; нового лицензионного
соглашения или коммерческого сервиса для локального smoke не потребовалось.

## Android: доказанное и ещё не проверенное

У DFN3 есть
[C API](https://github.com/Rikorose/DeepFilterNet/blob/d375b2d8309e0935d165700c91da9de862a99c31/libDF/src/capi.rs)
`df_create` / `df_get_frame_length` / `df_process_frame`. Модель открывается
до обработки, PCM передаётся через указатели. Это реальный путь к C++ capture,
но официальный [release v0.5.6](https://github.com/Rikorose/DeepFilterNet/releases/tag/v0.5.6)
не содержит Android AAR или Bionic `.so`: ARM64 Linux GNU не является Android.
У [матрицы сборки C API](https://github.com/Rikorose/DeepFilterNet/blob/d375b2d8309e0935d165700c91da9de862a99c31/.github/workflows/build_capi.yml)
также нет Android. Поэтому minSdk 23, размер Android runtime, ELF 16 КБ и скорость
на vivo пока **не доказаны**. Потребуются отдельная Rust/NDK-сборка, проверка ELF
и bounded worker; отсутствие выделений памяти на capture из C API не следует.

Для DTLN проверены настоящие официальные Google Maven AAR:

| Runtime | Минимальный API в AAR | ARM64 библиотека, raw / compressed | ELF LOAD |
| --- | ---: | ---: | --- |
| [LiteRT 1.4.2](https://dl.google.com/dl/android/maven2/com/google/ai/edge/litert/litert/1.4.2/litert-1.4.2.aar), Interpreter | 21, подходит существующему min23 | 4 475 256 / 1 820 761 байт | Все сегменты 16 384 |
| [LiteRT 2.3.0](https://dl.google.com/dl/android/maven2/com/google/ai/edge/litert/litert/2.3.0/litert-2.3.0.aar), актуальный release по Maven metadata | 24 | 5 629 696 / 2 338 001 байт | Все сегменты 16 384 |

Это совместимость бинарного runtime, **не выполненный Android-инференс DTLN**.
AAR не содержат Prefab; у проверенного JNI `.so` 1.4.2 нет экспортированных
`TfLiteModelCreate` / `TfLiteInterpreterCreate`. Для прямого C API понадобятся
отдельные headers/library; Java Interpreter допустим на worker, не на callback
захвата. Другой реальный путь — уже исследованный ORT C API 1.31, который требует
min24. Новые Gradle-зависимости в приложение не добавлялись.
Доказательства размеров, SHA и `llvm-readelf`:
`artifacts/research/neural-denoisers/litert-aar.json`, `litert-api-symbols.json`.

DFN3 [публикует RTF 0.19](https://arxiv.org/abs/2305.08227) на одном потоке
notebook CPU. У [DTLN](https://github.com/breizhn/DTLN/blob/1de1f15a8b5b7e1c44905618ff2ef70ca8277fbc/README.md#execution-times)
quantized TFLite занимает 2.2 мс на Raspberry Pi 3 B+ против бюджета 8 мс;
FP32 там же — 9.6 мс. Ни одна из цифр не подтверждает Android, Bluetooth,
температуру или расход батареи. Размер desktop CLI тоже не является размером
библиотеки, которую получит APK.

## Выполненный PCM smoke и следующий gate

Обе официальные модели успешно обработали **три записи по 6 секунд**: чистую A,
A с дождём и только дождь, из тех же закреплённых public fixtures. Во всех шести
выходах проверены точная длина и конечные отсчёты. Нормализации выхода нет.
DFN3: официальный Mac ARM64 CLI v0.5.6, явный закреплённый ONNX archive,
отдельный процесс для каждого файла, postfilter выключен, добавлен нулевой хвост
и применена штатная компенсация 30 мс; его WAV writer сохраняет PCM16.
DTLN: официальный split-state алгоритм, ORT 1.31 CPU с одним потоком,
SoXR VHQ 48→16 кГц, сброс states между файлами и явный zero-tail flush.

Репродуктор `.tmp/current/smoke-neural-denoisers.py`, отдельная среда
`.local/denoiser-research-venv`, результат
`artifacts/research/neural-denoisers/smoke/result.json`. Исходники, модели и PCM
остаются ignored. В JSON есть диагностическое host wall time; оно не используется
как телефонный benchmark. **SI-SDR, начала согласных, dropout и прослушивание
этим smoke не оценивались; RMS не доказывает сохранение речи.**

В Rust runtime действительно есть
[`apply_stages`](https://github.com/Rikorose/DeepFilterNet/blob/d375b2d8309e0935d165700c91da9de862a99c31/libDF/src/tract.rs)
с нулевой маской при `lsnr < −15`. Однако **это не объяснение наблюдавшихся
потерь речи**: в закреплённом `enc.onnx` проверена фактическая цепочка
`Sigmoid → Mul(50) → Add(−15)`, диапазон LSNR `[-15, 35]`.
При корректных конечных вычислениях строгая граница `< −15` недостижима.
То же выражение есть в
[deepfilternet3.py](https://github.com/Rikorose/DeepFilterNet/blob/d375b2d8309e0935d165700c91da9de862a99c31/DeepFilterNet/df/deepfilternet3.py).
Статический разбор сохранён в `artifacts/research/neural-denoisers/dfn3-lsnr-graph.json`.
Порог не менялся; причину конкретных потерь onset этот этап не выделяет.

## Последующий общий прогон: те же 43 PCM

Выполнены 3 clean, 27 смесей трёх голосов и трёх шумов при SNR +10/0/−10 дБ,
9 loud-burst, 3 только-шум и тишина. Входной manifest GTCRN закреплён SHA-256
`c4bca5c8a8bf23b654dd96ca180660aaae3fe5f3f19a85c90e0c4ba198a48877`.
Общая reference — 16 кГц / полоса 8 кГц: это сравнение на одинаковой полосе,
не отдельная оценка качества исходной full-band записи 48 кГц.

[dfn3_matrix_probe.py](../../../../tests/miccontrol/dfn3_matrix_probe.py) читает
уже готовый `<case>-input48.f32` RNNoise, делит FloatS16 на 32768 и сохраняет
FLOAT WAV без нового пересчёта 16→48 кГц. Отдельный процесс CLI для каждого
файла сбрасывает состояние. После `-D` снимается фиксированная задержка 1440
отсчётов; удаляется только явное terminal-hop padding. Обратный 48→16 — тот же
Torchaudio Kaiser: width 64, rolloff `0.9475937167399596`, beta
`14.769656459379492`. Никакой нормализации или подбора задержки по шумной записи.
Все 43 выхода имеют точную длину и конечные значения; SHA повторно проверены.

Общий scorer аудиоагента использовал одинаковые reference/masks и вычислил
SI-SDR, raw least-squares gain, onset 20/40/100/200 мс, скользящие 100-мс окна
и post-burst recovery. Итог:
`artifacts/qa/gtcrn/matrix-43/result-with-dfn3.json`; происхождение каждого выхода,
точные команды и SHA — `artifacts/research/neural-denoisers/dfn3-matrix43/manifest.json`.
Корреляционный сдвиг clean A после фиксированной компенсации равен нулю у всех
трёх моделей; потери onset не объясняются простым неверным сдвигом 30 мс.

DFN3 лучше RNNoise 1.6 по SI-SDR в **25/27 смесей**; медианный выигрыш
`+3.99 / +4.49 / +9.80` дБ при +10/0/−10 дБ. В loud-burst — **8/9**, медиана
`+3.04` дБ. Но SI-SDR нечувствителен к масштабу, поэтому сравнивается и gain:

| Медиана gain активной речи | RNNoise 1.6 | GTCRN | DFN3 |
| --- | ---: | ---: | ---: |
| Смеси +10 дБ | 0.931 | 0.985 | 0.950 |
| Смеси 0 дБ | 0.810 | 0.908 | 0.896 |
| Смеси −10 дБ | 0.439 | 0.373 | 0.701 |

DFN3 сильно подавляет некоторые шумы, но RNNoise остаётся тише на чистом
пылесосе. Ни один такой случай не доказывает сохранение согласных:

| Ослабление только шума, дБ | RNNoise 1.6 | GTCRN | DFN3 |
| --- | ---: | ---: | ---: |
| Дождь | 20.67 | 31.79 | 60.64 |
| Пылесос | 45.19 | 13.25 | 39.63 |
| Клавиатура | 30.40 | 17.34 | 42.27 |

Существенный отрицательный результат DFN3 — начала речи и отдельные окна после
громкого шума. Это именно reference gain, а не показатель общего RMS:

| Окно gain | RNNoise 1.6 | GTCRN | DFN3 |
| --- | ---: | ---: | ---: |
| Clean A, первые 100 мс | 0.687 | 0.967 | 0.033 |
| Clean B, первые 100 мс | 0.510 | 0.853 | 0.178 |
| A/пылесос, первые 100 мс после первого burst | 0.002 | 0.539 | 0.008 |

У clean A общий SI-SDR DFN3 также ниже RNNoise: `15.32` против `16.75` дБ;
у DFN3 9.5% оценённых активных 100-мс окон имеют gain ниже половины reference,
у RNNoise и GTCRN в этой чистой записи — 0%. Поэтому штатный DFN3 не проходит
проверку «не обрывать речь», несмотря на сильное подавление шума и средние метрики.
Причинную абляцию сети или APM не делали. Новых условий и повторного подбора
порогов после результата нет. Full-band модель не восстанавливает полосу HFP.

Репродукция inference требует существующих закреплённых manifest, бинарника и
архива; helper проверяет их SHA и запрещает перезапись доказательств:

```sh
.local/tse-baseline-venv/bin/python tests/miccontrol/dfn3_matrix_probe.py \
  --manifest artifacts/qa/gtcrn/matrix-43/inputs.json \
  --binary .tmp/current/deep-filter-0.5.6-aarch64-apple-darwin \
  --model .tmp/current/deepfilternet-audit/models/DeepFilterNet3_onnx.tar.gz \
  --output-dir artifacts/research/neural-denoisers/dfn3-reproduced
```

Выполнены AST/`--help`, отрицательные проверки подмены model SHA и повторной
записи output-dir, повторная сверка всех 43 output SHA; результаты —
`artifacts/research/neural-denoisers/dfn3-matrix43-validation.json`.
