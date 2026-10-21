# GTCRN: потоковое сравнение с RNNoise 1.6

Дата: 21 октября 2026. Рабочая версия приложения: Danygramm 1.2 с картами; её код не менялся. Это исследование отдельных шумодавов на публичных PCM, без сборки APK и проверки интерфейса.

GTCRN лучше сохранил форму речи в большинстве условий, но не подходит для безусловной замены RNNoise при приоритете удаления окружающего шума. Он выиграл по SI-SDR в 24 из 27 смесей и во всех девяти случаях с громкими всплесками. При этом остаточный пылесос и стук клавиш в паузах оказались заметно громче. Очень громкий фон по-прежнему подавлял речь. До выбора модели нужно учесть эти проигрыши; одного снижения RMS или среднего SI-SDR недостаточно.

## Модель, веса и лицензия

Проверен [официальный GTCRN](https://github.com/Xiaobin-Rong/gtcrn/tree/502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73), commit `502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73`. В репозитории [MIT License](https://github.com/Xiaobin-Rong/gtcrn/blob/502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73/LICENSE), Copyright © 2024 Rong Xiaobin; отдельного исключения для размещённых там весов не найдено. Аудио и веса в Git приложения не добавляются.

| Файл | Размер | SHA256 |
|---|---:|---|
| [Streaming DNS3 checkpoint](https://github.com/Xiaobin-Rong/gtcrn/blob/502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73/stream/onnx_models/model_trained_on_dns3.tar) | 737 323 B | `250fa2820ea9947704a62dda8e642ba773a067719c5e4294ad95aeab23f06442` |
| [Официальный streaming `gtcrn_simple.onnx`](https://github.com/Xiaobin-Rong/gtcrn/blob/502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73/stream/onnx_models/gtcrn_simple.onnx) | 535 190 B | `b4718df6228e7bdf1a8a435cf98f838636eb2fd331acabf86ba87c5192ebcb87` |
| [Тот же граф для Sherpa, с metadata](https://github.com/k2-fsa/sherpa-onnx/releases/download/speech-enhancement-models/gtcrn_simple.onnx) | 535 638 B | `e77603ac0c23dac3227dd2d7135b3a585cbee2679048aecfa886657d3ae1b534` |

Граф Sherpa побайтно совпал с upstream `ModelProto.graph`; различаются metadata. Корневой `checkpoints/model_trained_on_dns3.tar` в том же репозитории содержит другие веса: для проверки взят именно checkpoint из `stream/onnx_models`, который загружает официальный streaming example.

Checkpoint прочитан через `torch.load(weights_only=True, map_location="cpu")`, без allowlist и исполнения pickle. `strict=True` загрузил все 271 ключ. Подсчёт: 23 669 обучаемых параметров, 48 245 с фиксированным ERB, 48 847 элементов state dict с buffers. После официального `convert_to_stream` проверены 12 последовательных спектральных кадров с сохранением состояний. PyTorch → ONNX Runtime: максимальная ошибка выхода `1.64e-7`, худшая ошибка cache `5.01e-6`. Веса не экспортировались заново и не дообучались.

## Потоковый контракт и задержка

Реально использован `sherpa_onnx.OnlineSpeechDenoiser` 1.13.8, [официальный пример](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/python-api-examples/online-speech-enhancement-gtcrn.py), source tag commit `11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf`. Лицензия Sherpa — Apache-2.0. Python wheel Sherpa содержит ORT **1.28.2**, что проверено `OrtGetApiBase()->GetVersionString()`; отдельно установленный ORT **1.31.0** использован для checkpoint parity. Эти runtime не смешиваются в отчётности.

- Mono float32, 16 кГц; STFT 512, hop 256, окно `sqrt(Hann)`. Спектр входа и выхода `[1,257,1,2]`, opset 11.
- Состояния: convolution `[2,1,16,16,33]`, temporal attention `[2,3,1,1,16]`, temporal RNN `[2,1,33,16]` — 18 048 float32, 72 192 B суммарно.
- По [исходникам](https://github.com/Xiaobin-Rong/gtcrn/blob/502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73/stream/gtcrn_stream.py) temporal convolution использует прошлый cache, temporal GRU однонаправленный. Двунаправленный GRU работает по частоте внутри текущего кадра; LayerNorm охватывает частоту и каналы, BatchNorm работает в eval. Будущих спектральных кадров нейросеть не запрашивает.
- Сам STFT требует буферизации. [Реализация Sherpa](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.8/sherpa-onnx/csrc/online-speech-denoiser-stft-impl.h) выдаёт первые 256 samples после получения 512 входных: 32 мс при точных hop-блоках, 40 мс при фактической подаче по 10 мс. Далее выход идёт порциями по 256, иногда пустыми при очередной 160-sample подаче. Для callback приложения потребуется FIFO; это не обработка «без задержки».
- `flush` возвращает хвост и сбрасывает state. Во всех 43 случаях длина после flush равна входной, значения конечны. Подача clean A по 160 и 256 samples дала побайтно одинаковый результат; отдельный reset после частичного потока также дал `maxAbs=0`.

Заявленные авторами 33 MMAC/s и RTF 0.07 на Intel i5-12400 — характеристики из [README](https://github.com/Xiaobin-Rong/gtcrn/blob/502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73/README.md), а не наш замер Android. Эта проверка выполнялась функционально, параллельно с другими исследованиями, поэтому её время не используется как performance benchmark.

## Метод сравнения

Скрипт: [gtcrn_streaming_probe.py](../../../../tests/miccontrol/gtcrn_streaming_probe.py). Взяты те же три полных LibriSpeech utterance A/B/C и ESC-50 rain/vacuum/typing, что в [предыдущем исследовании RNNoise](ambient-noise-spectral-evaluation.md). Их шесть исходных SHA не менялись; скрипт проверяет FLAC/WAV до чтения. LibriSpeech — CC BY 4.0; ESC-50 — CC BY-NC 3.0, rain из ESC-10 — CC BY. Это исследовательские файлы, они не входят в APK.

Всего 43 случая, 352.595 секунды: 3 clean; 27 смесей (каждый голос × каждый шум × +10/0/−10 дБ); 9 случаев с двумя 400 мс всплесками фона; 3 noise-only; цифровая тишина. До и после каждой фразы — одна секунда паузы. Исходная речь приведена к RMS 0.06, SNR рассчитан по всей фразе; для всплесков фон меняется с +10 до −10 дБ SNR с 20 мс переходом. Чтобы исключить искусственный клиппинг, к input и clean reference применён один общий коэффициент, ограничивающий peak до 0.90 с учётом 48 кГц реконструкции. Коэффициент записан для каждого случая. Выходы не нормализуются, не усиливаются и не подрезаются.

У обоих методов одинаковая полоса: исходники, reference и итоговые выходы — **16 кГц**, то есть до 8 кГц. Для существующего RNNoise этот вход пересчитан в 48 кГц, обработан фактическим `VoiceIsolationDenoiser` с exponent **1.6**, затем выход пересчитан обратно. Использован прежний native runner и неизменённые product-файлы. Потеря полосы выше 8 кГц — отдельный компромисс GTCRN относительно нынешнего 48 кГц тракта приложения.

RNNoise компенсирован фиксированным сдвигом 480 samples при 48 кГц. Sherpa уже возвращает aligned waveform после пропуска первого OLA-hop. Одна clean A calibration в диапазоне ±128 samples при 16 кГц дала lag 0 для обоих; на шумных смесях задержка не подбиралась.

Метрики: SI-SDR на активной речи, сырой least-squares gain относительно clean reference, attenuation в паузах, gain начала речи на 20/40/100/200 мс, gain активных 100 мс окон и восстановление через 100/200 мс после всплеска. Маски определяются только чистой речью и одинаковы для методов. Доля окон с gain <0.5 — **прокси подавления**, не доказательство выпадения samples или разборчивости. Численно почти нулевые 10 мс окна проверены отдельно после всплесков.

## Результаты GTCRN против RNNoise 1.6

В таблице SI-SDR — медиана по соответствующим случаям; gain без нормализации выхода.

| Условия | SI-SDR RN / GTCRN, дБ | Медиана разницы GTCRN−RN | Победы GTCRN | Медиана speech gain RN / GTCRN |
|---|---:|---:|---:|---:|
| Clean | 16.75 / 32.35 | +18.75 дБ | 3/3 | 0.980 / 0.996 |
| +10 дБ SNR | 11.65 / 16.85 | +3.78 дБ | 8/9 | 0.931 / 0.985 |
| 0 дБ SNR | 7.69 / 9.83 | +2.29 дБ | 8/9 | 0.810 / 0.908 |
| −10 дБ SNR | −4.13 / −1.05 | +1.71 дБ | 8/9 | 0.439 / 0.373 |
| Всплески | 8.50 / 10.92 | +2.23 дБ | 9/9 | 0.853 / 0.890 |

Чистую речь GTCRN в целом сохранил лучше, включая начало фразы. Однако для clean A полный active gain составил 0.960 против 0.980 у RNNoise; для clean B в первых 200 мс — 0.646 против 0.668. При −10 дБ оба метода сильно искажают/подавляют речь: GTCRN gain от 0.106 до 0.681. Средний выигрыш SI-SDR этого не отменяет.

Три проигрыша SI-SDR: A + rain при 0 дБ (**−1.71 дБ**, gain GTCRN 0.392 против RN 0.617); A + typing при +10 дБ (**−0.89 дБ**, gain 0.763 против 0.896); A + typing при −10 дБ (**−1.55 дБ**, gain 0.373 против 0.439).

| Чистый шум, attenuation в steady pause | RNNoise 1.6 | GTCRN |
|---|---:|---:|
| Rain | 20.67 дБ | 31.79 дБ |
| Vacuum | 45.19 дБ | 13.25 дБ |
| Typing | 30.40 дБ | 17.34 дБ |

У пылесоса и клавиш GTCRN оставляет значительно больше фона. Это существенный проигрыш для текущего запроса, даже если часть случаев с речью имеет лучший SI-SDR.

После первого всплеска vacuum у A gain первых 100 мс вырос с **0.002 до 0.539**, после второго — с **0.126 до 0.562**. Но после первого всплеска typing у A gain ухудшился с **0.953 до 0.325**. В остальных условиях также есть неодинаковые результаты восстановления. Численно почти нулевых активных 10 мс окон после всплесков не найдено у обоих методов; это не исключает слышимое подавление речи. На цифровой тишине оба дали точный ноль.

Полные входы, outputs и метрики: `artifacts/qa/gtcrn/matrix-43/inputs.json`, `result.json`, `checkpoint-audit.json`, `stream-checks.json`. В result сохранены исходные SHA, SHA native-файлов, скрипта и каждого выхода, все onset/recovery окна. Первый orchestration run остановился из-за разыменования symlink venv Python, а не модели. Исправлен выбор executable; сохранён `matrix-43.log`. Уже готовые native outputs не пересчитывались: отдельно выполнены streaming и scoring phases.

## Дополнительный кандидат: DeepFilterNet3 на тех же входах

После GTCRN отдельно проверен DeepFilterNet3 через официальный CLI 0.5.6; [provenance и лицензии](neural-denoiser-alternatives.md). Его 43 выхода переданы **в тот же scorer**, без повторной GTCRN/RNNoise inference. Использованы существующие `input48.f32` / 32768, без новой интерполяции; фиксированная компенсация 1440 samples при 48 кГц и тот же Kaiser resampler до 16 кГц. Общая clean A calibration подтвердила lag 0. Официальный CLI пишет PCM16 WAV: эта дополнительная квантизация отмечена как отличие от float выходов двух других методов. Нормализации выхода нет.

| Условия | SI-SDR RN / GTCRN / DFN3, дБ | Медиана разницы DFN3−RN | Победы DFN3 над RN | Speech gain RN / GTCRN / DFN3 |
|---|---:|---:|---:|---:|
| Clean | 16.75 / 32.35 / 28.76 | +11.12 дБ | 2/3 | 0.980 / 0.996 / 0.973 |
| +10 дБ SNR | 11.65 / 16.85 / 17.49 | +3.99 дБ | 8/9 | 0.931 / 0.985 / 0.950 |
| 0 дБ SNR | 7.69 / 9.83 / 12.68 | +4.49 дБ | 8/9 | 0.810 / 0.908 / 0.896 |
| −10 дБ SNR | −4.13 / −1.05 / 5.94 | +9.80 дБ | 9/9 | 0.439 / 0.373 / 0.701 |
| Всплески | 8.50 / 10.92 / 12.64 | +3.04 дБ | 8/9 | 0.853 / 0.890 / 0.906 |

На noise-only rain/vacuum/typing attenuation DFN3 составил **60.64 / 39.63 / 42.27 дБ**. Это сильнее GTCRN во всех трёх случаях; относительно RNNoise rain и typing тише, vacuum на 5.56 дБ громче. При очень сильном фоне DFN3 лучше сохранил речь в большинстве случаев. Исключение — A с rain: при 0 дБ SI-SDR 2.24 против 3.76 у RNNoise, а при burst — 1.88 против 2.32. A с typing при +10 дБ также хуже: 7.65 против 10.88 дБ.

Для жалобы на обрыв речи остаётся серьёзный дефект: в **чистой** A-фразе gain первых 100 мс DFN3 всего **0.033**, RNNoise **0.687**, GTCRN **0.967**; для чистой B — **0.178 / 0.510 / 0.853** соответственно. В полной clean A-фразе DFN3 gain 0.931 и SI-SDR 15.32 дБ против 0.980/16.75 у RNNoise. После первого vacuum-burst у A gain первых 100 мс DFN3 0.008, RNNoise 0.002, GTCRN 0.539. На фоне улучшений при −10 дБ такие потери начала фразы нельзя скрывать средними величинами.

По этой ограниченной матрице DFN3 — более сильный кандидат для **следующего прототипа подавления фона**, а GTCRN лучше сохраняет некоторые начала фраз. Ни один из проверенных методов не прошёл как готовая универсальная замена: у DFN3 отдельно нужно разобраться с подавлением первых звуков, у GTCRN — с остаточным бытовым шумом. Параметры моделей ради улучшения этой таблицы не подбирались; интеграция в приложение не выполнялась.

Общий JSON: `artifacts/qa/gtcrn/matrix-43/result-with-dfn3.json`; source/provenance: `artifacts/research/neural-denoisers/dfn3-matrix43/manifest.json`. Scorer проверяет complete manifest, совпадение SHA входного manifest и SHA входов/выходов дополнительного метода. У всех 129 сравниваемых outputs проверены конечность, длина и SHA. Низкий gain — измеренное подавление/искажение, не подтверждённый packet dropout и не субъективная оценка разборчивости. Несколько исходных/clean/RNNoise/GTCRN примеров для прослушивания сохранены с неизменным уровнем как FLOAT WAV в `artifacts/qa/gtcrn/matrix-43/listening/`.

## Применимость к Android и границы вывода

Модель небольшая, монофоническая, работает с явным потоковым state и имеет официальный путь через Sherpa/ONNX. Это делает её кандидатом для мобильного прототипа, но не доказывает приемлемую задержку или CPU на телефоне. ORT Android 1.31.0 AAR, ранее проверенный в проекте, требует API 24, тогда как приложение поддерживает API 23. Это ограничение конкретной поставки runtime; поднимать minSdk ради исследования нельзя. [Отдельная статическая проверка Sherpa Android](sherpa-android-1.13.8-static-feasibility.md) нашла совместимый по ELF/symbol closure static JNI/AAR с 16 KiB alignment, а shared C API bundle для API 23 отклонила. Выполнение на Android ещё не проверено; полный готовый runtime также включает дополнительные TTS/eSpeak-компоненты с отдельными лицензионными обязательствами.

Текущий продукт перед RNNoise уже применяет WebRTC NS и fixed digital AGC1. Их сочетание может влиять на обрывы речи, но причинность этим исследованием не доказана: здесь сравниваются **отдельные denoiser stages**, без APM NS/AGC/AEC. Замена только последнего stage не гарантирует исправления всего call-тракта. Не проверялись физический телефон, Bluetooth, живые звонки, MOS/ASR-разборчивость и интерфейс. Три голоса и три шума не покрывают все бытовые условия.

## Воспроизведение

Нужны pinned public FLAC/WAV из существующих audio fixtures, `clang`, Torch/torchaudio/soundfile/NumPy и минимальный `einops==0.7.0` в `.local/tse-baseline-venv`; `sherpa_onnx==1.13.8`, ONNX 1.23.2 и ORT 1.31.0 — в отдельном `.local/tse-venv`. Версии фактического запуска записаны в result. Зависимости из старого `requirements.txt` GTCRN поверх этих окружений не устанавливаются.

```bash
git clone https://github.com/Xiaobin-Rong/gtcrn.git .tmp/current/gtcrn-official
git -C .tmp/current/gtcrn-official checkout --detach 502ebfab64da7c4a9af78dcb9c6ceef1ebb01c73
mkdir -p .local/target-voice/gtcrn-502ebfa
curl --fail --location https://github.com/k2-fsa/sherpa-onnx/releases/download/speech-enhancement-models/gtcrn_simple.onnx --output .local/target-voice/gtcrn-502ebfa/gtcrn-sherpa.onnx
.local/tse-baseline-venv/bin/python tests/miccontrol/gtcrn_streaming_probe.py --output-dir artifacts/qa/gtcrn/reproduction-new
```

Хеши модели и исходных fixtures проверяются до работы. Новый каталог обязателен для полного запуска. Чтобы добавить готовый, уже выровненный вывод другого метода `<case>-dfn3.f32`, используются те же метрики без новой GTCRN/RNNoise inference:

```bash
.local/tse-baseline-venv/bin/python tests/miccontrol/gtcrn_streaming_probe.py --score-only --output-dir artifacts/qa/gtcrn/matrix-43 --additional-model dfn3=artifacts/research/neural-denoisers/dfn3-matrix43 --result-name result-with-dfn3.json
```

Для дополнительного метода отдельно проверяются provenance, одинаковая входная подготовка и фиксированная задержка. Этот режим не выдаёт произвольный файл за результат заявленной модели.
