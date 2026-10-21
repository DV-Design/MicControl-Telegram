#include "miccontrol/VoiceIsolationDenoiser.h"
#include "rnnoise.h"

#include <algorithm>
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
std::size_t rnnoise_allocation_calls = 0;

void Require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

void CompareAmbientPcm(const char* input_path, const char* output_prefix) {
    std::ifstream file(input_path, std::ios::binary | std::ios::ate);
    Require(file.is_open(), "cannot open ambient PCM fixture");
    const auto bytes = static_cast<std::size_t>(file.tellg());
    Require(bytes >= 48000 * sizeof(float) && bytes % sizeof(float) == 0,
            "ambient fixture must contain at least one second of float PCM");
    std::vector<float> input(bytes / sizeof(float));
    file.seekg(0);
    file.read(reinterpret_cast<char*>(input.data()), bytes);
    Require(static_cast<std::size_t>(file.gcount()) == bytes, "truncated ambient fixture");
    for (float sample : input) {
        Require(std::isfinite(sample) && sample >= -32768 && sample <= 32767,
                "invalid ambient PCM amplitude");
    }
    const std::string prefix(output_prefix);
    std::ofstream baseline_file(prefix + "-baseline.f32", std::ios::binary);
    std::ofstream candidate_file(prefix + "-candidate.f32", std::ios::binary);
    std::ofstream probability_file(prefix + "-probability.f32", std::ios::binary);
    Require(baseline_file.good() && candidate_file.good() && probability_file.good(),
            "cannot open ambient output files");
    // This unchanged C API is the shipped exp1.3 reference. The application
    // wrapper is exercised independently, including any proposed pause gain.
    std::unique_ptr<DenoiseState, decltype(&rnnoise_destroy)> baseline(rnnoise_create(nullptr), rnnoise_destroy);
    Require(baseline != nullptr, "ambient RNNoise baseline init failed");
    miccontrol::VoiceIsolationDenoiser candidate;
    Require(candidate.Initialize(48000, 1), "ambient application wrapper init failed");
    const auto allocations_before = rnnoise_allocation_calls;
    const auto blocks = (input.size() + 479) / 480 + 5;
    for (std::size_t block = 0; block < blocks; ++block) {
        float source[480] = {}, before[480] = {}, after[480] = {};
        for (std::size_t i = 0; i < 480 && block * 480 + i < input.size(); ++i) {
            source[i] = after[i] = input[block * 480 + i];
        }
        const float probability = rnnoise_process_frame_strength(baseline.get(), before, source, 1.30f);
        float* channels[] = {after};
        Require(candidate.Process(channels, 1, 480, true), "ambient wrapper processing failed");
        Require(rnnoise_allocation_calls == allocations_before, "RNNoise allocated during steady capture");
        Require(std::isfinite(probability) && probability >= 0 && probability <= 1,
                "invalid speech probability");
        for (std::size_t i = 0; i < 480; ++i) {
            before[i] = std::max(-32768.0f, std::min(32767.0f, before[i]));
            Require(std::isfinite(before[i]) && std::isfinite(after[i]), "non-finite ambient output");
        }
        baseline_file.write(reinterpret_cast<const char*>(before), sizeof(before));
        candidate_file.write(reinterpret_cast<const char*>(after), sizeof(after));
        probability_file.write(reinterpret_cast<const char*>(&probability), sizeof(probability));
    }
    Require(baseline_file.good() && candidate_file.good() && probability_file.good(),
            "ambient output write failed");
    std::cout << "Ambient PCM: " << input.size() << " input samples, " << blocks * 480
              << " output samples, exp1.3 C API and actual wrapper; no steady RNNoise allocation\n";
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
    miccontrol::VoiceIsolationDenoiser previous, stronger, current_default;
    Require(previous.Initialize(48000, 1, 0.0f), "baseline init failed");
    Require(stronger.Initialize(48000, 1, 0.30f), "stronger init failed");
    Require(current_default.Initialize(48000, 1), "current default init failed");
    std::mt19937 random(42);
    std::uniform_real_distribution<float> noise(-3000.0f, 3000.0f);
    float baseline[480], enhanced[480], latest[480];
    float* a[] = {baseline}; float* b[] = {enhanced}; float* c[] = {latest};
    double before = 0, after = 0, default_energy = 0;
    for (int block = 0; block < 300; ++block) {
        for (int i = 0; i < 480; ++i) baseline[i] = enhanced[i] = latest[i] = noise(random);
        previous.Process(a, 1, 480, true);
        stronger.Process(b, 1, 480, true);
        current_default.Process(c, 1, 480, true);
        if (block >= 100) for (int i = 0; i < 480; ++i) {
            before += baseline[i] * baseline[i]; after += enhanced[i] * enhanced[i];
            default_energy += latest[i] * latest[i];
        }
    }
    std::cout << "Measured residual noise ratio: " << after / before << std::endl;
    Require(before > 0 && after / before < 0.9 && after > 0,
            "30-percent stronger spectral attenuation did not lower residual noise");
    std::cout << "Stronger isolation residual noise energy ratio vs previous RNNoise: " << after / before << '\n';
    Require(default_energy > 0 && default_energy / after < 0.90,
            "product default did not reduce residual noise beyond legacy exp1.3");
    std::cout << "Product default / exp1.3 residual noise energy ratio: " << default_energy / after << '\n';
}

void CheckIsolationBandwidth() {
    // Each real wrapper run has an independent, identical exp1.6 RNNoise C API
    // reference. Separate stimuli avoid RNNoise's own suppression of one tone
    // making an added linear filter's response unmeasurable.
    struct Probe {
        double reference_cos[3] = {}, reference_sin[3] = {};
        double actual_cos[3] = {}, actual_sin[3] = {};
        std::vector<float> reference_pcm, actual_pcm;
    };
    constexpr double pi = 3.14159265358979323846;
    const int frequencies[] = {1000, 5000, 8000};
    const auto run = [&](int second_tone, bool add_noise) {
        Probe result;
        result.reference_pcm.reserve(200 * 480); result.actual_pcm.reserve(200 * 480);
        miccontrol::VoiceIsolationDenoiser actual;
        Require(actual.Initialize(48000, 1), "bandwidth wrapper init failed");
        std::unique_ptr<DenoiseState, decltype(&rnnoise_destroy)> reference(rnnoise_create(nullptr), rnnoise_destroy);
        Require(reference != nullptr, "bandwidth reference init failed");
        std::mt19937 random(20261021);
        std::uniform_real_distribution<float> noise(-1500.0f, 1500.0f);
        const auto allocations_before = rnnoise_allocation_calls;
        for (int block = 0; block < 300; ++block) {
            float source[480], expected[480], output[480];
            for (int i = 0; i < 480; ++i) {
                const double t = static_cast<double>(block * 480 + i) / 48000;
                source[i] = static_cast<float>(5000 * std::sin(2*pi*1000*t)
                            + (second_tone ? 5000 * std::cos(2*pi*second_tone*t) : 0));
                if (add_noise) source[i] += noise(random);
                output[i] = source[i];
            }
            rnnoise_process_frame_strength(reference.get(), expected, source, 1.60f);
            float* channels[] = {output};
            Require(actual.Process(channels, 1, 480, true), "bandwidth wrapper process failed");
            Require(rnnoise_allocation_calls == allocations_before, "bandwidth steady capture allocated RNNoise buffers");
            if (block < 100) continue;
            for (int i = 0; i < 480; ++i) {
                Require(std::isfinite(output[i]), "bandwidth output is non-finite");
                const double t = static_cast<double>(block * 480 + i) / 48000;
                for (int band = 0; band < 3; ++band) {
                    const double cosine = std::cos(2*pi*frequencies[band]*t);
                    const double sine = std::sin(2*pi*frequencies[band]*t);
                    result.reference_cos[band] += expected[i]*cosine;
                    result.reference_sin[band] += expected[i]*sine;
                    result.actual_cos[band] += output[i]*cosine;
                    result.actual_sin[band] += output[i]*sine;
                }
                if (add_noise) {
                    result.reference_pcm.push_back(expected[i]); result.actual_pcm.push_back(output[i]);
                }
            }
        }
        return result;
    };
    const auto amplitude = [](const Probe& probe, int band, bool reference) {
        return std::hypot(reference ? probe.reference_cos[band] : probe.actual_cos[band],
                          reference ? probe.reference_sin[band] : probe.actual_sin[band]) / 48000;
    };
    const auto pass_stop = run(8000, false);
    const auto transition = run(5000, false);
    const double pass_before = amplitude(pass_stop, 0, true);
    const double stop_before = amplitude(pass_stop, 2, true);
    const double edge_before = amplitude(transition, 1, true);
    std::cout << "Bandwidth reference amplitudes (1/5/8 kHz), separate stimuli: "
              << pass_before << " / " << edge_before << " / " << stop_before << std::endl;
    Require(pass_before > 0.1 && edge_before > 0.1 && stop_before > 0.1,
            "spectral reference lacks measurable tones");
    const double pass_ratio = amplitude(pass_stop, 0, false) / pass_before;
    const double stop_ratio = amplitude(pass_stop, 2, false) / stop_before;
    const double edge_ratio = amplitude(transition, 1, false) / edge_before;
    Require(pass_ratio >= 0.95 && pass_ratio <= 1.05, "5 kHz band limit changed the 1 kHz passband");
    Require(edge_ratio < 0.1, "5 kHz band limit did not attenuate its 5 kHz edge by 20 dB");
    Require(stop_ratio < 0.01, "5 kHz band limit did not reject the 8 kHz stopband by 40 dB");
    std::cout << "5 kHz band limit vs RNNoise1.6: 1 kHz amplitude ratio " << pass_ratio
              << ", 5 kHz transition attenuation " << -20*std::log10(std::max(edge_ratio, 1e-30)) << " dB"
              << ", 8 kHz attenuation " << -20*std::log10(std::max(stop_ratio, 1e-30)) << " dB\n";
    const auto delay = run(0, true);
    int best_lag = 0;
    double best_correlation = -1;
    for (int lag = 0; lag <= 240; ++lag) {
        double cross = 0, reference_energy = 0, actual_energy = 0;
        for (std::size_t i = 240; i < delay.actual_pcm.size(); ++i) {
            const double a = delay.reference_pcm[i-lag], b = delay.actual_pcm[i];
            cross += a*b; reference_energy += a*a; actual_energy += b*b;
        }
        const double correlation = cross/std::sqrt(reference_energy*actual_energy);
        if (correlation > best_correlation) { best_correlation = correlation; best_lag = lag; }
    }
    std::cout << "5 kHz band limit added fixed delay: " << best_lag << " / 48000 samples ("
              << best_lag/48.0 << " ms), correlation " << best_correlation << std::endl;
    // PushSincResampler discards floor((source_frames - 16) / ratio)
    // priming outputs. Thus 480->100 adds (100-floor(464/4.8))*4.8
    // = 19.2 samples at 48 kHz, and 100->480 adds 480-floor(84/(100/480))
    // = 77 samples. The pair's actual fixed delay is 96.2 samples, including
    // priming quantization, rather than just the two ideal half kernels.
    Require(best_lag >= 95 && best_lag <= 97 && best_correlation > 0.5,
            "band limit delay differs from its two existing sinc kernels");
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
    miccontrol::VoiceIsolationDenoiser previous, stronger, current_default;
    Require(previous.Initialize(48000, 1, 0.0f), "speech baseline init failed");
    Require(stronger.Initialize(48000, 1, 0.30f), "speech stronger init failed");
    Require(current_default.Initialize(48000, 1), "speech default init failed");
    double input_energy = 0, old_energy = 0, new_energy = 0, cross = 0;
    double default_energy = 0, default_cross = 0;
    // Drain both filters equally so their delay does not discard the final syllable.
    const auto blocks = (speech.size() + 479) / 480 + 5;
    for (std::size_t block = 0; block < blocks; ++block) {
        float old_samples[480] = {}, new_samples[480] = {}, default_samples[480] = {};
        for (std::size_t i = 0; i < 480 && block * 480 + i < speech.size(); ++i) {
            const auto sample = speech[block * 480 + i];
            Require(std::isfinite(sample), "speech input contains non-finite PCM");
            old_samples[i] = new_samples[i] = default_samples[i] = sample;
            input_energy += static_cast<double>(sample) * sample;
        }
        float* old_channels[] = {old_samples};
        float* new_channels[] = {new_samples};
        float* default_channels[] = {default_samples};
        Require(previous.Process(old_channels, 1, 480, true), "speech baseline process failed");
        Require(stronger.Process(new_channels, 1, 480, true), "speech stronger process failed");
        Require(current_default.Process(default_channels, 1, 480, true), "speech default process failed");
        for (std::size_t i = 0; i < 480; ++i) {
            old_energy += static_cast<double>(old_samples[i]) * old_samples[i];
            new_energy += static_cast<double>(new_samples[i]) * new_samples[i];
            cross += static_cast<double>(old_samples[i]) * new_samples[i];
            default_energy += static_cast<double>(default_samples[i]) * default_samples[i];
            default_cross += static_cast<double>(new_samples[i]) * default_samples[i];
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
    const double default_ratio = default_energy / new_energy;
    const double default_similarity = default_cross / std::sqrt(new_energy * default_energy);
    std::cout << "Clean speech: product default / exp1.3 energy=" << default_ratio
              << ", waveform cosine similarity=" << default_similarity << '\n';
    Require(std::isfinite(default_ratio) && default_ratio >= 0.95 && default_ratio <= 1.05,
            "product default changed overall clean speech level too much");
    Require(std::isfinite(default_similarity) && default_similarity >= 0.995,
            "product default substantially changed the clean speech waveform");
}
}

// Only denoise.c is compiled with these two symbol substitutions. This checks
// the three GRU buffers allocated by RNNoise without replacing the audio model.
extern "C" void* miccontrol_test_calloc(std::size_t count, std::size_t size) {
    ++rnnoise_allocation_calls;
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
        if (argc >= 4 && argc % 2 == 0 && std::strcmp(argv[1], "--ambient") == 0) {
            for (int argument = 2; argument < argc; argument += 2) {
                CompareAmbientPcm(argv[argument], argv[argument + 1]);
                Require(rnnoise_allocations.empty(), "ambient-isolation states leaked");
            }
            return 0;
        }
        {
            miccontrol::VoiceIsolationDenoiser denoiser;
            Require(denoiser.Initialize(48000, 1), "initialization failed");
        }
        Require(rnnoise_allocations.empty(), "RNNoise GRU buffers leaked during initialization/reset");
        CheckStrongerIsolation();
        Require(rnnoise_allocations.empty(), "stronger-isolation states leaked");
        CheckIsolationBandwidth();
        Require(rnnoise_allocations.empty(), "bandwidth-isolation states leaked");
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
