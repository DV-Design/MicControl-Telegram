package org.danygramm.voiceprobe;

final class NativeProbe {
    static {
        System.loadLibrary("onnxruntime");
        System.loadLibrary("voiceprobe");
    }

    /** Synchronous call made only by the single diagnostic worker. */
    static native String run(String enroll, String chunk, String reference, String mixture,
                             ProbeRun.Token token);

    private NativeProbe() {}
}
