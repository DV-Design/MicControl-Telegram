#include "VoiceIsolationDenoiser.h"

#include <algorithm>
#include <array>
#include <cmath>

#include "common_audio/resampler/push_sinc_resampler.h"
#include "rnnoise.h"

namespace miccontrol {
namespace {
constexpr std::size_t kRnnoiseFrames = 480;
// A 10 kHz intermediate rate limits the band to a 5 kHz Nyquist frequency.
// The existing finite sinc kernel has a transition band, not a brick-wall edge.
constexpr std::size_t kBandLimitFrames = 100;
}

struct VoiceIsolationDenoiser::Channel {
    ~Channel() {
        if (state) {
            rnnoise_destroy(state);
        }
    }

    bool Reset(std::size_t source_frames) {
        // Bundled rnnoise_init allocates GRU buffers and cannot reset a live
        // state safely. Destroy/create releases those buffers on every toggle.
        if (state) {
            rnnoise_destroy(state);
        }
        state = rnnoise_create(nullptr);
        if (!state) {
            return false;
        }
        if (source_frames != kRnnoiseFrames) {
            to_48k = std::make_unique<webrtc::PushSincResampler>(source_frames, kRnnoiseFrames);
            from_48k = std::make_unique<webrtc::PushSincResampler>(kRnnoiseFrames, source_frames);
        }
        // Recreate both histories together with RNNoise on every reset, so a
        // previous mode/call cannot reappear from the low-pass filter's tail.
        if (source_frames > kBandLimitFrames) {
            to_10k = std::make_unique<webrtc::PushSincResampler>(kRnnoiseFrames, kBandLimitFrames);
            from_10k = std::make_unique<webrtc::PushSincResampler>(kBandLimitFrames, kRnnoiseFrames);
        } else {
            // 8 kHz capture is already limited to 4 kHz by from_48k.
            to_10k.reset();
            from_10k.reset();
        }
        return true;
    }

    DenoiseState* state = nullptr;
    std::unique_ptr<webrtc::PushSincResampler> to_48k;
    std::unique_ptr<webrtc::PushSincResampler> from_48k;
    std::unique_ptr<webrtc::PushSincResampler> to_10k;
    std::unique_ptr<webrtc::PushSincResampler> from_10k;
    std::array<float, kRnnoiseFrames> input{};
    std::array<float, kRnnoiseFrames> output{};
    std::array<float, kBandLimitFrames> band_limited{};
};

VoiceIsolationDenoiser::VoiceIsolationDenoiser() = default;
VoiceIsolationDenoiser::~VoiceIsolationDenoiser() = default;

bool VoiceIsolationDenoiser::Initialize(int sample_rate_hz, std::size_t num_channels, float noise_reduction) {
    channels_.clear();
    source_frames_ = 0;
    needs_reset_ = false;
    noise_reduction_ = std::max(0.0f, std::min(0.60f, noise_reduction));
    // These are the internal processing rates supported by WebRTC's APM.
    if ((sample_rate_hz != 8000 && sample_rate_hz != 16000 &&
         sample_rate_hz != 32000 && sample_rate_hz != 48000) ||
        num_channels == 0 || num_channels > 2 || rnnoise_get_frame_size() != kRnnoiseFrames) {
        return false;
    }
    source_frames_ = static_cast<std::size_t>(sample_rate_hz / 100);
    for (std::size_t i = 0; i < num_channels; ++i) {
        auto channel = std::make_unique<Channel>();
        if (!channel->Reset(source_frames_)) {
            channels_.clear();
            return false;
        }
        channels_.push_back(std::move(channel));
    }
    return true;
}

bool VoiceIsolationDenoiser::Process(float* const* channels, std::size_t num_channels,
                                    std::size_t num_frames, bool enabled) {
    if (!enabled) {
        // Standard mode is an exact bypass. Reset on re-enable so an earlier
        // conversation cannot leak from the RNNoise/resampler delay buffers.
        needs_reset_ = true;
        return false;
    }
    if (!channels || channels_.empty() || num_channels != channels_.size() ||
        num_frames != source_frames_) {
        return false;
    }
    for (std::size_t i = 0; i < num_channels; ++i) {
        if (!channels[i]) {
            return false;
        }
    }
    if (needs_reset_) {
        for (auto& channel : channels_) {
            if (!channel->Reset(source_frames_)) {
                return false;
            }
        }
        needs_reset_ = false;
    }
    for (std::size_t i = 0; i < num_channels; ++i) {
        auto& channel = *channels_[i];
        const float* input = channels[i];
        if (channel.to_48k) {
            channel.to_48k->Resample(input, num_frames, channel.input.data(), kRnnoiseFrames);
            input = channel.input.data();
        }
        // AudioBuffer already uses PCM16 amplitude; do not multiply by 32768.
        // Process silence as well, allowing the filter's delayed audio to drain.
        // A 1.60 exponent means 60% stronger attenuation in decibels in the
        // frequency bins RNNoise identifies as noise. Speech bins near unity
        // keep their level; this is not a uniform microphone volume change.
        rnnoise_process_frame_strength(channel.state, channel.output.data(), input, 1.0f + noise_reduction_);
        if (channel.to_10k) {
            channel.to_10k->Resample(channel.output.data(), kRnnoiseFrames,
                                   channel.band_limited.data(), kBandLimitFrames);
            channel.from_10k->Resample(channel.band_limited.data(), kBandLimitFrames,
                                     channel.output.data(), kRnnoiseFrames);
        }
        if (channel.from_48k) {
            channel.from_48k->Resample(channel.output.data(), kRnnoiseFrames, channels[i], num_frames);
        } else {
            std::copy(channel.output.begin(), channel.output.end(), channels[i]);
        }
        for (std::size_t frame = 0; frame < num_frames; ++frame) {
            channels[i][frame] = std::max(-32768.0f, std::min(32767.0f, channels[i][frame]));
        }
    }
    return true;
}

} // namespace miccontrol
