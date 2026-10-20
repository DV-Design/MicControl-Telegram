package org.danygramm.voiceprobe;

import android.content.Context;
import android.os.Build;
import android.os.SystemClock;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.concurrent.CancellationException;
import java.util.concurrent.atomic.AtomicBoolean;

/** One application-scoped worker. It never retains an Activity or UI callback. */
final class ProbeRun {
    static final int BLOCKS = 100;
    private static long nextId;
    private static volatile Token current;

    static final class Token {
        final long id;
        final long startedAt = SystemClock.elapsedRealtime();
        final AtomicBoolean cancelled = new AtomicBoolean();
        volatile int phase;
        volatile int completedBlocks;
        volatile boolean done;
        volatile String result;

        Token(long id) { this.id = id; }
        // Called by JNI on this same worker thread, including between Push calls.
        public boolean isCancelled() { return cancelled.get(); }
        void check() { if (isCancelled()) throw new CancellationException(); }
    }

    static Token current() { return current; }

    static synchronized Token start(Context context) {
        if (current != null && !current.done) return null;
        Token token = new Token(++nextId);
        current = token;
        Context application = context.getApplicationContext();
        new Thread(() -> execute(application, token), "Danygramm-voice-probe").start();
        return token;
    }

    private static void execute(Context context, Token token) {
        try {
            JSONObject manifest = new JSONObject(readManifest(context));
            File directory = new File(context.getNoBackupFilesDir(), "verified-probe");
            if (!directory.isDirectory() && !directory.mkdirs()) throw new IllegalStateException("Cannot create private test directory");
            JSONArray assets = manifest.getJSONArray("assets");
            for (int i = 0; i < assets.length(); i++) extract(context, directory, assets.getJSONObject(i), token);
            token.check();
            String raw = NativeProbe.run(new File(directory, "enroll.onnx").getPath(),
                    new File(directory, "chunk_int8_full.onnx").getPath(),
                    new File(directory, "reference-a.f32").getPath(),
                    new File(directory, "mix-4s.f32").getPath(), token);
            token.check();
            JSONObject result = new JSONObject(raw);
            result.put("diagnostic_version", "0.1");
            result.put("device", new JSONObject().put("manufacturer", Build.MANUFACTURER)
                    .put("model", Build.MODEL).put("hardware", Build.HARDWARE)
                    .put("abis", new JSONArray(Arrays.asList(Build.SUPPORTED_ABIS)))
                    .put("api", Build.VERSION.SDK_INT).put("android_release", Build.VERSION.RELEASE));
            result.put("sample", "bundled_public_audio_not_microphone");
            result.put("quality_gate", "owner_absence_failed_no_call_integration");
            result.put("asset_provenance", manifest.getJSONObject("provenance"));
            result.put("assets_sha256_verified", true);
            token.result = result.toString(2);
        } catch (CancellationException cancelled) {
            token.result = "{\"status\":\"cancelled\"}";
        } catch (Throwable error) {
            try {
                token.result = new JSONObject().put("status", "error")
                        .put("error_type", error.getClass().getSimpleName())
                        .put("detail", String.valueOf(error.getMessage())).toString(2);
            } catch (Exception ignored) { token.result = "{\"status\":\"error\"}"; }
        } finally {
            // Native local objects have already been destroyed on this worker.
            token.done = true;
        }
    }

    private static String readManifest(Context context) throws Exception {
        try (InputStream input = context.getAssets().open("probe-manifest.json");
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] bytes = new byte[4096];
            for (int n; (n = input.read(bytes)) != -1;) {
                if (out.size() + n > 65536) throw new IllegalStateException("Oversized asset manifest");
                out.write(bytes, 0, n);
            }
            return new String(out.toByteArray(), StandardCharsets.UTF_8);
        }
    }

    private static void extract(Context context, File directory, JSONObject entry, Token token) throws Exception {
        token.check();
        String name = entry.getString("name");
        String expected = entry.getString("sha256");
        long size = entry.getLong("bytes");
        if (!name.matches("[A-Za-z0-9_.-]{1,80}") || !expected.matches("[a-f0-9]{64}")
                || size <= 0 || size > 128L * 1024 * 1024) throw new IllegalStateException("Invalid asset manifest");
        File output = new File(directory, name);
        if (output.isFile() && output.length() == size && digest(output, token).equals(expected)) return;
        File partial = new File(directory, name + ".part");
        try {
            MessageDigest hash = MessageDigest.getInstance("SHA-256");
            long copied = 0;
            try (InputStream input = context.getAssets().open(name);
                 FileOutputStream destination = new FileOutputStream(partial)) {
                byte[] bytes = new byte[65536];
                for (int n; (n = input.read(bytes)) != -1;) {
                    token.check();
                    copied += n;
                    if (copied > size) throw new IllegalStateException("Oversized bundled asset");
                    hash.update(bytes, 0, n);
                    destination.write(bytes, 0, n);
                }
                destination.getFD().sync();
            }
            token.check();
            if (copied != size || !hex(hash.digest()).equals(expected)) throw new IllegalStateException("Bundled asset SHA256 mismatch");
            if (output.exists() && !output.delete()) throw new IllegalStateException("Cannot replace verified test file");
            if (!partial.renameTo(output)) throw new IllegalStateException("Cannot finish verified test file");
        } finally {
            if (partial.exists()) partial.delete();
        }
    }

    private static String digest(File file, Token token) throws Exception {
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        try (InputStream input = new FileInputStream(file)) {
            byte[] bytes = new byte[65536];
            for (int n; (n = input.read(bytes)) != -1;) { token.check(); hash.update(bytes, 0, n); }
        }
        return hex(hash.digest());
    }

    private static String hex(byte[] bytes) {
        StringBuilder result = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) result.append(String.format(java.util.Locale.US, "%02x", value & 255));
        return result.toString();
    }
    private ProbeRun() {}
}
