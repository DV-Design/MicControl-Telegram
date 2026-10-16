#ifndef MICCONTROL_VOICE_ISOLATION_PROCESSOR_H
#define MICCONTROL_VOICE_ISOLATION_PROCESSOR_H

#include <memory>

#include "modules/audio_processing/include/audio_processing.h"

namespace miccontrol {

void SetVoiceIsolationEnabled(bool enabled);
std::unique_ptr<webrtc::CustomProcessing> WrapCapturePostProcessor(
    std::unique_ptr<webrtc::CustomProcessing> original);

} // namespace miccontrol

#endif
