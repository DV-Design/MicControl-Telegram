#ifndef MICCONTROL_VOICE_ISOLATION_DENOISER_H
#define MICCONTROL_VOICE_ISOLATION_DENOISER_H

#include <cstddef>
#include <memory>
#include <vector>

namespace miccontrol {

// Accepts WebRTC's planar FloatS16 capture samples, in 10 ms blocks. RNNoise
// operates at 48 kHz; the existing WebRTC sinc resampler handles other rates.
class VoiceIsolationDenoiser {
public:
    VoiceIsolationDenoiser();
    ~VoiceIsolationDenoiser();

    bool Initialize(int sample_rate_hz, std::size_t num_channels);
    bool Process(float* const* channels, std::size_t num_channels,
                 std::size_t num_frames, bool enabled);

private:
    struct Channel;
    std::vector<std::unique_ptr<Channel>> channels_;
    std::size_t source_frames_ = 0;
    bool needs_reset_ = false;
};

} // namespace miccontrol

#endif
