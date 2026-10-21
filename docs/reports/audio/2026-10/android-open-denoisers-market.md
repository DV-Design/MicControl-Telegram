# Открытые потоковые шумоподавители для Android

21 октября 2026, `miccontrol-8sd.1`. Ограниченный обзор первичных исходников,
моделей и документации. **По интеграционной готовности первым новым full-band
кандидатом был выбран DPDFNet; резервный лёгкий вариант — UL-UNAS.** Последующие
smoke DPDFNet и современного RNNoise выявили потери начал речи; готового
победителя пока нет. Современный RNNoise — другая сеть, чем bundled RNNoise
в текущем приложении. Ни один кандидат ещё не проверен на Android.
Продукт, зависимости, ключи, подпись и карты этим исследованием не изменены.

## Граница утверждения «лучший»

Открытого сопоставимого испытания всех Android-решений, включая закрытые
обработчики производителей, здесь нет. PESQ/DNSMOS из разных статей, MAC/s и
размер весов не образуют достоверный общий рейтинг. Для задачи Danygramm
существенны одновременно сохранение слабых начал речи, восстановление после
громких всплесков, остаточный шум, задержка, стабильный p95 и батарея телефона.

Существующие [43 PCM сравнения](neural-denoiser-alternatives.md) обнаружили
компромиссы: DFN3 лучше RNNoise 1.6 по SI-SDR в 25/27 смесей, но gain первых
100 мс clean A/B — 0.033/0.178; GTCRN лучше в 24/27, но оставляет больше чистого
шума пылесоса и клавиатуры. Ни один результат не доказывает готовую замену.
Высокий WebRTC NS и AGC1 стоят **перед** дополнительной сетью; их вклад требует
отдельной абляции, причинность обрывов пока не установлена.

## Кандидаты и закрепления

| Кандидат | Реально доступные веса и стоимость | Потоковость и задержка | Путь к Android |
| --- | --- | --- | --- |
| **DPDFNet 48 kHz HR** | Официальные ONNX/TFLite. 2HR: 2.58 M параметров, заявлено 2.42 G MAC/s; ONNX **10 493 337 байт**. 8HR: 3.63 M, 7.17 G MAC/s, **14 857 107 байт**. | Causal stateful inference, шаг 480 / 10 мс. Заявленные первые 20 мс буферизации нельзя путать с задержкой восстановленной waveform; первый отдельный clean-контроль 2HR дал 1920 отсчётов / 40 мс, ещё проверяется аудиоагентом. | Есть официальный sherpa-onnx streaming C API; возможен ORT CPU без Java на capture. Совместимость конкретной Android-сборки, 16 КБ и скорость vivo ещё не доказаны. |
| **UL-UNAS** | Официальный DNS3 checkpoint 2 284 926 байт; уже экспортированный `ulunas_stream_simple.onnx` **788 967 байт**. Статья: 171 k параметров, 34.91 M MAC/s. | Только **16 кГц**, FFT 512 / шаг 256 (32/16 мс), явные convolution/GRU caches. Сеть causal без дополнительного NN lookahead; это не нулевая задержка waveform. | ONNX opset 11 с обычными Conv/GRU; практичен ORT C API + свой STFT/OLA на worker. Нет найденного официального Android AAR/benchmark модели. |
| **RNNoise main 2025** | Официальный архив содержит full/little C weights; **58 603 099 байт — размер distribution archive, не APK/runtime**. Фактический full-model header: Conv 128/384 и три GRU по **384**, sparse/quantized C kernels. Современный проверенный MAC/s пока не получен. | Mono 48 кГц, C API `rnnoise_process_frame`. Есть дополнительный `delayed_X` перед synthesis; нельзя переносить delay старого RNNoise без проверки. | Нативный C и ARM NEON, без отдельного ONNX runtime. Это наиболее прямой путь к существующему NDK; actual min23/ELF 16 КБ, качество и скорость требуют сборки/измерения. |

Размеры DPDFNet и MAC/s заявлены авторами в
[официальном model card](https://huggingface.co/Ceva-IP/DPDFNet/tree/dd6818d00f50c836fed43a6243ebe49116de5964);
варианты 8/16/48 кГц и готовые форматы описаны в
[закреплённом source README](https://github.com/ceva-ip/DPDFNet/tree/9bd9844a227bb6aa57e55588d8d0e961fcff1c46).
Наличие streaming C API подтверждено
[документацией sherpa-onnx](https://k2-fsa.github.io/sherpa/onnx/speech-enhancement/dpdfnet-c-api.html).
Это подтверждение интеграционного интерфейса, не телефонного benchmark.

Для UL-UNAS основание — [статья v2](https://arxiv.org/html/2503.00340v2)
и [потоковый код/контракт](https://github.com/Xiaobin-Rong/ul-unas/tree/00f7c700da43d38347f30a6ccebd86fcbc798e07/ulunas_onnx).
BiGRU внутри attention идёт **по частоте**, а inter-frame GRU однонаправлен;
по одному слову `bidirectional` нельзя объявлять всю сеть noncausal.
Официальный waveform-пример сначала вычисляет целый `torch.stft` с обычным
center padding, затем делает frame-wise NN и общий iSTFT. Для реального capture
нужен конечный STFT/OLA buffer и явная задержка; готовый пример не является
законченным Android audio callback. Caches: 5358 + 402 + 1056 FP32 значений,
27 264 байта без временных tensors. Оба ONNX проверены `onnx.checker`, inference
этого кандидата данным обзором не запускался.

У [текущего Xiph source](https://github.com/xiph/rnnoise/tree/70f1d256acd4b34a572f999a05c87bf00b67730d)
README описывает обновлённые public training datasets, full/little модели и
автозагрузку. Нельзя использовать показатели старой статьи 2018 года как
измерения этой новой сети. Отдельное ограниченное PCM сравнение современной
полной модели выполнено ниже; старые 43 выхода не пересчитывались.

## Лицензии, веса и происхождение

| Кандидат | Проверенные условия | Точные pins |
| --- | --- | --- |
| DPDFNet | Source Apache-2.0; **официальный HF model card также явно Apache-2.0**. NC-ограничения в проверенных license/card не заявлены. | Source `9bd9844a227bb6aa57e55588d8d0e961fcff1c46`; HF `dd6818d00f50c836fed43a6243ebe49116de5964` |
| UL-UNAS | [Корневой LICENSE MIT](https://github.com/Xiaobin-Rong/ul-unas/blob/00f7c700da43d38347f30a6ccebd86fcbc798e07/LICENSE); checkpoint и ONNX опубликованы в том же tree. Отдельной лицензии/model card для весов и NC-условий в нём нет. Не выдаём это за отдельное явное разрешение правообладателя датасета. | Source/models `00f7c700da43d38347f30a6ccebd86fcbc798e07` |
| RNNoise | [COPYING BSD-3-Clause](https://github.com/xiph/rnnoise/blob/70f1d256acd4b34a572f999a05c87bf00b67730d/COPYING). В model archive шесть файлов C/header/PyTorch; отдельного LICENSE нет. В проверенных source/README нет NC-условия. PyTorch pickle не открывался/не исполнялся. | Source `70f1d256acd4b34a572f999a05c87bf00b67730d`; archive SHA из официального `model_version` ниже |

DPDFNet2HR SHA-256:
`7f0575a5cec0ba4ffd8f8bd657e06d007e4ccdd955d76faab922b9d3291dc14b`.
DPDFNet8HR:
`7b3afbb260a08fe9af3d16e3bda992971be1e7e951d1dee7c2d235f5c43f5631`.
Оба URL имеют вид
`https://huggingface.co/Ceva-IP/DPDFNet/resolve/<HF-pin>/onnx/<variant>.onnx`.
Нельзя смешивать current HF и более старые sherpa release assets: аудиоагент
проверил, что у 2HR веса/выходы различаются. В текущем сравнении используется
именно закреплённый HF вариант.

UL-UNAS simplified ONNX SHA-256:
`f2e804d54d6a88f4f82f44d86c9f1cf646db2509bfca935cfbfc5fcd8cbfac3b`.
RNNoise archive SHA-256:
`0a8755f8e2d834eff6a54714ecc7d75f9932e845df35f8b59bc52a7cfe6e8b37`,
совпадает с содержимым
[`model_version`](https://github.com/xiph/rnnoise/blob/70f1d256acd4b34a572f999a05c87bf00b67730d/model_version)
и загрузкой официального Xiph media server. Контрольная сумма подтверждает
закрепление скачивания, не качество модели.

## Поддержка и ограничения выбора

GitHub API на дату обзора: DPDFNet main commit 09.09.2026
(repo push 20.10.2026), UL-UNAS main commit 17.06.2026, Xiph convenience mirror
main commit 22.02.2025; все три не archived. Это даты наблюдения, не SLA
поддержки. RNNoise README указывает GitLab Xiph как основной upstream.

Коротко проверен и официальный LiSenNet `df4e481…`, MIT: в tree нет pretrained
checkpoint/ONNX и README требует свой `--ckpt_path`; его исходный phase-refinement
вариант использует Griffin–Lim с lookahead. Поэтому в данный bounded shortlist
готовых causal весов он не добавлен. Сторонние retrained HF weights не подменяют
официальную модель без отдельной проверки. Offline, cloud-only и CUDA-only
решения не дают готового пути к локальному исходящему Android-звонку.

DPDFNet2/8HR после пяти smoke каждый также не прошли onset gate; полный прогон
43 остановлен, детали сохраняет отдельный отчёт аудиоагента. UL-UNAS перешёл
к ограниченному smoke, его оценка остаётся отдельной работой. Если качество выдержит gate,
нужен один arm64 Android CPU prototype: exact waveform parity, min API,
ELF LOAD 16 КБ, размер `.so` + weights, p50/p95/p99, RSS и real-time budget;
после этого — физическая проверка vivo. Отсутствие cloud inference не означает
нулевой расход батареи. Full-band модель не расширяет Bluetooth HFP полосу.

Raw source/size/hash evidence остаётся ignored:
`artifacts/research/android-open-denoisers/{repositories,downloads,ul-unas-onnx,rnnoise-model-archive,lisennet}.json`.
DFN native feasibility остановлена до установки Rust toolchain и до Android
сборки. В этом этапе нет UI, микрофона, аккаунта или продуктовой APK-сборки.

## Последующее ограниченное сравнение современного RNNoise

Выполнены только **три существующих** случая: `clean_A`, `clean_B`,
`bursts_A_vacuum_cleaner`. Репродукторы:
[rnnoise_current_probe.py](../../../../tests/miccontrol/rnnoise_current_probe.py)
и [малый C adapter](../../../../tests/miccontrol/rnnoise_current_pcm.c).
Собраны неизменённые десять upstream C sources с полными штатными C weights;
`-DDISABLE_DEBUG_FLOAT` соответствует обычному default `configure`, ARM NEON
выбирается штатным source. Host binary 3 671 536 байт — это **не размер Android
библиотеки** и не доказательство телефонной скорости. Архив checkpoint pickle
не исполнялся; full-model C/header SHA проверены перед компиляцией.

Вход — существующий FloatS16 `input48.f32`, выход остаётся Float32: нет PCM16
округления, нашего exponent 1.6, внешнего VAD gate или output normalization.
Hop 480, задержка **960 отсчётов / 20 мс**: один OLA hop и явный `delayed_X` hop.
Это подтверждено одной clean A cross-correlation: после фиксированного trim
остаточный lag равен нулю. Для шумных случаев задержка не подбиралась. На конце
добавлен нулевой хвост; выход 48→16 использует общий Torchaudio Kaiser из
43-case матрицы, длина сохранена точно, все отсчёты конечные.

Независимый общий scorer дал:

| Метрика | Bundled RNNoise 1.6 | Official RNNoise 2025 full |
| --- | ---: | ---: |
| Clean A SI-SDR, дБ | 16.75 | 7.59 |
| Clean A active reference gain | 0.980 | 0.777 |
| Clean A onset 100 мс gain | 0.687 | 0.336 |
| Clean B onset 100 мс gain | 0.510 | 0.000754 |
| A/пылесос burst SI-SDR, дБ | 2.65 | 5.00 |
| A/пылесос pause attenuation, дБ | 28.41 | 63.57 |

Штатная новая модель сильнее подавляет этот шум, одновременно ухудшая сохранение
чистой речи. **Smoke gate отрицательный; остальные 40 inference не запускались.**
Три случая не являются общим рейтингом модели. Не делались обучение, замена
весов, подбор порогов или ослабления после результата.

Evidence:
`artifacts/research/android-open-denoisers/rnnoise2025-matrix43/manifest.json`
(несмотря на имя каталога, `caseSelection=smoke`, ровно три случая),
`artifacts/qa/gtcrn/matrix-43/result-rnnoise2025-smoke.json`.
AST/help, C `-Wall -Wextra -Werror` syntax, реальные отрицательные проверки
подмены source SHA, перезаписи evidence, неполного кадра и NaN прошли;
`artifacts/research/android-open-denoisers/rnnoise2025-validation.json`.

Репродукция этого smoke с заранее скачанными закреплёнными архивами:

```sh
.local/tse-baseline-venv/bin/python tests/miccontrol/rnnoise_current_probe.py \
  --source-archive .tmp/current/denoisers-market/rnnoise-source.tar.gz \
  --model-archive .tmp/current/denoisers-market/rnnoise/rnnoise_data-0a8755f8e2d834eff6a54714ecc7d75f9932e845df35f8b59bc52a7cfe6e8b37.tar.gz \
  --output-dir artifacts/research/android-open-denoisers/rnnoise2025-smoke-reproduced \
  --phase smoke
```
