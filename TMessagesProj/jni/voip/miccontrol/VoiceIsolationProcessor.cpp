#include "VoiceIsolationProcessor.h"

#include <atomic>
#include <algorithm>
#include <mutex>
#include <vector>
#include <utility>

#include "VoiceIsolationDenoiser.h"
#include "group/GroupAudioCapturePostProcessor.h"
#include "modules/audio_processing/audio_buffer.h"
#include "modules/audio_processing/audio_processing_impl.h"

namespace miccontrol {
namespace {
std::atomic<int> microphone_mode{1};
// Lock order is registry -> APM render -> APM capture. AudioProcessingImpl
// unregisters before tearing down its members and takes no APM lock there.
// Capture/configuration callbacks must never acquire this registry lock.
std::mutex processing_mutex;
std::vector<webrtc::AudioProcessingImpl*> processing_instances;

class VoiceIsolationProcessor final : public webrtc::CustomProcessing {
public:
    explicit VoiceIsolationProcessor(std::unique_ptr<webrtc::CustomProcessing> original)
        : original_(std::move(original)) {}

    void Initialize(int sample_rate_hz, int num_channels) override {
        sample_rate_hz_ = sample_rate_hz;
        num_channels_ = num_channels;
        denoiser_.Initialize(sample_rate_hz, num_channels);
        if (original_) {
            original_->Initialize(sample_rate_hz, num_channels);
        }
    }

    void Process(webrtc::AudioBuffer* audio) override {
        if (!audio) {
            return;
        }
        if (audio->num_channels() != num_channels_) {
            num_channels_ = audio->num_channels();
            denoiser_.Initialize(sample_rate_hz_, num_channels_);
        }
        denoiser_.Process(audio->channels(), audio->num_channels(), audio->num_frames(),
                          mode_ == MicrophoneMode::VoiceIsolation);
        // Preserve the legacy engine's level reporting and external audio mix.
        if (original_) {
            original_->Process(audio);
        }
    }

    std::string ToString() const override {
        return "MicControlVoiceIsolation";
    }

    void SetRuntimeSetting(webrtc::AudioProcessing::RuntimeSetting setting) override {
        if (original_) {
            original_->SetRuntimeSetting(setting);
        }
    }

    // ConfigureCapture and Process run under the same APM capture lock. Reading
    // the global atomic during Process would mix the new RNNoise mode with the
    // previous frame's APM configuration while SetMicrophoneMode waits for it.
    void SetMode(MicrophoneMode mode) {
        if (mode_ != mode) {
            denoiser_.Reset();
            mode_ = mode;
        }
    }

private:
    std::unique_ptr<webrtc::CustomProcessing> original_;
    VoiceIsolationDenoiser denoiser_;
    MicrophoneMode mode_ = MicrophoneMode::NoiseSuppression;
    int sample_rate_hz_ = 0;
    std::size_t num_channels_ = 0;
};
}

void SetVoiceIsolationEnabled(bool enabled) {
    SetMicrophoneMode(enabled ? 2 : 1);
}

MicrophoneMode GetMicrophoneMode() {
    return static_cast<MicrophoneMode>(microphone_mode.load(std::memory_order_acquire));
}

bool IsManagedCaptureProcessor(webrtc::CustomProcessing* processor) {
    return dynamic_cast<VoiceIsolationProcessor*>(processor) != nullptr;
}

void ConfigureCapture(webrtc::AudioProcessing::Config& config,
                      webrtc::CustomProcessing* processor) {
    auto* managed = dynamic_cast<VoiceIsolationProcessor*>(processor);
    if (!managed) return;
    const auto mode = GetMicrophoneMode();
    managed->SetMode(mode);
    const bool enabled = mode != MicrophoneMode::None;
    config.noise_suppression.enabled = enabled;
    config.noise_suppression.level = webrtc::AudioProcessing::Config::NoiseSuppression::kHigh;
    config.high_pass_filter.enabled = enabled;
    config.gain_controller1.enabled = enabled;
    config.gain_controller1.mode = webrtc::AudioProcessing::Config::GainController1::kFixedDigital;
    config.gain_controller2.enabled = false;
    config.pre_amplifier.enabled = false;
    config.capture_level_adjustment.enabled = false;
    config.transient_suppression.enabled = false;
    // Echo cancellation is essential for speaker calls and stays under the engine's control.
}

void RegisterAudioProcessing(webrtc::AudioProcessingImpl* processing) {
    std::lock_guard<std::mutex> lock(processing_mutex);
    processing_instances.push_back(processing);
    processing->RefreshMicrophoneMode();
}

void UnregisterAudioProcessing(webrtc::AudioProcessingImpl* processing) {
    std::lock_guard<std::mutex> lock(processing_mutex);
    processing_instances.erase(std::remove(processing_instances.begin(), processing_instances.end(), processing),
                               processing_instances.end());
}

void SetMicrophoneMode(int mode) {
    if (mode < 0 || mode > 2) mode = 1;
    std::lock_guard<std::mutex> lock(processing_mutex);
    microphone_mode.store(mode, std::memory_order_release);
    for (auto* processing : processing_instances) {
        processing->RefreshMicrophoneMode();
    }
}

std::unique_ptr<webrtc::CustomProcessing> WrapCapturePostProcessor(
        std::unique_ptr<webrtc::CustomProcessing> original) {
    // Group/conference calls already own RNNoise and their level/VAD processor.
    // This prototype exposes MicControl only for personal voice/video calls.
    if (dynamic_cast<tgcalls::AudioCapturePostProcessor*>(original.get())) {
        return original;
    }
    return std::make_unique<VoiceIsolationProcessor>(std::move(original));
}

} // namespace miccontrol
