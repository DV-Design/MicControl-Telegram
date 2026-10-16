#include "VoiceIsolationProcessor.h"

#include <atomic>
#include <utility>

#include "VoiceIsolationDenoiser.h"
#include "group/GroupAudioCapturePostProcessor.h"
#include "modules/audio_processing/audio_buffer.h"

namespace miccontrol {
namespace {
std::atomic<bool> voice_isolation_enabled{false};

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
                          voice_isolation_enabled.load(std::memory_order_relaxed));
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

private:
    std::unique_ptr<webrtc::CustomProcessing> original_;
    VoiceIsolationDenoiser denoiser_;
    int sample_rate_hz_ = 0;
    std::size_t num_channels_ = 0;
};
}

void SetVoiceIsolationEnabled(bool enabled) {
    voice_isolation_enabled.store(enabled, std::memory_order_relaxed);
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
