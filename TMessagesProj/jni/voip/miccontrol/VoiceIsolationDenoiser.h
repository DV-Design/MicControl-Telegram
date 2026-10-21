#ifndef MICCONTROL_VOICE_ISOLATION_DENOISER_H
#define MICCONTROL_VOICE_ISOLATION_DENOISER_H

#include <cstddef>
#include <memory>
#include <vector>

namespace miccontrol {

// Accepts WebRTC's planar FloatS16 capture samples, in 10 ms blocks. RNNoise
// operates at 48 kHz; the existing WebRTC sinc resampler handles other rates.
// Enabled isolation then uses a 10 kHz intermediate rate (5 kHz Nyquist band),
// except 8 kHz input, which is already limited to a 4 kHz Nyquist band.
// Disabled processing remains an exact bypass; reset clears all filter history.
class VoiceIsolationDenoiser {
public:
    VoiceIsolationDenoiser();
    ~VoiceIsolationDenoiser();

    bool Initialize(int sample_rate_hz, std::size_t num_channels, float noise_reduction = 0.60f);
    bool Process(float* const* channels, std::size_t num_channels,
                 std::size_t num_frames, bool enabled);
    void Reset() { needs_reset_ = true; }

private:
    struct Channel;
    std::vector<std::unique_ptr<Channel>> channels_;
    std::size_t source_frames_ = 0;
    bool needs_reset_ = false;
    float noise_reduction_ = 0.60f;
};

} // namespace miccontrol

#endif
