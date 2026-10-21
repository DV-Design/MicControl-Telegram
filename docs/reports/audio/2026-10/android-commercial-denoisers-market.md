# Коммерческое шумоподавление для Android: доступ, ограничения и проверяемость

Дата: 21 октября 2026. Задача: `miccontrol-8sd.1`. Основа приложения — опубликованная Danygramm 1.2, minSDK 23, arm64, поддержка страниц 16 КиБ. Приоритет пользователя — окружающие звуки; сохранение чужой речи допустимо. Продуктовый код, APK и настройки телефона в этом исследовании не менялись.

По доступным данным победитель не выбран. Все четыре SDK заявляют локальную обработку, однако это не означает работу без лицензирующего сервера. Сопоставимых измерений качества и времени обработки на vivo для этих SDK у нас нет. Размер модели, рекламная оценка качества и длительность входного блока не определяют лучший вариант для звонка.

По назначению для следующего сравнения подходят Krisp **RTC Noise Cancellation** и ai-coustics **Rook Multi Speaker**: оба предназначены для человеческих разговоров. Это порядок проверки, а не рейтинг качества. Koala и Just Voice также стоит сравнивать при наличии действующего trial. Доступ к более тяжёлой модели имеет смысл только после проверки сохранения речи и бюджета CPU на телефоне.

## Что подтверждено

| SDK | Обработка и задача | Android / minSDK / 16 КиБ | Доступ для нашего испытания | Наше качество / RTF на Android |
|---|---|---|---|---|
| [Krisp RTC Mobile](https://sdk-docs.krisp.ai/docs/mobile-background-voice-cancellation) | Локальный C SDK; NC для шума, отдельный BVC для других голосов | Android и arm64 в официальном примере. minSDK и ELF 16 КиБ не установлены: сам SDK не получен | SDK и модели выдаются через Developers Portal с разрешённым доступом; крупные модели по запросу | Не измерены |
| [Picovoice Koala 3.0.0](https://picovoice.ai/docs/quick-start/koala-android/) | Локальное потоковое подавление шума, сохранение речи | AAR minSDK 21; arm64 ELF LOAD `0x4000`; 70 сильных импортов разрешаются API 23 stubs | Публичный AAR скачан; для инициализации нужен AccessKey, которого у нас нет | Не измерены |
| [ai-coustics core 0.25.1](https://github.com/ai-coustics/aic-sdk-c/releases/tag/0.25.1) | Локальный CPU SDK; Rook для слушателя, Quail прежде всего для машинной обработки речи | Публичный Android arm64 `.so`, LOAD `0x4000`. Android ident 24; 90 сильных импортов разрешаются API 23 stubs. Поддержка API 23 поставщиком и runtime не подтверждены | Библиотека скачана; нужны учётная запись, лицензия и разрешённая модель. Self-service использует онлайн-авторизацию | Не измерены |
| [Gaudio Just Voice 1.1.2 / fefed85](https://www.gaudiolab.com/products/just-voice) | On-device SDK для окружающего шума | В public trial есть Android arm64 static `.a`; minSDK не указан, итогового ELF для проверки 16 КиБ нет | Публичный пакет скачан. Mac CLI запрашивает ID/PW; единственная обычная сетевая попытка без данных завершилась отказом проверки лицензии | Выходной PCM не получен; качество и RTF не измерены |

ELF-проверка — статическая. Она не проверяет загрузку моделей, работу лицензии, скрытые зависимости через `dlopen`, APK packaging, CPU, нагрев или поведение звонка. API 23 symbol closure сама по себе не заменяет поддержку этой версии поставщиком. Для ai-coustics Android ident 24 сохранён как отдельная неопределённость, а не объявлен доказательством отказа на 23.

## Назначение моделей и задержка

**Krisp.** Нужен RTC SDK для звонков, а не облачный Krisp API и не VIVA для голосовых агентов. [Основная документация](https://sdk-docs.krisp.ai/docs/getting-started) разделяет эти продукты. Mobile C library принимает 48 кГц и другие частоты, обрабатывает 10-мс кадры; Android зависит от OpenBLAS из SDK-пакета. 10 мс — размер кадра, не полная задержка.

В [руководстве моделей](https://sdk-docs.krisp.ai/docs/rtc-model-guide-bvc-nc) обычный outbound NC Pro `krisp-nc-o-pro-v1` занимает 5,8 MB, Med `krisp-nc-o-med-v7` — 5,7 MB и рекомендован для мобильных устройств; более крупные модели выдаются отдельно. Близкий размер файлов не означает близкое потребление CPU. Outbound рассчитан на исходный микрофонный сигнал: предварительное шумоподавление может ухудшить сохранение голоса. BVC уже включает NC, цепочка NC+BVC не рекомендуется; для нашей текущей задачи подавление второстепенных голосов не обязательно. [Пример алгоритмической задержки поставщика](https://sdk-docs.krisp.ai/docs/krisp-rtc-bvc-nc) — около 25 мс при 16 кГц и 10-мс кадрах; это не наше измерение на Android.

**ai-coustics.** [Rook Multi Speaker](https://docs.ai-coustics.com/models/perceptual-speech-enhancement/rook-multi-speaker) ориентирован на естественность и разборчивость слышимого разговора, сохраняет несколько говорящих, доступен small/large на 8/16/48 кГц. Например, `rook-ms-l-48khz` соответствует полнополосному входу. Quail Voice Focus выбирает основной голос по контексту и предназначен прежде всего для voice agents; он не является постоянной идентификацией владельца. [Выбор задач в документации](https://docs.ai-coustics.com/) прямо разделяет эти варианты. Задержку следует получить после настройки через `aic_processor_context_get_audio_delay`, а выполнение измерить отдельно: [официальное описание](https://docs.ai-coustics.com/reference/concepts/latency) не приравнивает эти величины.

**Koala.** В [публичном C header](https://github.com/Picovoice/koala/blob/db6b0822266bc765e3296c3da750137ab18fe8f7/include/pv_koala.h) — mono PCM16, поток последовательных кадров, отдельные getters частоты, размера кадра и задержки. Числовую задержку без инициализированного экземпляра не выдаём за измеренную. Обещания распознавания владельца или гарантированного удаления других говорящих в рассмотренных Koala docs нет.

**Gaudio.** Страница продукта заявляет задержку менее 30 мс и локальную обработку; это оценка поставщика. Trial C API содержит `JV_SETUP`, `JV_PROCESS`, intensity 0…1 и `JV_GET_LATENCY`, но получить результат работающего экземпляра не удалось. Just Voice Lite — отдельное приложение с иным поведением, его описание нельзя использовать как результат SDK.

## Получение trial, сеть и стоимость

| SDK | Конкретный путь доступа и секрет | Что пока мешает | Опубликованная стоимость |
|---|---|---|---|
| Krisp | [Developers Portal](https://developers.krisp.ai/), доступ к Noise Cancellation и Android SDK. Для автоматического скачивания — серверный `KRISP_API_KEY`, не секрет в APK | Нужны разрешённый SDK version ID, библиотека и модели; доступ к самому runtime ещё не получен. Точный runtime licensing/офлайн-режим следует проверить по выданному Android пакету | [Developers Early stage / Enterprise](https://krisp.ai/pricing/) — Apply Now, фиксированная цена Android RTC на странице не указана |
| Koala | [Picovoice Console](https://console.picovoice.ai/), получение AccessKey; предложенное имя секрета проекта `PICOVOICE_ACCESS_KEY` | Нет AccessKey; trial одноразовый. [FAQ](https://picovoice.ai/docs/faq/general/) сейчас не предлагает отдельного плана для личных/некоммерческих проектов | Enterprise quotation; Koala учитывает обработанное аудио по секундам. Публичной числовой цены в рассмотренных docs нет |
| ai-coustics | [Developer platform](https://developers.ai-coustics.com/), SDK key `AIC_SDK_LICENSE` на доверенном backend; распределённый клиент получает короткий JWT (`AIC_SESSION_TOKEN` в примере) | Нет принятого trial/лицензии. Стандартная авторизация и metering требуют сети; offline entitlement оформляется отдельно | [На странице цен](https://ai-coustics.com/pricing): Startup $135/мес при оплате $1 620/год, 100 000 мин/мес; Pro $360 при $4 320/год, 300 000 мин; Business $540 при $6 480/год, 500 000 мин; Enterprise от $2 000/мес |
| Gaudio | [Download SDK на странице продукта](https://www.gaudiolab.com/products/just-voice), затем действующая trial-авторизация от поставщика; имя runtime secret публично не документировано | CLI запрашивает ID/PW, default trial не прошёл online validation. Данных авторизации нет, их подбор не выполнялся | Публичной числовой цены Just Voice SDK не найдено; условия зависят от предложения/договора |

Указанные цены ai-coustics — показанный сайтом **годовой платёж**, пересчитанный в месяц, а не цена свободно отменяемого месячного договора. Налоги и окончательные условия определяются покупкой. [Trial документация](https://docs.ai-coustics.com/models/get-started/pricing) предлагает 30 дней после создания аккаунта; аккаунт здесь не создавался. Модели учитываются отдельно: два процессора на одном аудио могут расходовать две квоты минут.

[Krisp download API](https://sdk-docs.krisp.ai/docs/programmatic-sdk-model-downloads-api) требует API key и version ID из SDK dashboard. Открытый [WebRTC Android bridge](https://sdk-docs.krisp.ai/docs/webrtc-android) сам Krisp SDK не содержит. Доступ к облачному API или скачивание bridge не подтверждает права и доступ к Mobile RTC runtime. [Browser quickstart](https://sdk-docs.krisp.ai/docs/quickstart-browser-sdk) описывает запрос доступа в Noise Cancellation; точные условия Android нужно получить для этого продукта.

[README Koala](https://github.com/Picovoice/koala/tree/db6b0822266bc765e3296c3da750137ab18fe8f7) прямо требует интернет для проверки AccessKey, хотя аудио обрабатывается локально. Сроки повторной проверки и гарантированный длительный офлайн-режим здесь не проверены. У [ai-coustics](https://docs.ai-coustics.com/models/get-started/authenticate-apps) ключи обычного тарифа используют онлайн-авторизацию и отчётность. [Документация telemetry](https://docs.ai-coustics.com/reference/concepts/sdk-telemetry) сообщает, что эти каналы не передают PCM; `DO_NOT_TRACK=1` отключает error reporting, но не авторизацию/метринг и не даёт офлайн-лицензию. Долгоживущие ключи не нужно отправлять в чат или включать в публичный APK.

## Реальная попытка Gaudio

Скачан trial archive по ссылке с официальной страницы, без аккаунта. В 36 файлах пакета отдельный LICENSE/EULA не найден; header содержит all rights reserved. Страница приглашает пробовать SDK, но это не определяет права публичного распространения. [Общие условия Gaudio](https://www.gaudiolab.com/gaudio-studio/docs/terms) допускают отдельные соглашения для developer SDK; условий default-авторизации этого trial в пакетных guides нет.

Использован штатный Mac arm64 `just_voice_cli`, без модификации. `--version` вернул `v1.1.2 (fefed85)`. Один публичный `clean_A` из сохранённой исследовательской матрицы преобразован из FloatS16 в mono FLOAT WAV 48 кГц без нормализации уровня. Параметры: 480 samples/block, intensity 1.0, stdin `DEVNULL`.

Сначала запуск с явным запретом сети завершился exit 1. Затем выполнена **одна обычная сетевая попытка** с тем же fixture и без введённых ID/PW. За 2,085 с утилита завершилась exit 1: `ID: PW: Online validation for license failed.` Выходного файла нет. Таким образом, отказ не объяснён только нашим firewall; точная причина отказа лицензирующего сервера без выданных данных неизвестна. Никакие лицензионные проверки не обходились. До обработки остальных fixtures не дошли; это не оценка качества модели или её RTF.

Доказательства: `artifacts/qa/commercial-denoisers/gaudio/clean_A-smoke.json`, `artifacts/qa/commercial-denoisers/gaudio/clean_A-online-smoke.json`, `artifacts/qa/commercial-denoisers/gaudio/clean_A-online-cli.log`. Публичный входной PCM SHA-256 `9af583b305b386309ea0db8502d3b48882d9f224128a6fc8c1639e444f3fbbc0`. Пользовательское аудио не использовано, вход в аккаунты не выполнялся.

## Лицензия и публичный Telegram APK

Унаследованный [LICENSE](../../../../LICENSE) — GNU GPLv2, а [ApplicationLoader.java](../../../../TMessagesProj/src/main/java/org/telegram/messenger/ApplicationLoader.java) объявляет GPLv2-or-later. Для распространения связанного APK нужно отдельно установить совместимость **всего** SDK, модели и условий получателей с GPL либо получить надлежащие права/исключения. Одна коммерческая подписка и доступность `.so` этого не доказывают. Мы не можем выдать исключение за чужой upstream copyright: это прямо разбирает [GNU GPL FAQ](https://www.gnu.org/licenses/gpl-faq.en.html#GPLIncompatibleLibs).

Это существенный нерешённый вопрос распространения, а не утверждение, что любой закрытый SDK всегда незаконен. Отдельная standalone оценка trial и публикация SDK внутри изменённого Telegram — разные действия с разными условиями.

Для ai-coustics есть ещё конкретные ограничения: [Model License v2.0](https://ai-coustics.com/legal/model-license), §3, требует ограничить извлечение, модификацию и отдельное распространение модели получателями; §5 разрешает внутренние benchmarks в рамках лицензии, но внешняя публикация результатов/сравнения требует письменного согласия. Эти условия нужно согласовать до публичного comparative report с результатами модели. SDK и model license не следует смешивать с лицензией примеров/обёрток. [Terms v2.0](https://ai-coustics.com/legal/terms) отдельно связывает использование с trial/Plan/Order и онлайн-лицензированием.

У Koala публичный [repository LICENSE](https://github.com/Picovoice/koala/blob/db6b0822266bc765e3296c3da750137ab18fe8f7/LICENSE) — Apache 2.0, а бизнес-документация описывает проприетарный движок и AccessKey. Наличие открытых bindings не устанавливает наличие соответствующего исходного кода и всех прав для полного binary/model payload в GPL APK. Проверка этой границы остаётся открытой; в этом исследовании лицензионное исключение для Danygramm не получено.

## Пины скачанных SDK и статическое доказательство

| Артефакт | Размер, байт | SHA-256 |
|---|---:|---|
| [Koala Android 3.0.0 AAR](https://repo.maven.apache.org/maven2/ai/picovoice/koala-android/3.0.0/koala-android-3.0.0.aar) | 4 094 473 | `dc532251a76e90943d3fcc20e89e335f69e4401625e0df660af238bdaf3be4ba` |
| Koala `libpv_koala.so`, arm64 | 215 904 | `815f5af7f547d38d3329e374445e2021eec32a9734909d34c27275f343ba97c2` |
| [ai-coustics Android arm64 0.25.1 tar](https://github.com/ai-coustics/aic-sdk-c/releases/download/0.25.1/aic-sdk-aarch64-linux-android-0.25.1.tar.gz) | 6 249 489 | `7fdc017b27b8ac4661ab2413a1e16f65c10c8cf0d6d3d4dc53ef69bc580b0c0d` |
| ai-coustics `libaic.so`, arm64 | 4 097 784 | `cc6903b0cdaded924b68021f5d359e0f12510aa9499cacc60a31080ab3887407` |
| Gaudio trial full package `v1.1.2-fefed85` | 192 162 932 | `259fce71137a1993681f754678eee02e87da346213bf9551756900fb206bffae` |
| Gaudio Android arm64 static `libjust_voice.a` | 9 390 204 | `5353864d62b9dfb0f0b45b762df83b32e434c6b3061007914632a49c284100bf` |

Koala AAR содержит модель `koala_params.pv` размером 4 007 743 байта; arm64 native+model raw payload — 4 223 647 байт. Его системные зависимости: `liblog`, `libm`, `libdl`, `libc`; Android ident 21. ai-coustics `.so` требует `libdl`, `libm`, `libc`, отдельной ORT `.so` в этом пакете нет; размер конкретной модели в число 4 097 784 не входит. Android ident — 24/NDK r25c. Для обоих библиотек сохранены LOAD, DT_NEEDED, symbol versions и сравнение с NDK `27.2.12479018` API 21/23/24. У ai-coustics два weak imports, включая отсутствующий в API 23 `getrandom`; сильного неразрешённого импорта для 23 не найдено. Гарантию runtime из этого не выводим.

Пути: `artifacts/qa/commercial-denoisers/koala/aar.json`, `artifacts/qa/commercial-denoisers/aicoustics/inventory.json`, `artifacts/qa/commercial-denoisers/api-stub-closure.json`, `artifacts/qa/commercial-denoisers/gaudio/download.json`. Копии SDK и PCM находятся в ignored `artifacts/qa/commercial-denoisers/`; они не добавлялись в Git. Для Gaudio static archive итоговый Android ELF не линковался, поэтому требования shared dependencies и 16-КиБ выравнивание финального runtime ещё не установлены.

## Что требуется для выбора

Для обоснованного выбора нужны действующий разрешённый trial, точный model ID/revision и права на его проверку; затем один и тот же набор чистой речи, смесей, коротких начал слов и возврата речи после шума. Задержка фиксируется независимо от качества, выходы сохраняют исходный уровень и длительность. Проверка должна включать время на блок p50/p95/p99, sustained RTF, память и пропуски на реальном vivo. Рекламные «real time» и шум в паузе не заменяют проверку сохранения речи.

Пока подтверждены пути получения SDK, часть Android binary compatibility и реальные ограничения доступа. Готового победителя рынка, исправления звука Danygramm или работоспособности этих моделей в публичном APK этот отчёт не устанавливает. Авторизации и контактов с поставщиками, покупок, UI/adb/device-тестов и новых сборок приложения не было.
