package org.telegram.messenger;

import android.content.SharedPreferences;
import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.os.Build;
import android.text.TextUtils;

import org.telegram.tgnet.TLRPC;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileReader;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.ShortBuffer;
import java.security.MessageDigest;
import java.util.Locale;

/**
 * Danygramm on-device transcription of voice and round video messages with whisper.cpp.
 * Audio never leaves the device; only the model file is downloaded once from Hugging Face.
 */
public final class DanygrammTranscriber {

    public static final int MODE_TELEGRAM = 0;
    public static final int MODE_FAST = 1;
    public static final int MODE_ACCURATE = 2;

    private static final String PREF_MODE = "danygrammTranscribeMode";
    private static final int MAX_SECONDS = 15 * 60;
    private static final long UNLOAD_DELAY_MS = 90_000;

    public interface Callback {
        /** UI thread. Intermediate status text (download progress / recognizing). */
        void onProgress(String status);
        /** UI thread. Final text, or null on failure (error already reported to the user). */
        void onResult(String text);
    }

    public static final class Model {
        public final int mode;
        public final String fileName;
        public final long size;
        public final String sha256;

        Model(int mode, String fileName, long size, String sha256) {
            this.mode = mode;
            this.fileName = fileName;
            this.size = size;
            this.sha256 = sha256;
        }

        public String url() {
            return "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/" + fileName;
        }

        public File file() {
            return new File(modelDir(), fileName);
        }

        public int sizeMb() {
            return (int) Math.round(size / 1048576.0);
        }
    }

    private static final Model FAST = new Model(MODE_FAST, "ggml-base-q5_1.bin", 59707625L,
            "422f1ae452ade6f30a004d7e5c6a43195e4433bc370bf23fac9cc591f01a8898");
    private static final Model ACCURATE = new Model(MODE_ACCURATE, "ggml-small-q5_1.bin", 190085487L,
            "ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb");

    private static final DispatchQueue queue = new DispatchQueue("danygrammWhisper");
    private static Boolean cpuSupported;
    private static boolean libraryLoaded;
    // Posted on the UI thread after idle time; the actual unload runs on the worker queue so the UI never waits on whisper.
    private static final Runnable unloadRunnable = () -> queue.postRunnable(() -> {
        if (libraryLoaded) nativeUnloadModel();
    });

    private DanygrammTranscriber() {
    }

    // ---- settings ----

    private static SharedPreferences prefs() {
        return MessagesController.getGlobalMainSettings();
    }

    public static int getMode() {
        int mode = prefs().getInt(PREF_MODE, MODE_FAST);
        return mode >= MODE_TELEGRAM && mode <= MODE_ACCURATE ? mode : MODE_FAST;
    }

    public static void setMode(int mode) {
        prefs().edit().putInt(PREF_MODE, mode).apply();
    }

    /** Local transcription replaces Telegram's server transcription (and its Premium limits). */
    public static boolean isEnabled() {
        return getMode() != MODE_TELEGRAM && isCpuSupported();
    }

    public static Model currentModel() {
        return getMode() == MODE_ACCURATE ? ACCURATE : FAST;
    }

    public static Model model(int mode) {
        return mode == MODE_ACCURATE ? ACCURATE : FAST;
    }

    public static File modelDir() {
        return new File(ApplicationLoader.applicationContext.getFilesDir(), "danygramm-whisper");
    }

    public static boolean isModelReady(Model model) {
        File file = model.file();
        return file.exists() && file.length() == model.size;
    }

    public static long downloadedModelsBytes() {
        long total = 0;
        File[] files = modelDir().listFiles();
        if (files != null) {
            for (File f : files) total += f.length();
        }
        return total;
    }

    public static void deleteModels() {
        queue.postRunnable(() -> {
            AndroidUtilities.cancelRunOnUIThread(unloadRunnable);
            if (libraryLoaded) nativeUnloadModel();
            File[] files = modelDir().listFiles();
            if (files != null) {
                for (File f : files) {
                    //noinspection ResultOfMethodCallIgnored
                    f.delete();
                }
            }
        });
    }

    /** The bundled library is built for ARMv8.2 (fp16 + dot product); older cores would crash with SIGILL. */
    public static boolean isCpuSupported() {
        if (cpuSupported != null) return cpuSupported;
        boolean supported = false;
        String[] abis = Build.SUPPORTED_ABIS;
        if (abis != null && abis.length > 0 && "arm64-v8a".equals(abis[0])) {
            try (BufferedReader reader = new BufferedReader(new FileReader("/proc/cpuinfo"))) {
                String line;
                boolean fp16 = false, dot = false;
                while ((line = reader.readLine()) != null) {
                    if (line.startsWith("Features")) {
                        fp16 = line.contains(" asimdhp") && line.contains(" fphp");
                        dot = line.contains(" asimddp");
                        break;
                    }
                }
                supported = fp16 && dot;
            } catch (IOException e) {
                FileLog.e(e);
            }
        }
        cpuSupported = supported;
        return supported;
    }

    // ---- transcription ----

    public static void transcribe(MessageObject messageObject, Callback callback) {
        final Model model = currentModel();
        final int account = messageObject.currentAccount;
        final TLRPC.Message message = messageObject.messageOwner;
        final boolean round = messageObject.isRoundVideo();
        final File[] mediaFile = {resolveFile(account, message)};
        if (mediaFile[0] == null || !mediaFile[0].exists()) {
            TLRPC.Document document = messageObject.getDocument();
            if (document != null) {
                FileLoader.getInstance(account).loadFile(document, messageObject, FileLoader.PRIORITY_HIGH, 0);
            }
        }
        queue.postRunnable(() -> {
            AndroidUtilities.cancelRunOnUIThread(unloadRunnable);
            String result = null;
            int error = R.string.DanygrammTranscribeFailed;
            try {
                if (!isModelReady(model)) {
                    if (!downloadModel(model, callback)) {
                        error = R.string.DanygrammTranscribeDownloadFailed;
                        throw new IOException("model download failed");
                    }
                }
                File file = mediaFile[0];
                long deadline = System.currentTimeMillis() + 120_000;
                while ((file == null || !file.exists() || file.length() == 0) && System.currentTimeMillis() < deadline) {
                    Thread.sleep(250);
                    file = resolveFile(account, message);
                }
                if (file == null || !file.exists()) {
                    error = R.string.DanygrammTranscribeNoFile;
                    throw new IOException("media file is not downloaded");
                }
                postProgress(callback, LocaleController.getString(R.string.DanygrammTranscribeWorking));
                float[] pcm = round ? decodeWithMediaCodec(file) : decodeOpus16k(file.getAbsolutePath(), MAX_SECONDS);
                if (pcm == null || pcm.length == 0) {
                    throw new IOException("audio decode failed");
                }
                if (!loadLibrary() || !nativeLoadModel(model.file().getAbsolutePath())) {
                    throw new IOException("whisper model load failed");
                }
                int threads = Math.max(2, Math.min(4, Runtime.getRuntime().availableProcessors() - 2));
                String raw = nativeTranscribe(pcm, "auto", threads);
                if (raw == null) {
                    throw new IOException("whisper failed");
                }
                int newline = raw.indexOf('\n');
                result = cleanup(newline >= 0 ? raw.substring(newline + 1) : raw);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } catch (Throwable e) {
                FileLog.e(e);
            }
            if (libraryLoaded) {
                AndroidUtilities.runOnUIThread(unloadRunnable, UNLOAD_DELAY_MS);
            }
            final String finalResult = result;
            final int finalError = error;
            AndroidUtilities.runOnUIThread(() -> {
                if (finalResult == null) {
                    try {
                        org.telegram.ui.Components.BulletinFactory.global().createErrorBulletin(LocaleController.getString(finalError)).show();
                    } catch (Exception ignore) {
                    }
                }
                callback.onResult(finalResult);
            });
        });
    }

    private static File resolveFile(int account, TLRPC.Message message) {
        if (message == null) return null;
        if (!TextUtils.isEmpty(message.attachPath)) {
            File f = new File(message.attachPath);
            if (f.exists()) return f;
        }
        return FileLoader.getInstance(account).getPathToMessage(message);
    }

    private static String cleanup(String text) {
        if (text == null) return "";
        return text.replace("[BLANK_AUDIO]", "").replaceAll("\\s+", " ").trim();
    }

    private static void postProgress(Callback callback, String text) {
        AndroidUtilities.runOnUIThread(() -> callback.onProgress(text));
    }

    private static synchronized boolean loadLibrary() {
        if (libraryLoaded) return true;
        try {
            System.loadLibrary("danywhisper");
            libraryLoaded = true;
        } catch (Throwable e) {
            FileLog.e(e);
        }
        return libraryLoaded;
    }

    private static boolean downloadModel(Model model, Callback callback) {
        File dir = modelDir();
        if (!dir.exists() && !dir.mkdirs()) return false;
        File part = new File(dir, model.fileName + ".part");
        HttpURLConnection connection = null;
        try {
            URL url = new URL(model.url());
            for (int redirects = 0; ; redirects++) {
                connection = (HttpURLConnection) url.openConnection();
                connection.setInstanceFollowRedirects(false);
                connection.setConnectTimeout(20_000);
                connection.setReadTimeout(60_000);
                connection.setRequestProperty("User-Agent", "Danygramm");
                int code = connection.getResponseCode();
                if (code >= 300 && code < 400 && redirects < 5) {
                    String location = connection.getHeaderField("Location");
                    connection.disconnect();
                    url = new URL(url, location);
                    if (!"https".equals(url.getProtocol())) return false;
                    continue;
                }
                if (code != 200) return false;
                break;
            }
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            long received = 0;
            int lastPercent = -1;
            try (InputStream in = connection.getInputStream(); FileOutputStream out = new FileOutputStream(part)) {
                byte[] buffer = new byte[64 * 1024];
                int read;
                while ((read = in.read(buffer)) != -1) {
                    out.write(buffer, 0, read);
                    digest.update(buffer, 0, read);
                    received += read;
                    if (received > model.size) return false;
                    int percent = (int) (received * 100 / model.size);
                    if (percent != lastPercent) {
                        lastPercent = percent;
                        postProgress(callback, LocaleController.formatString(R.string.DanygrammTranscribeDownloading, percent, model.sizeMb()));
                    }
                }
                out.getFD().sync();
            }
            if (received != model.size || !model.sha256.equals(hex(digest.digest()))) {
                FileLog.e("danygramm whisper: model checksum mismatch");
                return false;
            }
            return part.renameTo(model.file());
        } catch (Exception e) {
            FileLog.e(e);
            return false;
        } finally {
            if (connection != null) connection.disconnect();
            if (part.exists() && !model.file().exists()) {
                //noinspection ResultOfMethodCallIgnored
                part.delete();
            }
        }
    }

    private static String hex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) sb.append(String.format(Locale.US, "%02x", b));
        return sb.toString();
    }

    /** Round videos (MP4/AAC): decode the audio track with MediaCodec, mix to mono and resample to 16 kHz. */
    private static float[] decodeWithMediaCodec(File file) throws IOException {
        MediaExtractor extractor = new MediaExtractor();
        MediaCodec codec = null;
        try {
            extractor.setDataSource(file.getAbsolutePath());
            int track = -1;
            MediaFormat format = null;
            for (int i = 0; i < extractor.getTrackCount(); i++) {
                MediaFormat f = extractor.getTrackFormat(i);
                String mime = f.getString(MediaFormat.KEY_MIME);
                if (mime != null && mime.startsWith("audio/")) {
                    track = i;
                    format = f;
                    break;
                }
            }
            if (track < 0) return null;
            extractor.selectTrack(track);
            int sampleRate = format.getInteger(MediaFormat.KEY_SAMPLE_RATE);
            int channels = format.getInteger(MediaFormat.KEY_CHANNEL_COUNT);
            codec = MediaCodec.createDecoderByType(format.getString(MediaFormat.KEY_MIME));
            codec.configure(format, null, null, 0);
            codec.start();

            float[] mono = new float[Math.max(16000, sampleRate * 30)];
            int count = 0;
            int maxCount = sampleRate * MAX_SECONDS;
            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            boolean inputDone = false, outputDone = false;
            while (!outputDone && count < maxCount) {
                if (!inputDone) {
                    int in = codec.dequeueInputBuffer(10_000);
                    if (in >= 0) {
                        ByteBuffer buffer = codec.getInputBuffer(in);
                        int size = buffer == null ? -1 : extractor.readSampleData(buffer, 0);
                        if (size < 0) {
                            codec.queueInputBuffer(in, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM);
                            inputDone = true;
                        } else {
                            codec.queueInputBuffer(in, 0, size, extractor.getSampleTime(), 0);
                            extractor.advance();
                        }
                    }
                }
                int out = codec.dequeueOutputBuffer(info, 10_000);
                if (out == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    MediaFormat outFormat = codec.getOutputFormat();
                    sampleRate = outFormat.getInteger(MediaFormat.KEY_SAMPLE_RATE);
                    channels = outFormat.getInteger(MediaFormat.KEY_CHANNEL_COUNT);
                    maxCount = sampleRate * MAX_SECONDS;
                } else if (out >= 0) {
                    ByteBuffer buffer = codec.getOutputBuffer(out);
                    if (buffer != null && info.size > 0) {
                        buffer.position(info.offset);
                        buffer.limit(info.offset + info.size);
                        ShortBuffer shorts = buffer.order(ByteOrder.nativeOrder()).asShortBuffer();
                        int frames = shorts.remaining() / Math.max(1, channels);
                        if (count + frames > mono.length) {
                            float[] grown = new float[Math.max(mono.length * 2, count + frames)];
                            System.arraycopy(mono, 0, grown, 0, count);
                            mono = grown;
                        }
                        for (int i = 0; i < frames; i++) {
                            float sum = 0;
                            for (int c = 0; c < channels; c++) sum += shorts.get();
                            mono[count++] = sum / channels / 32768f;
                        }
                    }
                    codec.releaseOutputBuffer(out, false);
                    if ((info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) outputDone = true;
                }
            }
            return resampleTo16k(mono, count, sampleRate);
        } finally {
            if (codec != null) {
                try {
                    codec.stop();
                } catch (Exception ignore) {
                }
                codec.release();
            }
            extractor.release();
        }
    }

    private static float[] resampleTo16k(float[] in, int count, int rate) {
        if (count <= 0 || rate <= 0) return null;
        if (rate == 16000) {
            float[] out = new float[count];
            System.arraycopy(in, 0, out, 0, count);
            return out;
        }
        double step = rate / 16000.0;
        int outCount = (int) (count / step);
        float[] out = new float[outCount];
        int window = Math.max(1, (int) Math.round(step));
        for (int i = 0; i < outCount; i++) {
            int start = (int) (i * step);
            float sum = 0;
            int n = 0;
            for (int k = 0; k < window && start + k < count; k++, n++) sum += in[start + k];
            out[i] = n > 0 ? sum / n : 0;
        }
        return out;
    }

    // ---- native ----

    /** Implemented in jni/audio.c (libtmessages): Ogg/Opus voice note → 16 kHz mono float PCM. */
    private static native float[] decodeOpus16k(String path, int maxSeconds);

    private static native boolean nativeLoadModel(String path);

    private static native void nativeUnloadModel();

    public static native void nativeAbort();

    private static native String nativeTranscribe(float[] pcm, String language, int threads);
}
