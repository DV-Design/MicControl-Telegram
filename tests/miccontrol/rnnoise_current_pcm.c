/* Research-only FloatS16 PCM adapter for the unchanged upstream RNNoise C API.
 * Input/output: host little-endian float32 mono48k, whole 480-sample frames.
 * No gain exponent, normalization, VAD gate, clipping or PCM16 conversion.
 */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "rnnoise.h"

int main(int argc, char **argv) {
  const uint32_t endian = 1;
  if (argc != 3 || *(const unsigned char *)&endian != 1 || sizeof(float) != 4) {
    fprintf(stderr, "usage: rnnoise-current-pcm input-float-s16.f32 output.f32\n");
    return 2;
  }
  FILE *input = fopen(argv[1], "rb");
  FILE *output = fopen(argv[2], "wb");
  DenoiseState *state = rnnoise_create(NULL);
  int status = 1;
  size_t frames = 0;
  float samples[480], processed[480], peak = 0;
  if (!input || !output || !state || rnnoise_get_frame_size() != 480) {
    fprintf(stderr, "cannot initialize files/default RNNoise model\n");
    goto done;
  }
  for (;;) {
    size_t count = fread(samples, 1, sizeof(samples), input);
    if (count == 0 && feof(input)) break;
    if (count != sizeof(samples)) {
      fprintf(stderr, "input must contain complete Float32/480 frames\n");
      goto done;
    }
    for (size_t i = 0; i < 480; ++i) {
      if (!isfinite(samples[i])) {
        fprintf(stderr, "non-finite input\n");
        goto done;
      }
    }
    const float probability = rnnoise_process_frame(state, processed, samples);
    if (!isfinite(probability)) goto done;
    for (size_t i = 0; i < 480; ++i) {
      if (!isfinite(processed[i])) {
        fprintf(stderr, "non-finite RNNoise output\n");
        goto done;
      }
      peak = fmaxf(peak, fabsf(processed[i]));
    }
    if (fwrite(processed, 1, sizeof(processed), output) != sizeof(processed)) goto done;
    ++frames;
  }
  if (ferror(input) || frames == 0 || fflush(output) != 0) goto done;
  printf("{\"frames\":%zu,\"samples48k\":%zu,\"frameSize\":480,"
         "\"stateBytes\":%d,\"maxAbsFloatS16\":%.9g,\"allFinite\":true}\n",
         frames, frames * 480, rnnoise_get_size(), (double)peak);
  status = 0;
done:
  if (state) rnnoise_destroy(state);
  if (input) fclose(input);
  if (output && fclose(output) != 0) status = 1;
  return status;
}
