// Danygramm: JNI bridge between org.telegram.messenger.DanygrammTranscriber and whisper.cpp.
// One model context is kept loaded; calls are serialized on the Java side (single worker thread).

#include <jni.h>
#include <android/log.h>
#include <atomic>
#include <mutex>
#include <string>
#include <thread>
#include <algorithm>
#include "whisper.h"

#define DANY_TAG "DanyWhisper"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, DANY_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, DANY_TAG, __VA_ARGS__)

namespace {
std::mutex g_lock;
whisper_context *g_ctx = nullptr;
std::string g_model_path;
std::atomic<bool> g_abort{false};

bool abort_requested(void *) {
    return g_abort.load();
}

void quiet_log(enum ggml_log_level level, const char *text, void *) {
    if (level == GGML_LOG_LEVEL_ERROR) {
        __android_log_write(ANDROID_LOG_ERROR, DANY_TAG, text);
    }
}

std::string to_std(JNIEnv *env, jstring value) {
    if (value == nullptr) return {};
    const char *chars = env->GetStringUTFChars(value, nullptr);
    if (chars == nullptr) return {};
    std::string result(chars);
    env->ReleaseStringUTFChars(value, chars);
    return result;
}

// whisper may cut a multi-byte UTF-8 sequence at a token boundary; NewStringUTF rejects invalid
// (and 4-byte) sequences, so build the Java string from UTF-16 ourselves.
jstring to_java(JNIEnv *env, const std::string &utf8) {
    std::u16string out;
    out.reserve(utf8.size());
    size_t i = 0;
    while (i < utf8.size()) {
        unsigned char c = (unsigned char) utf8[i];
        uint32_t cp;
        size_t len;
        if (c < 0x80) { cp = c; len = 1; }
        else if ((c >> 5) == 0x6) { cp = c & 0x1F; len = 2; }
        else if ((c >> 4) == 0xE) { cp = c & 0x0F; len = 3; }
        else if ((c >> 3) == 0x1E) { cp = c & 0x07; len = 4; }
        else { i++; continue; }
        if (i + len > utf8.size()) break;
        bool ok = true;
        for (size_t k = 1; k < len; k++) {
            unsigned char cc = (unsigned char) utf8[i + k];
            if ((cc >> 6) != 0x2) { ok = false; break; }
            cp = (cp << 6) | (cc & 0x3F);
        }
        if (!ok) { i++; continue; }
        i += len;
        if (cp >= 0x10000) {
            cp -= 0x10000;
            out.push_back((char16_t) (0xD800 + (cp >> 10)));
            out.push_back((char16_t) (0xDC00 + (cp & 0x3FF)));
        } else {
            out.push_back((char16_t) cp);
        }
    }
    return env->NewString(reinterpret_cast<const jchar *>(out.data()), (jsize) out.size());
}
}

extern "C" JNIEXPORT jboolean JNICALL
Java_org_telegram_messenger_DanygrammTranscriber_nativeLoadModel(JNIEnv *env, jclass, jstring path) {
    std::lock_guard<std::mutex> guard(g_lock);
    std::string model = to_std(env, path);
    if (g_ctx != nullptr && g_model_path == model) {
        return JNI_TRUE;
    }
    if (g_ctx != nullptr) {
        whisper_free(g_ctx);
        g_ctx = nullptr;
        g_model_path.clear();
    }
    whisper_log_set(quiet_log, nullptr);
    whisper_context_params params = whisper_context_default_params();
    params.use_gpu = false;
    params.flash_attn = true;
    g_ctx = whisper_init_from_file_with_params(model.c_str(), params);
    if (g_ctx == nullptr) {
        LOGE("failed to load model");
        return JNI_FALSE;
    }
    g_model_path = model;
    LOGI("model loaded, whisper %s", WHISPER_VERSION);
    return JNI_TRUE;
}

extern "C" JNIEXPORT void JNICALL
Java_org_telegram_messenger_DanygrammTranscriber_nativeUnloadModel(JNIEnv *, jclass) {
    std::lock_guard<std::mutex> guard(g_lock);
    if (g_ctx != nullptr) {
        whisper_free(g_ctx);
        g_ctx = nullptr;
    }
    g_model_path.clear();
}

extern "C" JNIEXPORT void JNICALL
Java_org_telegram_messenger_DanygrammTranscriber_nativeAbort(JNIEnv *, jclass) {
    g_abort.store(true);
}

// Returns "<lang>\n<text>" or null on failure/abort. language: ISO code or "auto".
extern "C" JNIEXPORT jstring JNICALL
Java_org_telegram_messenger_DanygrammTranscriber_nativeTranscribe(JNIEnv *env, jclass, jfloatArray pcm, jstring language, jint threads) {
    std::lock_guard<std::mutex> guard(g_lock);
    if (g_ctx == nullptr || pcm == nullptr) {
        return nullptr;
    }
    g_abort.store(false);
    const jsize count = env->GetArrayLength(pcm);
    jfloat *samples = env->GetFloatArrayElements(pcm, nullptr);
    if (samples == nullptr) {
        return nullptr;
    }
    std::string lang = to_std(env, language);
    if (lang.empty()) lang = "auto";

    whisper_full_params params = whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    params.n_threads = std::max(1, std::min((int) threads, 8));
    params.language = lang.c_str();
    params.detect_language = false;
    params.translate = false;
    params.no_context = true;
    params.no_timestamps = true;
    params.print_progress = false;
    params.print_realtime = false;
    params.print_special = false;
    params.print_timestamps = false;
    params.suppress_blank = true;
    params.suppress_nst = true;
    params.abort_callback = abort_requested;
    params.abort_callback_user_data = nullptr;

    int rc = whisper_full(g_ctx, params, samples, count);
    env->ReleaseFloatArrayElements(pcm, samples, JNI_ABORT);
    if (rc != 0 || g_abort.load()) {
        LOGE("whisper_full failed: %d", rc);
        return nullptr;
    }
    std::string text;
    const int segments = whisper_full_n_segments(g_ctx);
    for (int i = 0; i < segments; i++) {
        const char *segment = whisper_full_get_segment_text(g_ctx, i);
        if (segment != nullptr) text += segment;
    }
    const char *detected = whisper_lang_str(whisper_full_lang_id(g_ctx));
    std::string result = std::string(detected != nullptr ? detected : "") + "\n" + text;
    return to_java(env, result);
}
