// Real-model diagnostic for the portable TargetVoiceInference backend.
// No microphone, account access or inference substitutes. See --help.
#include "TargetVoiceInference.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/resource.h>

namespace {
using Clock = std::chrono::steady_clock;
using miccontrol::TargetVoiceInference;
using miccontrol::TargetVoiceProfile;
using miccontrol::TargetVoiceStatus;
using miccontrol::TargetVoiceStream;
constexpr std::size_t kChunk = TargetVoiceInference::kChunkSamples;

void Require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
void Check(TargetVoiceStatus status) {
    if (!status.ok()) throw std::runtime_error(status.message());
}
double Milliseconds(Clock::time_point start) {
    return std::chrono::duration<double, std::milli>(Clock::now() - start).count();
}
std::vector<float> ReadF32(const std::string& path) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    Require(file.good(), "Cannot open Float32 input");
    const auto length = file.tellg();
    Require(length > 0 && length % 4 == 0, "Input must contain complete, nonempty LE Float32 samples");
    Require(static_cast<std::uint64_t>(length) <= 1024ULL * 1024 * 1024, "Probe input exceeds 1 GiB");
    file.seekg(0);
    std::vector<float> samples(static_cast<std::size_t>(length) / 4);
    for (auto& sample : samples) {
        std::array<unsigned char, 4> bytes{};
        file.read(reinterpret_cast<char*>(bytes.data()), 4);
        const std::uint32_t bits = static_cast<std::uint32_t>(bytes[0]) |
            (static_cast<std::uint32_t>(bytes[1]) << 8) |
            (static_cast<std::uint32_t>(bytes[2]) << 16) |
            (static_cast<std::uint32_t>(bytes[3]) << 24);
        std::memcpy(&sample, &bits, 4);
    }
    Require(file.good(), "Cannot read Float32 input");
    return samples;
}
void WriteF32(const std::string& path, const std::vector<float>& samples) {
    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    Require(file.good(), "Cannot open Float32 output");
    for (const auto sample : samples) {
        std::uint32_t bits = 0;
        std::memcpy(&bits, &sample, 4);
        const std::array<unsigned char, 4> bytes{
            static_cast<unsigned char>(bits), static_cast<unsigned char>(bits >> 8),
            static_cast<unsigned char>(bits >> 16), static_cast<unsigned char>(bits >> 24)};
        file.write(reinterpret_cast<const char*>(bytes.data()), 4);
    }
    file.close();
    Require(!file.fail(), "Cannot finish Float32 output");
}
struct Stats {
    std::vector<double> chunks;
    double run_total_ms = 0.0, flush_ms = 0.0;
    std::size_t first_output = 0, steady_output = 0;
};
std::vector<float> Run(TargetVoiceStream* stream, const std::vector<float>& mixture, Stats* stats) {
    std::vector<float> result;
    result.reserve(mixture.size() + kChunk);
    stats->chunks.reserve((mixture.size() + kChunk - 1) / kChunk);
    std::array<float, kChunk> input{}, output{};
    for (std::size_t offset = 0; offset < mixture.size(); offset += kChunk) {
        input.fill(0.0f);
        std::copy_n(mixture.data() + offset, std::min(kChunk, mixture.size() - offset), input.data());
        std::size_t count = 0;
        const auto start = Clock::now();
        Check(stream->Push(input.data(), input.size(), output.data(), output.size(), &count));
        const double elapsed = Milliseconds(start);
        Require(count == (offset == 0 ? 256 : kChunk), "Unexpected Push output length");
        stats->chunks.push_back(elapsed);
        stats->run_total_ms += elapsed;
        if (offset == 0) stats->first_output = count;
        else stats->steady_output = count;
        result.insert(result.end(), output.begin(), output.begin() + count);
    }
    std::size_t count = 0;
    const auto start = Clock::now();
    Check(stream->Flush(output.data(), output.size(), &count));
    stats->flush_ms = Milliseconds(start);
    stats->run_total_ms += stats->flush_ms;
    Require(count == 384, "Unexpected Flush output length");
    result.insert(result.end(), output.begin(), output.begin() + count);
    Require(result.size() >= mixture.size(), "Stream dropped samples");
    result.resize(mixture.size());
    for (const float value : result) Require(std::isfinite(value), "Non-finite output");
    return result;
}
void ValidationChecks(TargetVoiceStream* stream) {
    std::array<float, kChunk> input{}, output{};
    std::size_t count = 99;
    auto status = stream->Push(nullptr, kChunk, output.data(), output.size(), &count);
    Require(status.code == TargetVoiceStatus::Code::kInvalidArgument && count == 0, "Null input accepted");
    status = stream->Push(input.data(), kChunk - 1, output.data(), output.size(), &count);
    Require(status.code == TargetVoiceStatus::Code::kInvalidArgument && count == 0, "Short input accepted");
    status = stream->Push(input.data(), kChunk, output.data(), output.size() - 1, &count);
    Require(status.code == TargetVoiceStatus::Code::kInvalidArgument && count == 0, "Short output accepted");
    input[3] = std::numeric_limits<float>::quiet_NaN();
    status = stream->Push(input.data(), kChunk, output.data(), output.size(), &count);
    Require(status.code == TargetVoiceStatus::Code::kInvalidArgument && count == 0, "NaN input accepted");
    input[3] = 1.01f;
    status = stream->Push(input.data(), kChunk, output.data(), output.size(), &count);
    Require(status.code == TargetVoiceStatus::Code::kInvalidArgument && count == 0, "Unnormalized input accepted");
    Check(stream->Flush(output.data(), output.size(), &count));
    Require(count == 0, "Empty flush produced samples");
    input[3] = 0;
    Require(stream->Push(input.data(), kChunk, output.data(), output.size(), &count).code ==
            TargetVoiceStatus::Code::kStreamFinished, "Push after Flush accepted");
    stream->Reset();
}
double MaxDifference(const std::vector<float>& a, const std::vector<float>& b, double* rms = nullptr) {
    Require(a.size() == b.size(), "Comparison waveform length differs");
    double maximum = 0, squared = 0;
    for (std::size_t i = 0; i < a.size(); ++i) {
        Require(std::isfinite(b[i]), "Non-finite comparison waveform");
        const double diff = static_cast<double>(a[i]) - b[i];
        maximum = std::max(maximum, std::abs(diff));
        squared += diff * diff;
    }
    if (rms) *rms = std::sqrt(squared / a.size());
    return maximum;
}
double Percentile(const std::vector<double>& sorted, double percentile) {
    const double index = (sorted.size() - 1) * percentile;
    const std::size_t lower = static_cast<std::size_t>(index);
    const std::size_t upper = std::min(lower + 1, sorted.size() - 1);
    return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower);
}
void Usage() {
    std::puts("target_voice_probe --enroll-model enroll.onnx --chunk-model chunk_int8_full.onnx\n"
              "  --profile owner.f32 --mixture mixture.f32 --output extracted.f32\n"
              "  [--threads 4] [--reset-check] [--expected python.f32] [--max-abs-diff 0.00002]\n"
              "All audio is raw little-endian normalized Float32, mono, 16 kHz.\n"
              "Profile: exactly 48000 samples. Mixture: any positive length.\n"
              "JSON timings cover Push+Flush; model loading/enrollment are separate.\n"
              "This is a diagnostic, with no owner-absence guarantee or live call integration.");
}
}  // namespace

int main(int argc, char** argv) {
    try {
        std::string enroll_model, chunk_model, reference_path, mixture_path, output_path, expected_path;
        miccontrol::TargetVoiceOptions options;
        bool reset_check = false;
        double tolerance = 0.00002;
        for (int i = 1; i < argc; ++i) {
            const std::string arg(argv[i]);
            if (arg == "--help") { Usage(); return 0; }
            if (arg == "--reset-check") { reset_check = true; continue; }
            Require(i + 1 < argc, "Missing argument value");
            const std::string value(argv[++i]);
            if (arg == "--enroll-model") enroll_model = value;
            else if (arg == "--chunk-model") chunk_model = value;
            else if (arg == "--profile") reference_path = value;
            else if (arg == "--mixture") mixture_path = value;
            else if (arg == "--output") output_path = value;
            else if (arg == "--expected") expected_path = value;
            else if (arg == "--threads") {
                std::size_t used = 0;
                options.intra_op_threads = std::stoi(value, &used);
                Require(used == value.size(), "Invalid --threads");
            } else if (arg == "--max-abs-diff") {
                std::size_t used = 0;
                tolerance = std::stod(value, &used);
                Require(used == value.size() && std::isfinite(tolerance) && tolerance >= 0, "Invalid tolerance");
            } else throw std::runtime_error("Unknown argument: " + arg);
        }
        Require(!enroll_model.empty() && !chunk_model.empty() && !reference_path.empty() &&
                !mixture_path.empty() && !output_path.empty(), "Required argument missing; use --help");
        Require(output_path != reference_path && output_path != mixture_path && output_path != expected_path,
                "Output must not overwrite a probe input");
        const auto reference = ReadF32(reference_path);
        const auto mixture = ReadF32(mixture_path);
        TargetVoiceProfile profile;
        std::unique_ptr<TargetVoiceStream> stream;
        double load_ms = 0, enroll_ms = 0;
        {
            TargetVoiceInference inference;
            auto start = Clock::now();
            Check(inference.LoadModel(enroll_model.c_str(), chunk_model.c_str(), options));
            load_ms = Milliseconds(start);
            if (reset_check) {
                TargetVoiceProfile invalid;
                const std::vector<float> silence(TargetVoiceInference::kEnrollmentSamples);
                Require(inference.Enroll(silence.data(), silence.size(), &invalid).code ==
                        TargetVoiceStatus::Code::kInvalidArgument && !invalid.valid(), "Silent profile accepted");
                Require(inference.Enroll(reference.data(), 1, &invalid).code ==
                        TargetVoiceStatus::Code::kInvalidArgument && !invalid.valid(), "Short profile accepted");
            }
            start = Clock::now();
            Check(inference.Enroll(reference.data(), reference.size(), &profile));
            enroll_ms = Milliseconds(start);
            Check(inference.CreateStream(profile, &stream));
        }  // Exercise stream lifetime after inference destruction.
        const auto mag_shape = profile.magnitude_shape(), context_shape = profile.context_shape();
        profile = {};  // The stream also retains its immutable derived profile.
        if (reset_check) ValidationChecks(stream.get());
        Stats stats;
        const auto result = Run(stream.get(), mixture, &stats);
        double reset_diff = 0, golden_diff = 0, golden_rms = 0;
        if (reset_check) {
            stream->Reset();
            std::array<float, kChunk> input{}, output{};
            std::copy_n(mixture.data(), std::min(kChunk, mixture.size()), input.data());
            std::size_t count = 0;
            Check(stream->Push(input.data(), input.size(), output.data(), output.size(), &count));
            stream->Reset();  // Discard an active recurrent state, not just a finished stream.
            Stats repeat_stats;
            reset_diff = MaxDifference(result, Run(stream.get(), mixture, &repeat_stats));
            Require(reset_diff <= tolerance, "Reset changed the extracted waveform");
        }
        if (!expected_path.empty()) {
            golden_diff = MaxDifference(result, ReadF32(expected_path), &golden_rms);
            Require(golden_diff <= tolerance, "Output differs from the Python golden waveform");
        }
        WriteF32(output_path, result);
        auto times = stats.chunks;
        std::sort(times.begin(), times.end());
        double total = 0;
        for (const auto value : times) total += value;
        struct rusage usage{};
        Require(getrusage(RUSAGE_SELF, &usage) == 0, "getrusage failed");
        long peak_rss_kib = usage.ru_maxrss;
#if defined(__APPLE__)
        peak_rss_kib /= 1024;
#endif
        std::printf("{\"runtime_version\":\"%s\",\"sample_rate\":16000,\"profile_samples\":%zu,"
            "\"input_samples\":%zu,\"output_samples\":%zu,\"threads\":%d,"
            "\"magnitude_shape\":[%lld,%lld,%lld],\"context_shape\":[%lld,%lld,%lld],"
            "\"chunk_input_shape_first\":[1,896],\"chunk_input_shape_steady\":[1,1024],"
            "\"frame_output_shape_first\":[1,4,512],\"frame_output_shape_steady\":[1,5,512],"
            "\"state_shape\":[6,32,256],\"load_ms\":%.6f,\"enroll_ms\":%.6f,"
            "\"chunk_count\":%zu,\"first_output_count\":%zu,\"steady_output_count\":%zu,"
            "\"flush_ms\":%.6f,\"run_total_ms\":%.6f,\"mean_ms\":%.6f,\"p50_ms\":%.6f,"
            "\"p95_ms\":%.6f,\"p99_ms\":%.6f,\"max_ms\":%.6f,\"rtf\":%.6f,"
            "\"peak_rss_kib\":%ld,\"reset_checked\":%s,\"reset_max_abs_diff\":%.9g,"
            "\"golden_checked\":%s,\"golden_max_abs_diff\":%.9g,\"golden_rms_diff\":%.9g}\n",
            TargetVoiceInference::RuntimeVersion(), reference.size(), mixture.size(), result.size(), options.intra_op_threads,
            static_cast<long long>(mag_shape[0]), static_cast<long long>(mag_shape[1]), static_cast<long long>(mag_shape[2]),
            static_cast<long long>(context_shape[0]), static_cast<long long>(context_shape[1]), static_cast<long long>(context_shape[2]),
            load_ms, enroll_ms, times.size(), stats.first_output, stats.steady_output,
            stats.flush_ms, stats.run_total_ms, total / times.size(), Percentile(times, 0.50),
            Percentile(times, 0.95), Percentile(times, 0.99), times.back(), stats.run_total_ms / (mixture.size() / 16.0),
            peak_rss_kib, reset_check ? "true" : "false", reset_diff, expected_path.empty() ? "false" : "true", golden_diff, golden_rms);
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "target_voice_probe: %s\n", error.what());
        return 1;
    }
}
