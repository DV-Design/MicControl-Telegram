// Copyright 2026 Arbaz Siddiqui (VoxLock streaming algorithm).
// C++ adaptation for Danygramm, 2026. SPDX-License-Identifier: Apache-2.0
// See NOTICE.target-voice and LICENSE.voxlock in this directory.
#ifndef MICCONTROL_TARGET_VOICE_INFERENCE_H
#define MICCONTROL_TARGET_VOICE_INFERENCE_H

#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>

namespace miccontrol {

struct TargetVoiceStatus {
    enum class Code { kOk, kInvalidArgument, kNotLoaded, kModelMismatch,
                      kRuntimeError, kOutOfMemory, kStreamFinished };
    Code code = Code::kOk;
    std::array<char, 512> detail{};
    bool ok() const noexcept { return code == Code::kOk; }
    const char* message() const noexcept { return detail.data(); }
};

struct TargetVoiceOptions {
    int intra_op_threads = 4;
};

// Immutable, reusable owner enrollment. Magnitude/context are private derived
// acoustic data (~1 MB) that may retain/reconstruct speech; treat them with the
// same care as a recording. Survives destruction/reloading of its inference
// object. Do not modify this object concurrently with CreateStream/getters.
class TargetVoiceProfile {
public:
    bool valid() const noexcept;
    std::array<std::int64_t, 3> magnitude_shape() const noexcept;
    std::array<std::int64_t, 3> context_shape() const noexcept;
private:
    struct Data;
    std::shared_ptr<const Data> data_;
    friend class TargetVoiceInference;
    friend class TargetVoiceStream;
};

// One call's recurrent/overlap state, used serially by one worker. Different
// streams may share a model/profile. Push is synchronous and belongs off the
// WebRTC capture lock: the eventual integration needs its own delayed FIFO.
class TargetVoiceStream {
public:
    ~TargetVoiceStream();
    TargetVoiceStream(const TargetVoiceStream&) = delete;
    TargetVoiceStream& operator=(const TargetVoiceStream&) = delete;
    // Exactly 640 normalized mono Float32 samples at 16 kHz per push. Output
    // capacity must be >=640; produces 256 on the first push, then 640. Input
    // and output may alias. No wrapper allocation occurs on successful pushes;
    // ONNX Runtime may allocate its own intermediate tensors/workspace.
    TargetVoiceStatus Push(const float* input, std::size_t input_count,
                           float* output, std::size_t output_capacity,
                           std::size_t* output_count) noexcept;
    // Reflect-pad the end and return the remaining 384 valid samples. No extra
    // padded samples are exposed. Push after Flush requires Reset. An empty
    // stream flushes to zero samples. Runtime errors also require Reset.
    TargetVoiceStatus Flush(float* output, std::size_t output_capacity,
                            std::size_t* output_count) noexcept;
    void Reset() noexcept;
private:
    struct Impl;
    explicit TargetVoiceStream(std::unique_ptr<Impl> impl) noexcept;
    std::unique_ptr<Impl> impl_;
    friend class TargetVoiceInference;
};

class TargetVoiceInference {
public:
    static constexpr std::size_t kSampleRate = 16000;
    static constexpr std::size_t kEnrollmentSamples = 48000;
    static constexpr std::size_t kChunkSamples = 640;

    // CPU ONNX Runtime C API 31, sequential execution, spinning and telemetry
    // disabled. Accepts the pinned VoxLock enroll + fp32/int8/int8-full chunk
    // graphs, all with Float32 I/O. No downloading or optional execution providers.
    // Failed loading leaves the previously loaded model usable. Existing
    // streams retain their old model if this object is reloaded or destroyed.
    TargetVoiceStatus LoadModel(const char* enrollment_model_path,
                                const char* chunk_model_path,
                                const TargetVoiceOptions& options = {}) noexcept;
    bool loaded() const noexcept;
    static const char* RuntimeVersion() noexcept;
    // Exactly three seconds, mono 16 kHz, finite samples in [-1,1]. Rejects
    // digital silence; callers must additionally ensure this is the owner.
    TargetVoiceStatus Enroll(const float* samples, std::size_t count,
                             TargetVoiceProfile* profile) const noexcept;
    TargetVoiceStatus CreateStream(const TargetVoiceProfile& profile,
                                   std::unique_ptr<TargetVoiceStream>* stream) const noexcept;
private:
    struct Impl;
    std::shared_ptr<Impl> impl_;
    friend class TargetVoiceStream;
};

}  // namespace miccontrol
#endif
