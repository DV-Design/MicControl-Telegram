// Isolated performance diagnostic. Uses the existing engine without changing it.
#include "TargetVoiceInference.h"

#include <jni.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <locale>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/resource.h>
#include <unistd.h>

#ifndef VOICE_PROBE_ENGINE_SHA256
#error Build must identify the measured engine source
#endif

namespace {
using Clock = std::chrono::steady_clock;
using miccontrol::TargetVoiceInference;
constexpr std::size_t kSamples = 64000, kChunk = 640, kBlocks = 100;
struct Cancelled {};

void Require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
void Check(miccontrol::TargetVoiceStatus status) {
    if (!status.ok()) throw std::runtime_error(status.message());
}
double Milliseconds(Clock::time_point start) {
    return std::chrono::duration<double, std::milli>(Clock::now() - start).count();
}
struct Utf {
    JNIEnv* env;
    jstring value;
    const char* text;
    Utf(JNIEnv* env, jstring value) : env(env), value(value), text(value ? env->GetStringUTFChars(value, nullptr) : nullptr) {}
    ~Utf() { if (text) env->ReleaseStringUTFChars(value, text); }
};
struct Progress {
    JNIEnv* env;
    jobject token;
    jmethodID cancelled;
    jfieldID phase, completed;
    void CheckCancelled() const {
        const bool requested = env->CallBooleanMethod(token, cancelled);
        Require(!env->ExceptionCheck(), "Cancellation callback failed");
        if (requested) throw Cancelled{};
    }
    void Phase(int value) const { env->SetIntField(token, phase, value); }
    void Completed(int value) const { env->SetIntField(token, completed, value); }
};
std::vector<float> Read(const char* path, std::size_t count) {
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    Require(input.good() && input.tellg() == static_cast<std::streamoff>(count * sizeof(float)), "Wrong test sample length");
    input.seekg(0);
    std::vector<float> result(count);
    input.read(reinterpret_cast<char*>(result.data()), static_cast<std::streamsize>(count * sizeof(float)));
    Require(input.good(), "Cannot read bundled test samples");
    for (const float x : result) Require(std::isfinite(x) && std::abs(x) <= 1, "Test samples must be finite normalized Float32");
    return result;
}
double Percentile(const std::vector<double>& values, double fraction) {
    const double index = (values.size() - 1) * fraction;
    const auto low = static_cast<std::size_t>(index);
    const auto high = std::min(low + 1, values.size() - 1);
    return values[low] + (values[high] - values[low]) * (index - low);
}
std::string Escape(const char* text) {
    std::string result;
    for (const unsigned char c : std::string(text)) {
        if (c == '"' || c == '\\') result += '\\';
        result += c >= 32 && c < 127 ? static_cast<char>(c) : '?';
    }
    return result;
}
std::string Run(const char* enroll_path, const char* chunk_path, const char* reference_path,
                const char* mixture_path, const Progress& progress) {
    progress.CheckCancelled();
    const auto reference = Read(reference_path, 48000);
    const auto mixture = Read(mixture_path, kSamples);
    miccontrol::TargetVoiceInference inference;
    miccontrol::TargetVoiceOptions options;
    options.intra_op_threads = 2;
    progress.Phase(1);
    auto start = Clock::now();
    Check(inference.LoadModel(enroll_path, chunk_path, options));
    const double load_ms = Milliseconds(start);
    progress.CheckCancelled();
    progress.Phase(2);
    miccontrol::TargetVoiceProfile profile;
    start = Clock::now();
    Check(inference.Enroll(reference.data(), reference.size(), &profile));
    const double enroll_ms = Milliseconds(start);
    progress.CheckCancelled();
    std::unique_ptr<miccontrol::TargetVoiceStream> stream;
    Check(inference.CreateStream(profile, &stream));
    profile = {};
    std::array<float, kChunk> output{};
    std::vector<double> times;
    times.reserve(kBlocks);
    double compute_ms = 0, squared = 0;
    std::size_t total_output = 0;
    auto consume = [&](std::size_t count) {
        for (std::size_t i = 0; i < count; ++i) {
            Require(std::isfinite(output[i]), "Non-finite model output");
            squared += static_cast<double>(output[i]) * output[i];
        }
        total_output += count;
    };
    progress.Phase(3);
    const auto wall_start = Clock::now();
    for (std::size_t block = 0; block < kBlocks; ++block) {
        progress.CheckCancelled();
        std::size_t count = 0;
        start = Clock::now();
        Check(stream->Push(mixture.data() + block * kChunk, kChunk,
                           output.data(), output.size(), &count));
        const double elapsed = Milliseconds(start);
        Require(count == (block == 0 ? 256 : kChunk), "Unexpected Push sample count");
        times.push_back(elapsed);
        compute_ms += elapsed;
        consume(count);
        progress.Completed(static_cast<int>(block + 1));
    }
    progress.CheckCancelled();
    progress.Phase(4);
    std::size_t flush_count = 0;
    start = Clock::now();
    Check(stream->Flush(output.data(), output.size(), &flush_count));
    const double flush_ms = Milliseconds(start);
    compute_ms += flush_ms;
    Require(flush_count == 384, "Unexpected Flush sample count");
    consume(flush_count);
    const double wall_ms = Milliseconds(wall_start);
    Require(total_output == kSamples && squared > 1e-10, "Missing or empty test output");
    progress.CheckCancelled();
    std::sort(times.begin(), times.end());
    struct rusage usage{};
    Require(getrusage(RUSAGE_SELF, &usage) == 0, "Cannot measure process peak RSS");
    std::ostringstream json;
    json.imbue(std::locale::classic());
    json << std::setprecision(10) << "{\"status\":\"ok\",\"runtime_version\":\""
         << TargetVoiceInference::RuntimeVersion() << "\",\"engine_sha256\":\"" << VOICE_PROBE_ENGINE_SHA256
         << "\",\"sample_rate\":16000,\"audio_seconds\":4,\"threads\":2,\"input_samples\":64000"
         << ",\"profile_samples\":48000,\"output_samples\":" << total_output
         << ",\"finite\":true,\"chunk_count\":100,\"first_output_count\":256,\"steady_output_count\":640"
         << ",\"flush_output_count\":" << flush_count << ",\"load_ms\":" << load_ms
         << ",\"enroll_ms\":" << enroll_ms << ",\"flush_ms\":" << flush_ms
         << ",\"run_total_ms\":" << compute_ms << ",\"wall_processing_ms\":" << wall_ms
         << ",\"rtf\":" << compute_ms / 4000 << ",\"wall_rtf\":" << wall_ms / 4000
         << ",\"p50_ms\":" << Percentile(times, .5) << ",\"p95_ms\":" << Percentile(times, .95)
         << ",\"p99_ms\":" << Percentile(times, .99) << ",\"max_ms\":" << times.back()
         << ",\"output_rms\":" << std::sqrt(squared / kSamples)
         << ",\"process_peak_rss_kib\":" << usage.ru_maxrss
         << ",\"page_size_bytes\":" << sysconf(_SC_PAGESIZE)
         << ",\"rss_scope\":\"whole_process_peak_including_UI_and_prior_runs\"}";
    return json.str();
}
} // namespace

extern "C" JNIEXPORT jstring JNICALL
Java_org_danygramm_voiceprobe_NativeProbe_run(JNIEnv* env, jclass, jstring enroll, jstring chunk,
                                             jstring reference, jstring mixture, jobject token) {
    try {
        Require(token && enroll && chunk && reference && mixture, "Missing diagnostic argument");
        jclass cls = env->GetObjectClass(token);
        Progress progress{env, token, env->GetMethodID(cls, "isCancelled", "()Z"),
                env->GetFieldID(cls, "phase", "I"), env->GetFieldID(cls, "completedBlocks", "I")};
        env->DeleteLocalRef(cls);
        if (env->ExceptionCheck()) return nullptr;
        Utf enrollment(env, enroll), model(env, chunk), owner(env, reference), input(env, mixture);
        if (env->ExceptionCheck()) return nullptr;
        Require(enrollment.text && model.text && owner.text && input.text, "Cannot read diagnostic paths");
        const auto result = Run(enrollment.text, model.text, owner.text, input.text, progress);
        return env->NewStringUTF(result.c_str());
    } catch (const Cancelled&) {
        return env->NewStringUTF("{\"status\":\"cancelled\"}");
    } catch (const std::exception& error) {
        if (env->ExceptionCheck()) return nullptr;
        const std::string result = "{\"status\":\"error\",\"detail\":\"" + Escape(error.what()) + "\"}";
        return env->NewStringUTF(result.c_str());
    } catch (...) {
        if (env->ExceptionCheck()) return nullptr;
        return env->NewStringUTF("{\"status\":\"error\",\"detail\":\"Unknown native failure\"}");
    }
}
