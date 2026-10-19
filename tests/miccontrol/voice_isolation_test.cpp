#include "miccontrol/VoiceIsolationDenoiser.h"

#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <fstream>
#include <random>
#include <stdexcept>
#include <unordered_set>
#include <vector>

namespace {
std::unordered_set<void*> rnnoise_allocations;

void Require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

void CheckAudio(int sample_rate, std::size_t channels_count) {
    const std::size_t frames = sample_rate / 100;
    miccontrol::VoiceIsolationDenoiser denoiser;
    Require(denoiser.Initialize(sample_rate, channels_count), "supported format rejected");
    std::vector<std::vector<float>> samples(channels_count, std::vector<float>(frames));
    std::vector<float*> channels;
    for (auto& channel : samples) {
        channels.push_back(channel.data());
    }
    std::mt19937 random(42);
    std::uniform_real_distribution<float> noise(-3000.0f, 3000.0f);
    for (auto& channel : samples) {
        for (float& sample : channel) sample = noise(random);
    }
    const auto original = samples;
    Require(!denoiser.Process(channels.data(), channels_count, frames, false), "Standard did not bypass");
    for (std::size_t ch = 0; ch < channels_count; ++ch) {
        Require(std::memcmp(original[ch].data(), samples[ch].data(), frames * sizeof(float)) == 0,
                "Standard changed input samples");
        std::fill(samples[ch].begin(), samples[ch].end(), 0.0f);
    }
    double input_energy = 0, output_energy = 0;
    for (int block = 0; block < 160; ++block) {
        for (float& sample : samples[0]) {
            sample = noise(random);
            if (block >= 60) input_energy += sample * sample;
        }
        Require(denoiser.Process(channels.data(), channels_count, frames, true), "isolation did not process");
        for (std::size_t ch = 0; ch < channels_count; ++ch) {
            for (float sample : samples[ch]) {
                Require(std::isfinite(sample) && sample >= -32768 && sample <= 32767,
                        "invalid output amplitude");
                if (ch == 0 && block >= 60) output_energy += sample * sample;
                if (ch == 1) Require(sample == 0.0f, "audio leaked between channels");
            }
        }
    }
    Require(output_energy < input_energy * 0.95, "background noise was not attenuated");
    // A mode may change while capture is paused, without any bypass frame.
    // Explicit reset must still discard the previous delayed microphone audio.
    denoiser.Reset();
    for (auto& channel : samples) std::fill(channel.begin(), channel.end(), 0.0f);
    Require(denoiser.Process(channels.data(), channels_count, frames, true), "explicit reset failed");
    for (const auto& channel : samples) {
        for (float sample : channel) Require(sample == 0.0f, "old audio survived explicit reset");
    }
    // A muted interval followed by re-enabling must not replay an old frame.
    for (int toggle = 0; toggle < 50; ++toggle) {
        for (auto& channel : samples) std::fill(channel.begin(), channel.end(), 10000.0f);
        denoiser.Process(channels.data(), channels_count, frames, false);
        for (auto& channel : samples) std::fill(channel.begin(), channel.end(), 0.0f);
        Require(denoiser.Process(channels.data(), channels_count, frames, true), "re-enable failed");
        for (const auto& channel : samples) {
            for (float sample : channel) Require(sample == 0.0f, "old audio survived mode switch");
        }
    }
    std::cout << sample_rate << " Hz / " << channels_count << " channel(s): bypass, finite output, "
              << "silence, channel isolation, toggles; noise energy ratio "
              << output_energy / input_energy << '\n';
}

void CheckStrongerIsolation() {
    miccontrol::VoiceIsolationDenoiser previous, stronger;
    Require(previous.Initialize(48000, 1, 0.0f), "baseline init failed");
    Require(stronger.Initialize(48000, 1, 0.30f), "stronger init failed");
    std::mt19937 random(42);
    std::uniform_real_distribution<float> noise(-3000.0f, 3000.0f);
    float baseline[480], enhanced[480];
    float* a[] = {baseline}; float* b[] = {enhanced};
    double before = 0, after = 0;
    for (int block = 0; block < 300; ++block) {
        for (int i = 0; i < 480; ++i) baseline[i] = enhanced[i] = noise(random);
        previous.Process(a, 1, 480, true);
        stronger.Process(b, 1, 480, true);
        if (block >= 100) for (int i = 0; i < 480; ++i) {
            before += baseline[i] * baseline[i]; after += enhanced[i] * enhanced[i];
        }
    }
    std::cout << "Measured residual noise ratio: " << after / before << std::endl;
    Require(before > 0 && after / before < 0.9 && after > 0,
            "30-percent stronger spectral attenuation did not lower residual noise");
    std::cout << "Stronger isolation residual noise energy ratio vs previous RNNoise: " << after / before << '\n';
}

void CheckSpeechPreservation(const char* path) {
    std::ifstream file(path, std::ios::binary | std::ios::ate);
    Require(file.is_open(), "cannot open speech fixture");
    const auto bytes = static_cast<std::size_t>(file.tellg());
    Require(bytes >= 48000 * sizeof(float) && bytes % sizeof(float) == 0,
            "speech fixture must contain at least one second of float PCM");
    std::vector<float> speech(bytes / sizeof(float));
    file.seekg(0);
    file.read(reinterpret_cast<char*>(speech.data()), bytes);
    Require(static_cast<std::size_t>(file.gcount()) == bytes, "truncated speech fixture");
    miccontrol::VoiceIsolationDenoiser previous, stronger;
    Require(previous.Initialize(48000, 1, 0.0f), "speech baseline init failed");
    Require(stronger.Initialize(48000, 1, 0.30f), "speech stronger init failed");
    double input_energy = 0, old_energy = 0, new_energy = 0, cross = 0;
    // Drain both filters equally so their delay does not discard the final syllable.
    const auto blocks = (speech.size() + 479) / 480 + 5;
    for (std::size_t block = 0; block < blocks; ++block) {
        float old_samples[480] = {}, new_samples[480] = {};
        for (std::size_t i = 0; i < 480 && block * 480 + i < speech.size(); ++i) {
            const auto sample = speech[block * 480 + i];
            Require(std::isfinite(sample), "speech input contains non-finite PCM");
            old_samples[i] = new_samples[i] = sample;
            input_energy += static_cast<double>(sample) * sample;
        }
        float* old_channels[] = {old_samples};
        float* new_channels[] = {new_samples};
        Require(previous.Process(old_channels, 1, 480, true), "speech baseline process failed");
        Require(stronger.Process(new_channels, 1, 480, true), "speech stronger process failed");
        for (std::size_t i = 0; i < 480; ++i) {
            old_energy += static_cast<double>(old_samples[i]) * old_samples[i];
            new_energy += static_cast<double>(new_samples[i]) * new_samples[i];
            cross += static_cast<double>(old_samples[i]) * new_samples[i];
        }
    }
    Require(input_energy > 1 && old_energy > input_energy * 0.20,
            "speech fixture is silent or baseline suppresses most of its energy");
    const double ratio = new_energy / old_energy;
    const double similarity = cross / std::sqrt(old_energy * new_energy);
    std::cout << "Clean speech: stronger/baseline energy=" << ratio
              << ", waveform cosine similarity=" << similarity
              << ", stronger/input energy=" << new_energy / input_energy << '\n';
    Require(std::isfinite(ratio) && ratio >= 0.70 && ratio <= 1.05,
            "stronger RNNoise removed too much clean speech");
    Require(std::isfinite(similarity) && similarity >= 0.95,
            "stronger RNNoise substantially changed the clean speech waveform");
}
}

// Only denoise.c is compiled with these two symbol substitutions. This checks
// the three GRU buffers allocated by RNNoise without replacing the audio model.
extern "C" void* miccontrol_test_calloc(std::size_t count, std::size_t size) {
    void* allocation = std::calloc(count, size);
    if (allocation) rnnoise_allocations.insert(allocation);
    return allocation;
}

extern "C" void miccontrol_test_free(void* allocation) {
    rnnoise_allocations.erase(allocation);
    std::free(allocation);
}

int main(int argc, char** argv) {
    try {
        {
            miccontrol::VoiceIsolationDenoiser denoiser;
            Require(denoiser.Initialize(48000, 1), "initialization failed");
        }
        Require(rnnoise_allocations.empty(), "RNNoise GRU buffers leaked during initialization/reset");
        CheckStrongerIsolation();
        Require(rnnoise_allocations.empty(), "stronger-isolation states leaked");
        if (argc > 1) {
            CheckSpeechPreservation(argv[1]);
            Require(rnnoise_allocations.empty(), "speech-isolation states leaked");
        }
        for (int rate : {8000, 16000, 32000, 48000}) {
            for (std::size_t channels : {1, 2}) {
                CheckAudio(rate, channels);
                Require(rnnoise_allocations.empty(), "RNNoise GRU buffers leaked after toggling");
            }
        }
        miccontrol::VoiceIsolationDenoiser invalid;
        Require(!invalid.Initialize(44100, 1), "unsupported rate accepted");
        Require(!invalid.Initialize(48000, 3), "unsupported channels accepted");
        Require(!invalid.Process(nullptr, 1, 480, true), "invalid input accepted");
        Require(invalid.Initialize(48000, 1), "valid reinitialization failed");
        float samples[480] = {1000};
        float* channels[] = {samples};
        Require(!invalid.Process(channels, 1, 479, true) && samples[0] == 1000,
                "invalid frame size modified input");
        std::cout << "PASS: Voice Isolation native tests\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL: " << error.what() << '\n';
        return 1;
    }
}
