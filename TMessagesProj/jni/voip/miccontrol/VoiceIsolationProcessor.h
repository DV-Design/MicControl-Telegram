#ifndef MICCONTROL_VOICE_ISOLATION_PROCESSOR_H
#define MICCONTROL_VOICE_ISOLATION_PROCESSOR_H

#include <memory>

#include "modules/audio_processing/include/audio_processing.h"

namespace webrtc {
class AudioProcessingImpl;
}

namespace miccontrol {

void SetVoiceIsolationEnabled(bool enabled);
enum class MicrophoneMode { None = 0, NoiseSuppression = 1, VoiceIsolation = 2 };
void SetMicrophoneMode(int mode);
MicrophoneMode GetMicrophoneMode();
bool IsManagedCaptureProcessor(webrtc::CustomProcessing* processor);
void ConfigureCapture(webrtc::AudioProcessing::Config& config,
                      webrtc::CustomProcessing* processor);
void RegisterAudioProcessing(webrtc::AudioProcessingImpl* processing);
void UnregisterAudioProcessing(webrtc::AudioProcessingImpl* processing);
std::unique_ptr<webrtc::CustomProcessing> WrapCapturePostProcessor(
    std::unique_ptr<webrtc::CustomProcessing> original);

} // namespace miccontrol

#endif
