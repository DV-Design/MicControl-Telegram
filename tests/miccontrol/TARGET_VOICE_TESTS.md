# Воспроизведение диагностических тестов Target Voice

Это standalone-прототип, **не подключённый к приложению или APK**. Проверенная
модель ошибается в выборе владельца, в том числе при наложении речи; см.
[результаты и контрпример](../../docs/reports/audio/2026-10/target-voice-model-evaluation.md).
Ни модель, ни аудио, ни runtime-библиотеки не добавляются в Git. Все команды — из
корня репозитория; модельные вычисления запускайте отдельно от замеров скорости.

## Фиксированные зависимости и исходные данные

Использованный host: Python **3.12.14**, NumPy **2.5.4**, soundfile **0.14.0**,
ONNX Runtime **1.31.0**. Для Python-golden достаточно этих трёх пакетов; Torch и
полный набор зависимостей VoxLock не нужны.

```sh
python3.12 -m venv .local/tse-venv
.local/tse-venv/bin/pip install numpy==2.5.4 soundfile==0.14.0 onnxruntime==1.31.0
mkdir -p .tmp/current artifacts/qa/target-voice/speech
git clone https://github.com/arbazsiddiqui/voxlock .tmp/current/voxlock
git -C .tmp/current/voxlock checkout --detach 08ed37cbb79f449ca6b499bc23fb14138b207bfd
```

Веса — revision `a50f4e1d109301d4b6f61dec57ebb1a61e7d8f03` из
[официального model repository](https://huggingface.co/arbazsiddiqui/voxlock).

```sh
target_voice_models=.local/target-voice/voxlock-a50f4e1d/onnx
mkdir -p "$target_voice_models"
for target_voice_file in enroll.onnx chunk_int8_full.onnx; do
  curl --fail --location --output "$target_voice_models/$target_voice_file" \
    "https://huggingface.co/arbazsiddiqui/voxlock/resolve/a50f4e1d109301d4b6f61dec57ebb1a61e7d8f03/onnx/$target_voice_file"
done
```

Генератор ниже проверяет SHA-256 обоих весов, девяти FLAC, commit и `core.py`.
Хеши весов: enroll — `86645cba23f207def0b31a6e74a615d3b7a813b4fdf957c53b3af2905ba2ffd3`,
int8-full — `7b57c1bfd5acd5b33768a9dff09d9af487d45374b3ba0b991e541ff121eaa337`.

Аудио — девять независимых фраз трёх мужчин из официального
[OpenSLR 12 / LibriSpeech test-clean](https://www.openslr.org/12/), **CC BY 4.0**.
Если FLAC ещё не подготовлены, скачайте архив и извлеките только эти файлы:

```sh
curl --fail --location --output .tmp/current/test-clean.tar.gz \
  https://www.openslr.org/resources/12/test-clean.tar.gz
tar -xzf .tmp/current/test-clean.tar.gz --strip-components=4 \
  -C artifacts/qa/target-voice/speech \
  LibriSpeech/test-clean/6930/75918/6930-75918-0000.flac \
  LibriSpeech/test-clean/6930/75918/6930-75918-0007.flac \
  LibriSpeech/test-clean/6930/75918/6930-75918-0006.flac \
  LibriSpeech/test-clean/1320/122617/1320-122617-0003.flac \
  LibriSpeech/test-clean/1320/122617/1320-122617-0012.flac \
  LibriSpeech/test-clean/1320/122617/1320-122617-0026.flac \
  LibriSpeech/test-clean/5639/40744/5639-40744-0032.flac \
  LibriSpeech/test-clean/5639/40744/5639-40744-0002.flac \
  LibriSpeech/test-clean/5639/40744/5639-40744-0030.flac
```

VoxLock code/weights заявляют Apache-2.0; см.
[NOTICE и ревизии](../../TMessagesProj/jni/voip/miccontrol/NOTICE.target-voice) и
[полный upstream license](../../TMessagesProj/jni/voip/miccontrol/LICENSE.voxlock).
Для WeSpeaker ECAPA есть конфликт: HF-карточка указывает Apache-2.0, а
[официальные pretrained docs](https://github.com/wenet-e2e/wespeaker/blob/master/docs/pretrained.md#model-license)
указывают CC BY 4.0 для VoxCeleb-весов. Лицензии компонентов требуют уточнения
перед распространением производной модели; диагностический исходник весов не содержит.
ORT — MIT; сохраняйте его LICENSE и ThirdPartyNotices при распространении.

## Входы и Python golden

Все файлы `.f32`: little-endian Float32, mono 16 kHz, нормализованные значения.
Профиль — 48000 отсчётов; смесь — 318720. Сначала без inference:

```sh
.local/tse-venv/bin/python tests/miccontrol/prepare_target_voice_fixtures.py \
  --model-dir "$target_voice_models" --out .tmp/current/target-voice-inputs --inputs-only
```

Если сохранён manifest предыдущего прогона, добавьте
`--check-against artifacts/qa/target-voice/golden/manifest.json` для проверки
точных хешей. Выводите данные в другой каталог, сохраняя исходный manifest.
Полный генератор строит входы и три результата настоящего upstream Stream:

```sh
.local/tse-venv/bin/python tests/miccontrol/prepare_target_voice_fixtures.py \
  --model-dir "$target_voice_models" --out artifacts/qa/target-voice/reproduced
target_voice_golden=artifacts/qa/target-voice/reproduced
```

Получаются `mix.f32`, `reference-{6930,1320,5639}.f32`, соответствующие
`expected-*.f32` и `manifest.json`. WAV PCM16 roundtrip сохранён намеренно:
сравнение с исходными неквантизованными массивами дало бы другие входы.

## Диагностическая фиксация контекста

Для этого отдельного эксперимента нужен также **onnx 1.23.2**. Скрипт
[freeze_target_voice_context.py](freeze_target_voice_context.py) принимает
только закреплённые SHA-256 моделей, исходника и публичных A/C fixtures,
включая эталоны. Он добавляет вычисленные enrollment magnitude/context как
initializers, сохраняя все 685 исходных весовых initializers побайтно.

```sh
.local/tse-venv/bin/pip install onnx==1.23.2
.local/tse-venv/bin/python tests/miccontrol/freeze_target_voice_context.py \
  --model-dir "$target_voice_models" --golden-manifest "$target_voice_golden/manifest.json" \
  --output-dir .tmp/current/target-voice-frozen-reproduced \
  --evidence-dir artifacts/qa/target-voice/frozen-context-reproduced
```

Полноценные трёхвходовые графы имеют только `wav/h/c`. Отдельный
`DIAGNOSTIC_ONLY_FROZEN_A-5-input-compat.onnx` сохраняет пять имён входов
исключительно для существующего native probe: переданные `enroll_mag/context`
**игнорируются**, всегда выбирается публичный A6930. Это проверяется отдельно
с нулевыми профилями и отмечается в metadata. **Ни один полученный граф нельзя
выдавать за модель другого владельца или включать в APK.** Derived acoustic
данные профиля могут сохранять восстанавливаемую речь.

`host-proof.json` записывает K4/K5 output/state parity, полный A/C golden,
сохранение известного ошибочного C-случая и изменения optimized graph.
Проверенный эксперимент удалил 32 `MatMulIntegerToFloat` и уменьшил число
узлов с 3213 до 3142; оценка 624951296 MAC на блок относится только к этим
контекстным linear layers и не доказывает доминирование по времени.
Файлы `*.ort-optimized.onnx` предназначены для анализа на текущем host:
они могут зависеть от CPU. Для Android использовался portable граф без
предварительной оптимизации; ORT выполнял folding на устройстве.
В bounded Android-проверке при двух потоках RTF снизился с 3.304806 до
2.874009, оставаясь выше 1; это не решение для звонка в реальном времени.
Все графы и evidence сохраняются только в проверяемых Git-ignored каталогах.

## Native Mac: сравнение и память

Скачайте официальный ORT Android AAR: он также содержит C API headers.
Его проверенный SHA-256 —
`72683787a80d0608a3121b967d8e1239aef48286826661c953211626690540a7`.

```sh
target_voice_runtime=.tmp/current/tse-runtimes/onnxruntime-android-1.31.0
mkdir -p .tmp/current/tse-runtimes
curl --fail --location --output "$target_voice_runtime.aar" \
  https://repo.maven.apache.org/maven2/com/microsoft/onnxruntime/onnxruntime-android/1.31.0/onnxruntime-android-1.31.0.aar
printf '%s  %s\n' 72683787a80d0608a3121b967d8e1239aef48286826661c953211626690540a7 "$target_voice_runtime.aar" | shasum -a 256 -c -
unzip -q -o "$target_voice_runtime.aar" 'headers/*' -d "$target_voice_runtime"
curl --fail --location --output "$target_voice_runtime/LICENSE" \
  https://raw.githubusercontent.com/microsoft/onnxruntime/v1.31.0/LICENSE
curl --fail --location --output "$target_voice_runtime/ThirdPartyNotices.txt" \
  https://raw.githubusercontent.com/microsoft/onnxruntime/v1.31.0/ThirdPartyNotices.txt
target_voice_native=artifacts/qa/target-voice/native-macos
target_voice_dylib="$PWD/.local/tse-venv/lib/python3.12/site-packages/onnxruntime/capi/libonnxruntime.1.31.0.dylib"
mkdir -p "$target_voice_native"
ln -sfn "$target_voice_dylib" "$target_voice_native/libonnxruntime.1.dylib"
target_voice_build() {
  clang++ -std=c++17 -g -Wall -Wextra -Werror "$@" \
    -I"$target_voice_runtime/headers" -ITMessagesProj/jni/voip/miccontrol \
    TMessagesProj/jni/voip/miccontrol/TargetVoiceInference.cpp tests/miccontrol/target_voice_probe.cpp \
    "$target_voice_dylib" -Wl,-rpath,"$PWD/$target_voice_native" -pthread
}
target_voice_build -O2 -o "$target_voice_native/target_voice_probe"
for target_voice_speaker in 6930 1320 5639; do
  "$target_voice_native/target_voice_probe" --enroll-model "$target_voice_models/enroll.onnx" \
    --chunk-model "$target_voice_models/chunk_int8_full.onnx" --threads 4 \
    --profile "$target_voice_golden/reference-$target_voice_speaker.f32" \
    --mixture "$target_voice_golden/mix.f32" --expected "$target_voice_golden/expected-$target_voice_speaker.f32" \
    --output "$target_voice_native/native-$target_voice_speaker.f32"
done
target_voice_build -O1 -fsanitize=address,undefined -fno-omit-frame-pointer -o "$target_voice_native/target_voice_probe_asan"
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
  "$target_voice_native/target_voice_probe_asan" --enroll-model "$target_voice_models/enroll.onnx" \
  --chunk-model "$target_voice_models/chunk_int8_full.onnx" --profile "$target_voice_golden/reference-6930.f32" \
  --mixture "$target_voice_golden/mix.f32" --expected "$target_voice_golden/expected-6930.f32" \
  --output "$target_voice_native/sanitized-6930.f32" --reset-check
```

Scratch symlink исправляет SONAME Python wheel (`libonnxruntime.1.dylib`), не
меняя установленную библиотеку. Не включайте `-ffast-math`: проверкам NaN/Inf
нужна обычная IEEE-семантика. LeakSanitizer на проверенном Mac не поддерживается;
ASan/UBSan PASS **не означает LSan PASS**. Для отдельной проверки освобождения
памяти можно выполнить обычный probe через `/usr/bin/leaks --atExit --` с теми
же аргументами; проверенный короткий реальный fixture дал 0 утечек/0 байт.

Официальный AAR не содержит LICENSE/ThirdPartyNotices: команды получают их
отдельно из тега `v1.31.0`. Проверенные SHA-256:
LICENSE — `2f07c72751aed99790b8a4869cf2311df85a860b22ded05fa22803587a48922c`,
ThirdPartyNotices — `143764b952fdb1a7c69ce653bfba74a7744d6a8a573bfb73e235fba356c83de3`.

## Android arm64: standalone, без APK

Нужен NDK **27.2.12479018**. Сборщик проверяет AAR и arm64 SO (SHA-256
`8005a741e57117b4d7b476417706c0e9af13cf1b89db47e60f0cbc56e1af91e0`),
компилирует для API 24 и проверяет ELF LOAD alignment 16 KiB:

```sh
python3 tests/miccontrol/build_target_voice_android.py --output-dir .tmp/current/target-voice-android-final
python3 tests/miccontrol/run_target_voice_android.py --probe-dir .tmp/current/target-voice-android-final \
  --enroll-model "$target_voice_models/enroll.onnx" --chunk-model "$target_voice_models/chunk_int8_full.onnx" \
  --mixture "$target_voice_golden/mix.f32" --golden-manifest "$target_voice_golden/manifest.json" \
  --case A "$target_voice_golden/reference-6930.f32" "$target_voice_golden/expected-6930.f32" \
  --case B "$target_voice_golden/reference-1320.f32" "$target_voice_golden/expected-1320.f32" \
  --case C "$target_voice_golden/reference-5639.f32" "$target_voice_golden/expected-5639.f32" \
  --threads 4 --output-dir artifacts/qa/target-voice/android-reproduced
```

Последняя команда по умолчанию проверяет локальные файлы и печатает план;
**adb не вызывается**. Добавьте `--execute`, когда намерены выполнить тест на
`emulator-5554` (arm64, API 24+, 16 KiB pages). Runner пишет только в
`/data/local/tmp/danygramm-tse`, забирает Float32-выходы и сохраняет `result.json`.
`--reset-check` добавляет проверки Reset/границ; `--case` принимает ровно три
значения: имя, профиль, эталон. Тест не затрагивает аккаунт или данные приложения.

Mac golden совпал побитно для всех трёх профилей; Android int8-выход близок, но
не побитно идентичен. Runner всегда записывает RMSE/max error/cosine и может
проверять явно заданный `--max-rmse`; не повышайте допуск, чтобы скрыть проблему.
Успех сравнений подтверждает перенос DSP, **не качество «только мой голос»** и
не скорость на vivo. Известные ошибки выбора говорящего и замеры эмулятора
остаются в [отчёте качества](../../docs/reports/audio/2026-10/target-voice-model-evaluation.md).

Проверка регистрации 6 секунд через upstream Python с исходным pinned ONNX
остановилась на ограничении экспорта: enrollment выдаёт context `[1,512,598]`, но chunk graph
пытается сделать reshape для 298 кадров (3 секунды). Эта проверка не дала
результатов качества; обрезка/усреднение признаков за успешный 6s-тест не выдавались.
