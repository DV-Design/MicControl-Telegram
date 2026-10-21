# Ревью исследования RNNoise, GTCRN и DeepFilterNet3

21 октября 2026. Задача `miccontrol-8sd`. Независимое чтение исходников, JSON и сохранённых PCM; inference повторно не запускался. Product Java/native, APK, minSDK, пакет и подпись не менялись. UI и устройства не использовались.

Исследовательские доказательства согласованы. Улучшение средних метрик DFN3 не закрывает проблему подавления речи. Немедленную замену штатного шумоподавления эти результаты не обосновывают.

## Проверенные версии

- `gtcrn_streaming_probe.py`: SHA-256 `0bc897156eacc2d725549593aac8cda6f619551d49fa9fe09244041a023c133e`.
- `dfn3_matrix_probe.py`: SHA-256 `9d4bd6969cedee429bc32c1ad81859d2dfe69db42b0a2123f84380a1de61d795`.
- Общий manifest входов: `c4bca5c8a8bf23b654dd96ca180660aaae3fe5f3f19a85c90e0c4ba198a48877`.
- DFN3 provenance manifest: `ae393e0627f17aa95c9b7b89193b58d54950605e8eeae016aff684eba94a2fe8`.
- Официальный CLI `deep_filter 0.5.6`: SHA-256 `4601e7f4e4c03e59a4c5b5000216ef3add3e808799cfccd95e14e83ea4611081`.
- Архив DFN3 из source `d375b2d8309e0935d165700c91da9de862a99c31`: SHA-256 `c94d91f70911001c946e0fabb4aa9adc37045f45a03b56008cb0c8244cb63616`.

Первоначальный `result.json` содержит scorer SHA `cba1c0b9a05d26406e3c8ceb9c387e95c3736440fccb7bbd4a03bc2cddd1c42d`. Его точный snapshot восстановлен удалением 25 последующих строк provenance/input/calibration guards, SHA совпал. Метрики базового сравнения не менялись. В `result-with-dfn3.json` записан текущий scorer SHA; все четыре native source SHA совпадают с файлами исследования.

## Проверка сопоставимости и guards

Независимо проверены SHA всех 43 входов, 43 исходных input48 и 129 выходов трёх методов. Каждый выход конечен и содержит ровно `inputSamples16k` отсчётов. Общая длительность входов 352,595 с. Входные FLOAT WAV DFN3 побайтно по значениям совпали с существующим FloatS16 input48 / 32768; добавленные хвосты состоят из нулей. Пересчёт 16→48 для DFN3 повторно не выполнялся.

`dfn3_matrix_probe.py:52` проверяет SHA manifest/binary/model до inference и отказывается перезаписывать непустой каталог. `:69` закрепляет sample rate/FFT/hop/lookahead. В `:112` DFN3 получает тот же input48, что и RNNoise. CLI вызывается с `-D`; ко входному 48-кГц WAV добавлены 1440 нулевых отсчётов для фиксированной компенсации плюс terminal-hop padding. Длины всех 43 WAV подтверждают этот контракт. После компенсации удаляется только terminal padding, затем выполняется тот же Torchaudio Kaiser 48→16, что у RNNoise: width 64, rolloff `0.9475937167399596`, beta `14.769656459379492`. Нормализации/усиления выходов в коде нет.

В `gtcrn_streaming_probe.py:274` optional-model guard требует завершённый manifest, общий input manifest SHA, совпадающие case/input/output SHA. Дальше проверяются длина и конечность каждого PCM. После фиксированного сдвига RNNoise 480/48k и штатной компенсации DFN3 clean-A correlation lag равен нулю у всех трёх методов; подбора задержки на шумных смесях нет. Маски и reference общие, результаты сравниваются в полосе 16 кГц / 8 кГц. Путь Python venv сохраняется через `.absolute()`, без разыменования executable symlink.

Остался ограниченный guard gap для будущих прогонов: `dfn3_matrix_probe.py:111` проверяет input48 по длине/конечности и сохраняет его SHA, но заранее не связывает содержимое этого файла с закреплённым input16. Optional scorer также не проверяет input48 SHA из candidate manifest. Подмена input48 между подготовкой и новым запуском могла бы пройти preflight при неизменном input16. У проверенного набора все 43 input48 совпали с provenance; этот gap не отменяет текущие результаты. До использования helper с новыми входами стоит закреплять также input48 hashes/их детерминированное происхождение. Исходники в рамках read-only ревью не исправлялись.

## Результат и ограничения качества

Числа в отчётах совпали с общим JSON. GTCRN выиграл у RNNoise по SI-SDR в 24/27 смесей и 9/9 burst случаев; у него остаются существенные проигрыши по остаточному vacuum/typing шуму.

DFN3 выиграл в 25/27 смесей и 8/9 burst случаев. Ослабление noise-only составило 60,64 / 39,63 / 42,27 дБ для rain/vacuum/typing. При этом:

| Окно reference gain | RNNoise 1.6 | GTCRN | DFN3 |
|---|---:|---:|---:|
| Clean A, первые 100 мс | 0,687 | 0,967 | 0,033 |
| Clean B, первые 100 мс | 0,510 | 0,853 | 0,178 |
| A/vacuum, 100 мс после первого burst | 0,002 | 0,539 | 0,008 |

Эти отрицательные случаи блокируют утверждение, что речь больше не обрывается. Least-squares gain и доля окон с gain <0,5 показывают подавление компонента reference, но не являются тестом потери samples или разборчивости согласных. SI-SDR нечувствителен к общему масштабу, поэтому отдельно проверен raw gain. Ни MOS, ни ASR-разборчивость, ни прослушивание здесь не выполнены.

Официальный DFN3 WAV writer сохраняет PCM16, что подтверждено для всех 43 файлов. Это дополнительная квантизация относительно float outputs RNNoise/GTCRN; очень слабый остаточный шум и численно нулевые окна нельзя интерпретировать как точный float-выход сети. Значения onset gain выше остаются измерениями сохранённого CLI-результата.

Причина конкретных потерь onset не установлена. LSNR `Sigmoid * 50 - 15` закреплённого encoder лежит в [-15, 35], поэтому строгий branch `lsnr < -15` не объясняет эти результаты при корректной конечной арифметике. Это не повод менять порог по одному примеру. Полная APM NS/AGC/AEC цепочка, Bluetooth, Android задержка и CPU не проверялись. Полоса 8 кГц этой матрицы также не оценивает full-band преимущество DFN3.

## Доказательства

- [GTCRN исследование](../../audio/2026-10/gtcrn-streaming-evaluation.md), [DFN3 исследование](../../audio/2026-10/neural-denoiser-alternatives.md).
- [Android runtime feasibility](../../audio/2026-10/sherpa-android-1.13.8-static-feasibility.md): shared C API ORT не проходит API 23, static JNI прошёл только статические проверки. Никакой Android inference этим ревью не подтверждён.
- `artifacts/qa/gtcrn/matrix-43/{result.json,result-with-dfn3.json,independent-review.json,independent-dfn3-review.json}`.
- `artifacts/qa/gtcrn/matrix-43/gtcrn_streaming_probe-base-snapshot.py` с исходным scorer SHA.
- `artifacts/research/neural-denoisers/dfn3-matrix43/{manifest.json,input-wav/,official-output/}` и `dfn3-matrix43-validation.json`.

Проверка синтаксиса двух helpers и целостности сохранённых файлов прошла. Повторных запусков моделей или изменения порогов после review не было.
