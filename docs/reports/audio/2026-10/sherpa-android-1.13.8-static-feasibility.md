# sherpa-onnx 1.13.8: статическая проверка Android runtime

21 октября 2026. Проверены официальные release assets и исходники. Приложение и его minSDK 23 не менялись. Сборка APK, inference, UI, adb и проверки устройства не запускались.

Готовый C API bundle не совместим с API 23 из-за его shared ONNX Runtime. Статический JNI-вариант прошёл проверку ELF, зависимостей и разрешения символов для API 23; официальный AAR содержит online GTCRN API, доступный из Java. Это позволяет рассматривать JNI worker после проверки качества модели. Скорость, загрузка модели и работа runtime на Android пока не подтверждены.

## Источник и точные артефакты

[Официальный релиз v1.13.8](https://github.com/k2-fsa/sherpa-onnx/releases/tag/v1.13.8), опубликован 10 сентября 2026, не prerelease. Tag указывает на commit `11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf`. URL получены из release metadata, скачанные файлы совпали с опубликованными GitHub SHA-256.

| Артефакт | GitHub asset ID | Размер, байт | SHA-256 |
|---|---:|---:|---|
| [Android shared tar](https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.13.8/sherpa-onnx-v1.13.8-android.tar.bz2) | 555165184 | 46 093 321 | `2ff63469a71cb6009aa2e3ed5f4a670f8abdcbe4bb9ffd23776afc792a6b4f44` |
| [Android static-ORT tar](https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.13.8/sherpa-onnx-v1.13.8-android-static-link-onnxruntime.tar.bz2) | 555154992 | 35 101 751 | `7583ca385ae7d981e65468455c2ea2c9f2da383921dccfc5658d0dc19d309e6f` |
| [Android static-ORT AAR](https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.13.8/sherpa-onnx-static-link-onnxruntime-1.13.8.aar) | 555212241 | 38 691 998 | `b22c3fc1b6a45666d28892bb2f7694beeb77a8362d7ebd77c1a5431ec9435471` |

Public asset metadata доступны по `https://api.github.com/repos/k2-fsa/sherpa-onnx/releases/assets/<asset ID>`. Архивы содержат несколько ABI; ниже измерены только arm64 библиотеки. Размер модели в эти числа не входит.

## Shared C API: 16 КиБ проходит, API 23 не проходит

| Библиотека arm64 | Размер, байт | SHA-256 | Android ident |
|---|---:|---|---|
| `libsherpa-onnx-c-api.so` | 4 465 168 | `c85e2382e2ca12b0513826be926eaccfea896b4cbf568182e287671ba526f80d` | API 21, NDK r29 |
| `libonnxruntime.so` | 22 249 560 | `33847ad43bffe204699fd4a27f7f3603452a8cdaf2f9a44983a0bc31ffcf2da1` | API 27, NDK r27d |

Суммарный raw payload C API и ORT: 26 714 728 байт. Все LOAD-сегменты обеих библиотек имеют `p_align=16384`. C API требует `libandroid.so`, `liblog.so`, `libonnxruntime.so`, `libm.so`, `libdl.so`, `libc.so`. ORT требует только системные `libdl.so`, `liblog.so`, `libm.so`, `libc.so`; отдельного `libc++_shared.so` нет.

В ORT обнаружены сильные импорты `__write_chk@LIBC_N` и `__fwrite_chk@LIBC_N`. В штатном arm64 `libc.so` stub из NDK `27.2.12479018` для API 23 этих символов нет; API 24 и 27 их экспортируют. Этого достаточно, чтобы отклонить данный комплект для API 23. Android ident 27 фиксирует цель сборки ORT, но сам по себе не устанавливает точную минимальную рабочую версию Android.

Пример sherpa объявляет minSDK 21, а build script по умолчанию использует `android-21`. Эти настройки не устраняют требования отдельно собранной shared ORT. [Android пример](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/android/SherpaOnnx/app/build.gradle#L10), [скрипт arm64](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/build-android-arm64-v8a.sh#L164).

Проверены реальные C API exports: `CreateOnlineSpeechDenoiser`, `DestroyOnlineSpeechDenoiser`, `OnlineSpeechDenoiserRun`, `Flush`, `Reset`, `GetSampleRate`, `GetFrameShiftInSamples`, `DestroyDenoisedAudio` (все с префиксом `SherpaOnnx`). Публичный API принимает mono float PCM в диапазоне [-1, 1], возвращает выделенный результат, который освобождается отдельной функцией. `Run` не thread-safe; результат может отсутствовать до накопления входа. `Flush` завершает и сбрасывает поток. Частоту и размер шага нужно брать из getters конкретной модели. [Pinned header](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/sherpa-onnx/c-api/c-api.h#L4248), [официальный пример](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/c-api-examples/online-speech-enhancement-gtcrn-c-api.c).

## Static JNI: статическая альтернатива для minSDK 23

В static tar находится одна arm64 библиотека `libsherpa-onnx-jni.so`, 24 169 352 байта, SHA-256 `b4a53d915c19cb6d09b1cdc9a8084be54419b647aab9097ffdfb46f30c3c4dd8`. Arm64 библиотека внутри static AAR совпала побайтно.

- Android ident: API 21, NDK r29. Все три LOAD имеют выравнивание 16 КиБ.
- DT_NEEDED: `libandroid.so`, `liblog.so`, `libm.so`, `libdl.so`, `libc.so`. Внешняя ORT и `libc++_shared.so` не требуются.
- Требования версий системных символов: только `LIBC`, без `LIBC_N` и более новых версий.
- Все 253 уникальных сильных UND-символа разрешаются по объединению этих пяти штатных arm64 stubs для API 23 из NDK `27.2.12479018`. Четыре weak-импорта не считаются обязательными; три отсутствующих имени: `_ZTH15ThreadedBufSize`, `__gcov_dump`, `__gcov_flush`.
- AAR manifest объявляет minSDK 21. Его `classes.jar` содержит `OnlineSpeechDenoiser`, `OnlineSpeechDenoiserConfig`, `OfflineSpeechDenoiserModelConfig`, `OfflineSpeechDenoiserGtcrnModelConfig`, `DenoisedAudio`. `javap` подтвердил Java-callable конструкторы/getters/setters.
- В `.so` есть реальные JNI exports `OnlineSpeechDenoiser_newFromAsset`, `newFromFile`, `run`, `flush`, `reset`, `getSampleRate`, `getFrameShiftInSamples`, `delete` с префиксом `Java_com_k2fsa_sherpa_onnx_`. Строка версии встроенной ORT: `1.28.2`.

Официальный Android AAR использует Kotlin-классы, которые вызываются из Java. Конструктор `OnlineSpeechDenoiser(AssetManager, OnlineSpeechDenoiserConfig)` допускает `null` вместо AssetManager для загрузки из файла. Конфигурация задаёт `gtcrn.model`, `numThreads`, `debug`, `provider`. Доступны `run(float[], int)`, `flush()`, `reset()`, getters частоты/шага и `release()`. Вход и выход копируются в Java/native массивы; выполнение на потоке захвата без замера задержки пока не обосновано. Возможный worker должен последовательно владеть `run/reset/release` и явно освобождать runtime. Desktop Java `LibraryLoader` для Android AAR не нужен. [Pinned Android API](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/sherpa-onnx/kotlin-api/OnlineSpeechDenoiser.kt), [GTCRN config](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/sherpa-onnx/kotlin-api/OfflineSpeechDenoiser.kt), [JNI реализация](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/sherpa-onnx/jni/online-speech-denoiser.cc).

Проверка symbol closure подтверждает статическую линковочную совместимость с API 23. Она не проверяет выполнение конструкторов, динамические `dlopen/dlsym`, качество модели, расход памяти или скорость на телефоне. Статический JNI bundle не экспортирует C API, поэтому заменить им C API `.so` без другого интерфейса нельзя.

## ORT и инвентаризация статического архива

Pinned sherpa CMake использует ORT `1.28.2`, подготовленную maintainer-проектом [csukuangfj/onnxruntime-libs](https://github.com/csukuangfj/onnxruntime-libs/releases/tag/v1.28.2). Это источник prebuilt-зависимости sherpa, отдельно от upstream Microsoft. Версия подтверждена `VERS_1.28.2` у shared C API и строкой `1.28.2` у обеих ORT-сборок.

Shared ORT ZIP из release metadata: [onnxruntime-android-1.28.2.zip](https://github.com/csukuangfj/onnxruntime-libs/releases/download/v1.28.2/onnxruntime-android-1.28.2.zip), asset ID `544593317`, 33 765 715 байт, SHA-256 `01518867f78241138b6aa25925802e843a4fa9085af8d303d49e35bbb52aff4d`. Этот pin совпадает с [sherpa CMake](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/cmake/onnxruntime-android-aarch64.cmake#L17).

Для собственного C API опубликован [arm64 static ORT ZIP](https://github.com/csukuangfj/onnxruntime-libs/releases/download/v1.28.2/onnxruntime-android-arm64-v8a-static_lib-1.28.2.zip), asset ID `542595703`, 229 052 542 байта, SHA-256 `bc68410f35f13df82c260830bf476ee5565f5efd0ec7622297829a929613c6c0`. Файл скачан и его GitHub digest проверен. Внутри один `lib/libonnxruntime.a`, 1 571 443 008 байт; headers также присутствуют. Архив `.a` не распаковывался и не линковался; API-уровень отдельных объектов не установлен. Готовый static JNI показывает совместимый результат линковки, но не заменяет проверку нового C API build. [Pinned static CMake](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/cmake/onnxruntime-android-aarch64-static.cmake#L17).

## Лицензии

Код sherpa-onnx имеет [Apache-2.0](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/LICENSE). Upstream ORT `1.28.2`, commit `33ca9628233dc8f002435e868d4c2e9f82766ca1`, имеет [MIT](https://github.com/microsoft/onnxruntime/blob/33ca9628233dc8f002435e868d4c2e9f82766ca1/LICENSE) и отдельный [ThirdPartyNotices.txt](https://github.com/microsoft/onnxruntime/blob/33ca9628233dc8f002435e868d4c2e9f82766ca1/ThirdPartyNotices.txt). Эти тексты сохранены в ignored evidence. В скачанных sherpa tar и static ORT ZIP полных license/notice файлов нет.

Готовые sherpa библиотеки содержат также TTS/Piper/eSpeak references. Default Android build включает TTS; CMake закрепляет eSpeak fork `ed530aa113046142eb5115cf2fc9157854d0ffe1`, у которого есть GPLv3 `COPYING`, а также отдельные Apache/BSD/Unicode notices. Поэтому лицензия самого sherpa не описывает все включённые компоненты. Перед распространением этого полного runtime нужен состав зависимостей и соответствующие notices/source obligations, либо отдельная проверенная сборка без ненужных TTS-компонентов. [Pinned eSpeak dependency](https://github.com/k2-fsa/sherpa-onnx/blob/11afbd009a7f8c08f4bcf2fc1b265d0df4670fbf/cmake/espeak-ng-for-piper.cmake), [eSpeak COPYING](https://github.com/csukuangfj/espeak-ng/blob/ed530aa113046142eb5115cf2fc9157854d0ffe1/COPYING).

Модель GTCRN и её обученные веса требуют отдельного pin/license review выбранного файла; Android runtime архивы модель не содержат. Этот отчёт не закрывает проверку лицензий всего будущего APK.

## Доказательства и границы

Ignored каталог: `artifacts/qa/sherpa-android-1.13.8/`. Основные файлы:

- `official-release-assets.json`, `source-manifest.json`, `jni-source-manifest.json`;
- `native-inspection.json`, `native/{shared,static}/*.readelf.txt`;
- `api23-stub-control.json`, `static-jni-api23-symbol-closure.json`;
- `static-aar-inspection.json`, `static-aar-AndroidManifest.xml`, `static-aar-java-api.txt`;
- `onnxruntime-release-metadata.json`, `onnxruntime-static-inventory.json`, `onnxruntime-license-manifest.json`, `espeak-license-manifest.json`;
- `summary.json` с явным `runtimeInferenceValidated=false` и `productWiringChanged=false`.

Использованы `llvm-readelf` и arm64 sysroot stubs из NDK `27.2.12479018`, SDK на `/Users/daniel/Library/Android/sdk`, и `javap` из OpenJDK 21. Проверка LOAD выполнена по [инструкции Android для страниц 16 КиБ](https://developer.android.com/guide/practices/page-sizes#elf-alignment). ZIP alignment итогового APK и работа на устройстве здесь не проверялись. Переход к интеграции зависит от отдельной матрицы качества и дальнейшего разрешения Android runtime/licensing вопросов.
