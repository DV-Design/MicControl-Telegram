// Copyright 2026 Arbaz Siddiqui (VoxLock streaming algorithm).
// C++ adaptation for Danygramm, 2026. SPDX-License-Identifier: Apache-2.0
// Licensed under the Apache License, Version 2.0; see LICENSE.voxlock.
// Changed from VoxLock core.py: fixed 40 ms blocks, preallocated I/O/state,
// owned enrollment, C API statuses, and Flush trimmed to valid input length.

#include "TargetVoiceInference.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <exception>
#include <new>

#include "onnxruntime_c_api.h"

namespace miccontrol {
namespace {
using Status = TargetVoiceStatus;
using Code = Status::Code;
constexpr std::size_t kHop = 128, kWindow = 512, kPadding = 256;
constexpr std::size_t kHistory = kWindow - kHop, kState = 6 * 32 * 256;
constexpr std::size_t kMagnitude = 257 * 376, kContext = 512 * 298;
constexpr std::array<std::int64_t, 3> kMagnitudeShape{1, 257, 376};
constexpr std::array<std::int64_t, 3> kContextShape{1, 512, 298};
constexpr std::array<std::int64_t, 3> kStateShape{6, 32, 256};
constexpr const char* kInputs[]{"wav", "enroll_mag", "context", "h", "c"};
constexpr const char* kOutputs[]{"frames", "h_out", "c_out"};

Status Error(Code code, const char* text, const char* detail = nullptr) noexcept {
    Status result;
    result.code = code;
    std::snprintf(result.detail.data(), result.detail.size(), "%s%s%s",
                  text, detail ? ": " : "", detail ? detail : "");
    return result;
}
Status Check(const OrtApi* api, OrtStatus* ort_status, const char* operation) noexcept {
    if (!ort_status) return {};
    const Status result = Error(Code::kRuntimeError, operation, api->GetErrorMessage(ort_status));
    api->ReleaseStatus(ort_status);
    return result;
}
#define TV_CHECK(expression) do { const Status tv_status = Check(api, (expression), #expression); \
    if (!tv_status.ok()) return tv_status; } while (false)

template <typename T> struct OrtDeleter {
    void (ORT_API_CALL *release)(T*) = nullptr;
    void operator()(T* pointer) const noexcept { if (pointer) release(pointer); }
};
template <typename T> using OrtOwner = std::unique_ptr<T, OrtDeleter<T>>;
using Value = OrtOwner<OrtValue>;

bool Normalized(const float* samples, std::size_t count) noexcept {
    if (!samples) return false;
    for (std::size_t i = 0; i < count; ++i) {
        if (!std::isfinite(samples[i]) || std::abs(samples[i]) > 1.0f) return false;
    }
    return true;
}
bool Finite(const float* samples, std::size_t count) noexcept {
    for (std::size_t i = 0; i < count; ++i) if (!std::isfinite(samples[i])) return false;
    return true;
}
Status Tensor(const OrtApi* api, const OrtMemoryInfo* memory, float* data,
              std::size_t count, const std::int64_t* dimensions,
              std::size_t rank, Value* value) noexcept {
    OrtValue* raw = nullptr;
    const Status result = Check(api, api->CreateTensorWithDataAsOrtValue(
        memory, data, count * sizeof(float), dimensions, rank,
        ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &raw), "CreateTensorWithDataAsOrtValue");
    *value = Value(raw, OrtDeleter<OrtValue>{api->ReleaseValue});
    return result;
}

// Verify the actual graph's names, Float32 types and ranks/static dimensions.
// Inputs must have the expected static/dynamic geometry. Exported outputs may
// describe a known dimension symbolically; the preallocated Run outputs still
// require the actual shape (including batch=1 and bands=32) at execution time.
Status Signature(const OrtApi* api, OrtSession* session, bool input,
                 std::size_t index, const char* expected_name,
                 const std::int64_t* expected, std::size_t rank) noexcept {
    OrtAllocator* allocator = nullptr;
    TV_CHECK(api->GetAllocatorWithDefaultOptions(&allocator));
    char* name = nullptr;
    TV_CHECK(input ? api->SessionGetInputName(session, index, allocator, &name)
                   : api->SessionGetOutputName(session, index, allocator, &name));
    const bool same_name = name && std::strcmp(name, expected_name) == 0;
    allocator->Free(allocator, name);
    if (!same_name) return Error(Code::kModelMismatch, "Unexpected graph tensor name", expected_name);
    OrtTypeInfo* raw_type = nullptr;
    const Status got_type = Check(api, input ? api->SessionGetInputTypeInfo(session, index, &raw_type)
        : api->SessionGetOutputTypeInfo(session, index, &raw_type), "SessionGetTypeInfo");
    OrtOwner<OrtTypeInfo> type(raw_type, OrtDeleter<OrtTypeInfo>{api->ReleaseTypeInfo});
    if (!got_type.ok()) return got_type;
    const OrtTensorTypeAndShapeInfo* shape = nullptr;
    TV_CHECK(api->CastTypeInfoToTensorInfo(type.get(), &shape));
    if (!shape) return Error(Code::kModelMismatch, "Graph value is not a tensor", expected_name);
    ONNXTensorElementDataType dtype;
    TV_CHECK(api->GetTensorElementType(shape, &dtype));
    std::size_t actual_rank = 0;
    TV_CHECK(api->GetDimensionsCount(shape, &actual_rank));
    if (dtype != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT || actual_rank != rank || rank > 3)
        return Error(Code::kModelMismatch, "Unexpected tensor type/rank", expected_name);
    std::array<std::int64_t, 3> dims{};
    TV_CHECK(api->GetDimensions(shape, dims.data(), actual_rank));
    for (std::size_t d = 0; d < rank; ++d) {
        if ((expected[d] > 0 && dims[d] != expected[d] && (input || dims[d] >= 0)) ||
            (expected[d] == -1 && dims[d] >= 0))
            return Error(Code::kModelMismatch, "Unexpected static/dynamic tensor dimension", expected_name);
    }
    return {};
}
Status Counts(const OrtApi* api, OrtSession* session,
              std::size_t expected_inputs, std::size_t expected_outputs) noexcept {
    std::size_t inputs = 0, outputs = 0;
    TV_CHECK(api->SessionGetInputCount(session, &inputs));
    TV_CHECK(api->SessionGetOutputCount(session, &outputs));
    return inputs == expected_inputs && outputs == expected_outputs ? Status{}
        : Error(Code::kModelMismatch, "Unexpected graph input/output count");
}
}  // namespace

struct TargetVoiceProfile::Data {
    std::array<float, kMagnitude> magnitude{};
    std::array<float, kContext> context{};
};

struct TargetVoiceInference::Impl {
    const OrtApi* api = nullptr;
    // Reverse destruction order: sessions/memory must precede the environment.
    OrtOwner<OrtEnv> environment;
    OrtOwner<OrtMemoryInfo> memory;
    OrtOwner<OrtSession> enrollment, chunk;

    Status Initialize(const char* enroll_path, const char* chunk_path,
                      const TargetVoiceOptions& options) noexcept {
        api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
        if (!api) return Error(Code::kRuntimeError, "ONNX Runtime C API 31 unavailable");
        OrtEnv* raw_environment = nullptr;
        const Status env_result = Check(api, api->CreateEnv(ORT_LOGGING_LEVEL_WARNING,
            "DanygrammTargetVoice", &raw_environment), "CreateEnv");
        environment = OrtOwner<OrtEnv>(raw_environment, OrtDeleter<OrtEnv>{api->ReleaseEnv});
        if (!env_result.ok()) return env_result;
        TV_CHECK(api->DisableTelemetryEvents(environment.get()));
        OrtSessionOptions* raw_options = nullptr;
        const Status options_result = Check(api, api->CreateSessionOptions(&raw_options), "CreateSessionOptions");
        OrtOwner<OrtSessionOptions> session_options(raw_options,
            OrtDeleter<OrtSessionOptions>{api->ReleaseSessionOptions});
        if (!options_result.ok()) return options_result;
        TV_CHECK(api->SetIntraOpNumThreads(session_options.get(), options.intra_op_threads));
        TV_CHECK(api->SetInterOpNumThreads(session_options.get(), 1));
        TV_CHECK(api->SetSessionExecutionMode(session_options.get(), ORT_SEQUENTIAL));
        TV_CHECK(api->SetSessionGraphOptimizationLevel(session_options.get(), ORT_ENABLE_ALL));
        TV_CHECK(api->AddSessionConfigEntry(session_options.get(), "session.intra_op.allow_spinning", "0"));
        TV_CHECK(api->AddSessionConfigEntry(session_options.get(), "session.inter_op.allow_spinning", "0"));
        OrtMemoryInfo* raw_memory = nullptr;
        const Status memory_result = Check(api, api->CreateCpuMemoryInfo(OrtArenaAllocator,
            OrtMemTypeDefault, &raw_memory), "CreateCpuMemoryInfo");
        memory = OrtOwner<OrtMemoryInfo>(raw_memory, OrtDeleter<OrtMemoryInfo>{api->ReleaseMemoryInfo});
        if (!memory_result.ok()) return memory_result;
        OrtSession* raw_session = nullptr;
        Status status = Check(api, api->CreateSession(environment.get(), enroll_path,
            session_options.get(), &raw_session), "Load enrollment model");
        enrollment = OrtOwner<OrtSession>(raw_session, OrtDeleter<OrtSession>{api->ReleaseSession});
        if (!status.ok()) return status;
        raw_session = nullptr;
        status = Check(api, api->CreateSession(environment.get(), chunk_path,
            session_options.get(), &raw_session), "Load chunk model");
        chunk = OrtOwner<OrtSession>(raw_session, OrtDeleter<OrtSession>{api->ReleaseSession});
        if (!status.ok()) return status;
        status = Counts(api, enrollment.get(), 1, 2);
        if (!status.ok()) return status;
        status = Counts(api, chunk.get(), 5, 3);
        if (!status.ok()) return status;
        constexpr std::int64_t enroll_dims[]{1, -1};
        constexpr std::int64_t magnitude_dims[]{1, 257, -1}, context_dims[]{1, 512, -1};
        constexpr std::int64_t frames_dims[]{1, -1, 512};
        status = Signature(api, enrollment.get(), true, 0, "enroll", enroll_dims, 2);
        if (!status.ok()) return status;
        status = Signature(api, enrollment.get(), false, 0, "enroll_mag", magnitude_dims, 3);
        if (!status.ok()) return status;
        status = Signature(api, enrollment.get(), false, 1, "context", context_dims, 3);
        if (!status.ok()) return status;
        const std::int64_t* input_shapes[]{enroll_dims, magnitude_dims, context_dims,
                                         kStateShape.data(), kStateShape.data()};
        for (std::size_t i = 0; i < 5; ++i) {
            status = Signature(api, chunk.get(), true, i, kInputs[i], input_shapes[i], i == 0 ? 2 : 3);
            if (!status.ok()) return status;
        }
        status = Signature(api, chunk.get(), false, 0, kOutputs[0], frames_dims, 3);
        if (!status.ok()) return status;
        for (std::size_t i = 1; i < 3; ++i) {
            status = Signature(api, chunk.get(), false, i, kOutputs[i], kStateShape.data(), 3);
            if (!status.ok()) return status;
        }
        return {};
    }
};

struct TargetVoiceStream::Impl {
    std::shared_ptr<TargetVoiceInference::Impl> model;
    std::shared_ptr<const TargetVoiceProfile::Data> profile;
    std::array<float, 1024> input{};
    std::array<float, 5 * kWindow> frames{};
    std::array<std::array<float, kState>, 2> h{}, c{};
    std::array<float, kWindow + 5 * kHop> ola{}, envelope{};
    std::array<float, kWindow> window_squared{};
    // Tensor handles alias the fixed storage above; destroy them first.
    std::array<Value, 3> wave_values, frame_values;  // K=4,5,2 (flush).
    std::array<Value, 2> h_values, c_values;
    Value magnitude_value, context_value;
    std::size_t state_bank = 0;
    bool first = true, finished = false, failed = false;

    Status Initialize() noexcept {
        const OrtApi* api = model->api;
        constexpr double pi = 3.1415926535897932384626433832795;
        for (std::size_t i = 0; i < kWindow; ++i) {
            // Match core.py: cast Hann to Float32 before squaring.
            const float hann = static_cast<float>(0.5 - 0.5 * std::cos(2.0 * pi * i / kWindow));
            window_squared[i] = hann * hann;
        }
        const std::size_t ks[]{4, 5, 2};
        for (std::size_t i = 0; i < 3; ++i) {
            const std::int64_t wave_shape[]{1, static_cast<std::int64_t>(ks[i] * kHop + kHistory)};
            const std::int64_t frame_shape[]{1, static_cast<std::int64_t>(ks[i]), kWindow};
            Status status = Tensor(api, model->memory.get(), input.data(), ks[i] * kHop + kHistory,
                                   wave_shape, 2, &wave_values[i]);
            if (!status.ok()) return status;
            status = Tensor(api, model->memory.get(), frames.data(), ks[i] * kWindow,
                            frame_shape, 3, &frame_values[i]);
            if (!status.ok()) return status;
        }
        for (std::size_t i = 0; i < 2; ++i) {
            Status status = Tensor(api, model->memory.get(), h[i].data(), kState,
                                   kStateShape.data(), 3, &h_values[i]);
            if (!status.ok()) return status;
            status = Tensor(api, model->memory.get(), c[i].data(), kState,
                            kStateShape.data(), 3, &c_values[i]);
            if (!status.ok()) return status;
        }
        Status status = Tensor(api, model->memory.get(), const_cast<float*>(profile->magnitude.data()),
                               kMagnitude, kMagnitudeShape.data(), 3, &magnitude_value);
        if (!status.ok()) return status;
        return Tensor(api, model->memory.get(), const_cast<float*>(profile->context.data()),
                      kContext, kContextShape.data(), 3, &context_value);
    }

    Status Run(std::size_t geometry, std::size_t k, float* output, std::size_t* count) noexcept {
        const OrtApi* api = model->api;
        const std::size_t next = state_bank ^ 1;
        const OrtValue* inputs[]{wave_values[geometry].get(), magnitude_value.get(), context_value.get(),
                                 h_values[state_bank].get(), c_values[state_bank].get()};
        OrtValue* outputs[]{frame_values[geometry].get(), h_values[next].get(), c_values[next].get()};
        Status status = Check(api, api->Run(model->chunk.get(), nullptr, kInputs, inputs, 5,
                                           kOutputs, 3, outputs), "Run chunk model");
        if (!status.ok()) { failed = true; return status; }
        if (!Finite(frames.data(), k * kWindow) || !Finite(h[next].data(), kState) || !Finite(c[next].data(), kState)) {
            failed = true;
            return Error(Code::kRuntimeError, "Model returned non-finite audio/state");
        }
        const std::size_t done = k * kHop;
        for (std::size_t j = 0; j < k; ++j) {
            for (std::size_t i = 0; i < kWindow; ++i) {
                ola[j * kHop + i] += frames[j * kWindow + i];
                envelope[j * kHop + i] += window_squared[i];
            }
        }
        const std::size_t drop = first ? kPadding : 0;
        for (std::size_t i = drop; i < done; ++i) {
            const float divisor = envelope[i] > 1.0e-11f ? envelope[i] : 1.0f;
            const float sample = ola[i] / divisor * -0.5f;
            if (!std::isfinite(sample)) {
                failed = true;
                return Error(Code::kRuntimeError, "Overlap-add returned non-finite audio");
            }
            output[i - drop] = sample;
        }
        *count = done - drop;
        std::memmove(ola.data(), ola.data() + done, kWindow * sizeof(float));
        std::memmove(envelope.data(), envelope.data() + done, kWindow * sizeof(float));
        std::fill(ola.begin() + kWindow, ola.end(), 0.0f);
        std::fill(envelope.begin() + kWindow, envelope.end(), 0.0f);
        std::memmove(input.data(), input.data() + done, kHistory * sizeof(float));
        state_bank = next;
        first = false;
        return {};
    }
};

bool TargetVoiceProfile::valid() const noexcept { return static_cast<bool>(data_); }
std::array<std::int64_t, 3> TargetVoiceProfile::magnitude_shape() const noexcept {
    return data_ ? kMagnitudeShape : std::array<std::int64_t, 3>{};
}
std::array<std::int64_t, 3> TargetVoiceProfile::context_shape() const noexcept {
    return data_ ? kContextShape : std::array<std::int64_t, 3>{};
}
const char* TargetVoiceInference::RuntimeVersion() noexcept { return OrtGetApiBase()->GetVersionString(); }
bool TargetVoiceInference::loaded() const noexcept { return static_cast<bool>(std::atomic_load(&impl_)); }
Status TargetVoiceInference::LoadModel(const char* enroll_path, const char* chunk_path,
                                      const TargetVoiceOptions& options) noexcept {
    if (!enroll_path || !*enroll_path || !chunk_path || !*chunk_path ||
        options.intra_op_threads < 1 || options.intra_op_threads > 64)
        return Error(Code::kInvalidArgument, "Model paths and 1..64 threads are required");
    try {
        auto next = std::make_shared<Impl>();
        const Status status = next->Initialize(enroll_path, chunk_path, options);
        if (!status.ok()) return status;
        std::atomic_store(&impl_, std::move(next));
        return {};
    } catch (const std::bad_alloc&) { return Error(Code::kOutOfMemory, "Model allocation failed"); }
      catch (const std::exception& e) { return Error(Code::kRuntimeError, "Model initialization failed", e.what()); }
      catch (...) { return Error(Code::kRuntimeError, "Model initialization failed"); }
}
Status TargetVoiceInference::Enroll(const float* samples, std::size_t count,
                                   TargetVoiceProfile* profile) const noexcept {
    if (!profile || count != kEnrollmentSamples || !Normalized(samples, count))
        return Error(Code::kInvalidArgument, "Enrollment requires 48000 finite normalized samples");
    double energy = 0.0;
    for (std::size_t i = 0; i < count; ++i) energy += static_cast<double>(samples[i]) * samples[i];
    if (energy / count <= 1.0e-10) return Error(Code::kInvalidArgument, "Enrollment is silent");
    const auto model = std::atomic_load(&impl_);
    if (!model) return Error(Code::kNotLoaded, "LoadModel must succeed before enrollment");
    try {
        const OrtApi* api = model->api;
        auto data = std::make_shared<TargetVoiceProfile::Data>();
        Value input, magnitude, context;
        const std::int64_t input_shape[]{1, static_cast<std::int64_t>(count)};
        Status status = Tensor(api, model->memory.get(), const_cast<float*>(samples), count, input_shape, 2, &input);
        if (!status.ok()) return status;
        status = Tensor(api, model->memory.get(), data->magnitude.data(), kMagnitude, kMagnitudeShape.data(), 3, &magnitude);
        if (!status.ok()) return status;
        status = Tensor(api, model->memory.get(), data->context.data(), kContext, kContextShape.data(), 3, &context);
        if (!status.ok()) return status;
        const char* input_names[]{"enroll"};
        const char* output_names[]{"enroll_mag", "context"};
        const OrtValue* inputs[]{input.get()};
        OrtValue* outputs[]{magnitude.get(), context.get()};
        TV_CHECK(api->Run(model->enrollment.get(), nullptr, input_names, inputs, 1, output_names, 2, outputs));
        if (!Finite(data->magnitude.data(), kMagnitude) || !Finite(data->context.data(), kContext))
            return Error(Code::kRuntimeError, "Enrollment returned non-finite features");
        profile->data_ = std::move(data);
        return {};
    } catch (const std::bad_alloc&) { return Error(Code::kOutOfMemory, "Enrollment allocation failed"); }
      catch (const std::exception& e) { return Error(Code::kRuntimeError, "Enrollment failed", e.what()); }
      catch (...) { return Error(Code::kRuntimeError, "Enrollment failed"); }
}
Status TargetVoiceInference::CreateStream(const TargetVoiceProfile& profile,
                                         std::unique_ptr<TargetVoiceStream>* stream) const noexcept {
    if (!stream || !profile.data_) return Error(Code::kInvalidArgument, "A valid owner profile and output are required");
    const auto model = std::atomic_load(&impl_);
    if (!model) return Error(Code::kNotLoaded, "LoadModel must succeed before creating a stream");
    try {
        auto impl = std::make_unique<TargetVoiceStream::Impl>();
        impl->model = model;
        impl->profile = profile.data_;
        const Status status = impl->Initialize();
        if (!status.ok()) return status;
        std::unique_ptr<TargetVoiceStream> next(new TargetVoiceStream(std::move(impl)));
        *stream = std::move(next);
        return {};
    } catch (const std::bad_alloc&) { return Error(Code::kOutOfMemory, "Stream allocation failed"); }
      catch (const std::exception& e) { return Error(Code::kRuntimeError, "Stream creation failed", e.what()); }
      catch (...) { return Error(Code::kRuntimeError, "Stream creation failed"); }
}
TargetVoiceStream::TargetVoiceStream(std::unique_ptr<Impl> impl) noexcept : impl_(std::move(impl)) {}
TargetVoiceStream::~TargetVoiceStream() = default;
void TargetVoiceStream::Reset() noexcept {
    for (auto& state : impl_->h) state.fill(0.0f);
    for (auto& state : impl_->c) state.fill(0.0f);
    impl_->input.fill(0.0f);
    impl_->frames.fill(0.0f);
    impl_->ola.fill(0.0f);
    impl_->envelope.fill(0.0f);
    impl_->state_bank = 0;
    impl_->first = true;
    impl_->finished = impl_->failed = false;
}
Status TargetVoiceStream::Push(const float* input, std::size_t count, float* output,
                              std::size_t capacity, std::size_t* produced) noexcept {
    if (produced) *produced = 0;
    if (!produced || !output || capacity < TargetVoiceInference::kChunkSamples ||
        count != TargetVoiceInference::kChunkSamples || !Normalized(input, count))
        return Error(Code::kInvalidArgument, "Push requires 640 finite normalized samples and output capacity >=640");
    if (impl_->finished || impl_->failed) return Error(Code::kStreamFinished, "Reset is required before Push");
    if (impl_->first) {
        for (std::size_t i = 0; i < kPadding; ++i) impl_->input[i] = input[kPadding - i];
        std::copy_n(input, count, impl_->input.data() + kPadding);
    } else {
        std::copy_n(input, count, impl_->input.data() + kHistory);
    }
    return impl_->Run(impl_->first ? 0 : 1, impl_->first ? 4 : 5, output, produced);
}
Status TargetVoiceStream::Flush(float* output, std::size_t capacity, std::size_t* produced) noexcept {
    if (produced) *produced = 0;
    if (!produced || !output || capacity < TargetVoiceInference::kChunkSamples)
        return Error(Code::kInvalidArgument, "Flush requires output capacity >=640");
    if (impl_->finished || impl_->failed) return Error(Code::kStreamFinished, "Reset is required before Flush");
    if (impl_->first) { impl_->finished = true; return {}; }
    for (std::size_t i = 0; i < kPadding; ++i) impl_->input[kHistory + i] = impl_->input[kHistory - 2 - i];
    Status status = impl_->Run(2, 2, output, produced);
    if (!status.ok()) return status;
    for (std::size_t i = 0; i < kHistory - 2 * kHop; ++i) {
        const float divisor = impl_->envelope[i] > 1.0e-11f ? impl_->envelope[i] : 1.0f;
        const float sample = impl_->ola[i] / divisor * -0.5f;
        if (!std::isfinite(sample)) {
            impl_->failed = true;
            *produced = 0;
            return Error(Code::kRuntimeError, "Final overlap-add returned non-finite audio");
        }
        output[*produced + i] = sample;
    }
    *produced = kHistory;
    impl_->finished = true;
    return {};
}
#undef TV_CHECK
}  // namespace miccontrol
