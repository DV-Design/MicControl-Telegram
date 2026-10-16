#include "miccontrol/VoiceIsolationDenoiser.h"

#include <cmath>
#include <cstdlib>
#include <cstring>
#include <iostream>
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

int main() {
    try {
        {
            miccontrol::VoiceIsolationDenoiser denoiser;
            Require(denoiser.Initialize(48000, 1), "initialization failed");
        }
        Require(rnnoise_allocations.empty(), "RNNoise GRU buffers leaked during initialization/reset");
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
