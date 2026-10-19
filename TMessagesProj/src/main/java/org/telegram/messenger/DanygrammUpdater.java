package org.telegram.messenger;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Build;
import android.os.SystemClock;
import android.provider.Settings;
import androidx.core.content.FileProvider;
import org.json.JSONObject;
import org.telegram.ui.ActionBar.AlertDialog;
import org.telegram.ui.ActionBar.BaseFragment;
import org.telegram.ui.LaunchActivity;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.concurrent.atomic.AtomicBoolean;

/** Public release metadata only. Never sends Telegram credentials or chat data. */
public final class DanygrammUpdater {
    public static final String PACKAGE = "org.miccontrol.messenger.web";
    public static final String CERTIFICATE = "59e104c1d8b66e20c47119aed387993df655475cdd3153fb21bfb3752d85debe";
    private static final String REPOSITORY = "https://github.com/DV-Design/MicControl-Telegram/releases/download/";
    private static final String LATEST = "https://api.github.com/repos/DV-Design/MicControl-Telegram/releases/latest";
    private static final String APK = "Danygramm-arm64.apk";
    private static final long MAX_APK = 160L * 1024 * 1024;
    private static final AtomicBoolean busy = new AtomicBoolean();

    public static final class Update {
        public final int version;
        public final long size;
        public final String sha256;
        public final String url;
        public Update(JSONObject object, String baseUrl) throws Exception {
            if (!PACKAGE.equals(object.getString("package")) || !APK.equals(object.getString("apk"))) throw new SecurityException();
            long code = object.getLong("versionCode");
            if (code <= 0 || code > Integer.MAX_VALUE) throw new SecurityException();
            version = (int) code;
            size = object.getLong("size");
            sha256 = object.getString("sha256");
            if (size <= 0 || size > MAX_APK || !sha256.matches("[a-f0-9]{64}")) throw new SecurityException();
            if (!baseUrl.startsWith(REPOSITORY) || baseUrl.length() <= REPOSITORY.length() || !baseUrl.endsWith("/")) throw new SecurityException();
            String tag = baseUrl.substring(REPOSITORY.length(), baseUrl.length() - 1);
            validateTag(tag);
            url = baseUrl + APK;
        }
    }

    private static void validateTag(String tag) {
        if (!tag.matches("[A-Za-z0-9._-]{1,80}") || tag.equals(".") || tag.equals("..")) throw new SecurityException();
    }

    /** A cancellation closes the active request, including redirects and blocked reads. */
    private static final class Transfer {
        final AtomicBoolean cancelled = new AtomicBoolean();
        final long deadline;
        volatile HttpURLConnection connection;
        volatile boolean finished;
        Transfer(long timeout) { deadline = SystemClock.elapsedRealtime() + timeout; }
        void check() throws IOException {
            if (cancelled.get() || SystemClock.elapsedRealtime() >= deadline) throw new IOException();
        }
        void cancel() {
            cancelled.set(true);
            if (finished) return;
            HttpURLConnection active = connection;
            if (active != null) active.disconnect();
        }
        void finish() {
            finished = true;
            HttpURLConnection active = connection;
            if (active != null) active.disconnect();
        }
        int timeout(int maximum) throws IOException {
            check();
            return (int) Math.max(1, Math.min(maximum, deadline - SystemClock.elapsedRealtime()));
        }
    }

    private static String text(int resource) { return LocaleController.getString(resource); }
    private static long installedVersion(Context context) throws Exception {
        PackageInfo info = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
        return Build.VERSION.SDK_INT >= 28 ? info.getLongVersionCode() : info.versionCode;
    }

    public static void maybeCheck() {
        long now = System.currentTimeMillis();
        if (now - MessagesController.getGlobalMainSettings().getLong("danygrammUpdateCheck", 0) < 86400000L
                || now - MessagesController.getGlobalMainSettings().getLong("danygrammUpdateAttempt", 0) < 3600000L) return;
        BaseFragment fragment = LaunchActivity.getLastFragment();
        if (fragment != null && !fragment.isPaused()) check(fragment, false);
    }

    public static void check(BaseFragment fragment, boolean manual) {
        Activity activity = fragment.getParentActivity();
        if (activity == null || fragment.isPaused()) return;
        if (!busy.compareAndSet(false, true)) {
            if (manual) message(fragment, R.string.DanygrammUpdateBusy);
            return;
        }
        MessagesController.getGlobalMainSettings().edit().putLong("danygrammUpdateAttempt", System.currentTimeMillis()).apply();
        Transfer transfer = new Transfer(60000);
        AlertDialog progress = manual ? progress(fragment, R.string.DanygrammCheckingUpdate, transfer) : null;
        new Thread(() -> {
            Update update = null;
            Exception error = null;
            try {
                JSONObject release;
                try { release = new JSONObject(readText(LATEST, 1024 * 1024, transfer)); }
                catch (java.io.FileNotFoundException noRelease) { release = null; }
                if (release != null) {
                    String tag = release.getString("tag_name");
                    if (release.optBoolean("draft") || release.optBoolean("prerelease")) throw new SecurityException();
                    validateTag(tag);
                    String base = REPOSITORY + tag + "/";
                    Update candidate = new Update(new JSONObject(readText(base + "danygramm-update.json", 4096, transfer)), base);
                    if (candidate.version > installedVersion(activity)) update = candidate;
                }
                transfer.check();
                MessagesController.getGlobalMainSettings().edit().putLong("danygrammUpdateCheck", System.currentTimeMillis()).apply();
            } catch (Exception failure) { error = failure; }
            finally { transfer.finish(); busy.set(false); }
            final Update result = update;
            final Exception failure = error;
            AndroidUtilities.runOnUIThread(() -> {
                if (progress != null) progress.dismiss();
                if (transfer.cancelled.get() || activity.isFinishing() || activity.isDestroyed() || fragment.isPaused()) return;
                if (failure != null) { if (manual) message(fragment, failure instanceof SecurityException ? R.string.DanygrammUpdateInvalid : R.string.DanygrammUpdateError); return; }
                if (result == null) { if (manual) message(fragment, R.string.DanygrammNoUpdate); return; }
                if (!manual && MessagesController.getGlobalMainSettings().getInt("danygrammUpdatePrompt", 0) == result.version) return;
                MessagesController.getGlobalMainSettings().edit().putInt("danygrammUpdatePrompt", result.version).apply();
                fragment.showDialog(new AlertDialog.Builder(activity).setTitle("Danygramm")
                        .setMessage(text(R.string.DanygrammUpdateAvailable))
                        .setPositiveButton(text(R.string.DanygrammUpdateDownload), (dialog, which) -> download(fragment, result))
                        .setNegativeButton(text(R.string.Cancel), null).create());
            });
        }, "Danygramm update check").start();
    }

    private static AlertDialog progress(BaseFragment fragment, int resource, Transfer transfer) {
        AlertDialog dialog = new AlertDialog(fragment.getParentActivity(), 3);
        dialog.setMessage(text(resource));
        dialog.setOnCancelListener(ignored -> transfer.cancel());
        if (fragment.showDialog(dialog, ignored -> { if (!transfer.finished) transfer.cancel(); }) == null) transfer.cancel();
        return dialog;
    }

    private static void download(BaseFragment fragment, Update update) {
        Activity activity = fragment.getParentActivity();
        if (activity == null || fragment.isPaused() || !busy.compareAndSet(false, true)) return;
        Transfer transfer = new Transfer(600000);
        AlertDialog progress = progress(fragment, R.string.DanygrammUpdateDownloading, transfer);
        new Thread(() -> {
            File directory = new File(activity.getFilesDir(), "cache");
            File apk = new File(directory, "danygramm-update-" + update.version + "-" + update.sha256 + ".apk");
            File partial = null;
            Exception error = null;
            try {
                if (!directory.isDirectory() && !directory.mkdirs()) throw new IOException();
                cleanupDownloads(directory, apk);
                if (apk.isFile()) {
                    try { verifyApk(activity, apk, update, installedVersion(activity)); }
                    catch (Exception invalidCache) { if (!apk.delete()) throw new IOException(); }
                }
                if (!apk.isFile()) {
                    partial = File.createTempFile("danygramm-update-", ".part", directory);
                    HttpURLConnection connection = connect(update.url, transfer);
                    if (connection.getContentLength() > update.size) throw new SecurityException();
                    long count = 0;
                    try (InputStream input = connection.getInputStream(); FileOutputStream output = new FileOutputStream(partial)) {
                        byte[] buffer = new byte[65536];
                        int length;
                        while ((length = input.read(buffer)) != -1) {
                            transfer.check();
                            count += length;
                            if (count > update.size) throw new SecurityException();
                            output.write(buffer, 0, length);
                        }
                    }
                    transfer.check();
                    verifyApk(activity, partial, update, installedVersion(activity));
                    if (!partial.renameTo(apk)) throw new IOException();
                }
                transfer.check();
            } catch (Exception failure) { error = failure; }
            finally {
                if (partial != null) partial.delete();
                transfer.finish();
                busy.set(false);
            }
            final Exception failure = error;
            AndroidUtilities.runOnUIThread(() -> {
                progress.dismiss();
                if (transfer.cancelled.get() || activity.isFinishing() || activity.isDestroyed() || fragment.isPaused()) return;
                if (failure != null) { message(fragment, failure instanceof SecurityException ? R.string.DanygrammUpdateInvalid : R.string.DanygrammUpdateError); return; }
                install(fragment, apk);
            });
        }, "Danygramm update download").start();
    }

    /** Keep the current file and two recent verified downloads; only our own names are eligible. */
    private static void cleanupDownloads(File directory, File current) throws IOException {
        File[] files = directory.listFiles((parent, name) ->
                name.matches("danygramm-update-[0-9]+-[a-f0-9]{64}\\.apk")
                        || name.matches("danygramm-update-[A-Za-z0-9-]+\\.part"));
        if (files == null) return;
        java.util.Arrays.sort(files, (a, b) -> Long.compare(b.lastModified(), a.lastModified()));
        int kept = 0;
        for (File file : files) {
            if (file.equals(current) || !file.isFile()) continue;
            if (file.getName().endsWith(".apk") && kept++ < 2) continue;
            if (!file.delete() && file.exists()) throw new IOException();
        }
    }

    private static void install(BaseFragment fragment, File apk) {
        Activity activity = fragment.getParentActivity();
        if (activity == null) return;
        if (Build.VERSION.SDK_INT >= 26 && !activity.getPackageManager().canRequestPackageInstalls()) {
            fragment.showDialog(new AlertDialog.Builder(activity).setTitle("Danygramm")
                    .setMessage(text(R.string.DanygrammUpdateInstallPermission))
                    .setPositiveButton(text(R.string.DanygrammUpdateOpenSettings), (dialog, which) -> {
                        try { activity.startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + activity.getPackageName()))); }
                        catch (RuntimeException unavailable) { message(fragment, R.string.DanygrammSettingsUnavailable); }
                    }).setNegativeButton(text(R.string.Cancel), null).create());
            return;
        }
        try {
            Intent intent = new Intent(Intent.ACTION_VIEW).setDataAndType(
                    FileProvider.getUriForFile(activity, activity.getPackageName() + ".provider", apk), "application/vnd.android.package-archive")
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            activity.startActivity(intent);
        } catch (RuntimeException ignored) { message(fragment, R.string.DanygrammUpdateError); }
    }

    public static void verifyApk(Context context, File apk, Update update, long minimumVersion) throws Exception {
        if (apk.length() != update.size || !update.sha256.equals(sha256(apk))) throw new SecurityException();
        int flags = Build.VERSION.SDK_INT >= 28 ? PackageManager.GET_SIGNING_CERTIFICATES : PackageManager.GET_SIGNATURES;
        PackageInfo info = context.getPackageManager().getPackageArchiveInfo(apk.getPath(), flags);
        if (info == null || !PACKAGE.equals(info.packageName) || info.applicationInfo == null
                || (info.applicationInfo.flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0) throw new SecurityException();
        long version = Build.VERSION.SDK_INT >= 28 ? info.getLongVersionCode() : info.versionCode;
        if (version != update.version || version <= minimumVersion) throw new SecurityException();
        Signature[] signatures = Build.VERSION.SDK_INT >= 28 && info.signingInfo != null ? info.signingInfo.getApkContentsSigners() : info.signatures;
        if (signatures == null || signatures.length != 1 || !CERTIFICATE.equals(hex(MessageDigest.getInstance("SHA-256").digest(signatures[0].toByteArray())))) throw new SecurityException();
    }

    private static String sha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = new FileInputStream(file)) {
            byte[] buffer = new byte[65536]; int count;
            while ((count = input.read(buffer)) != -1) digest.update(buffer, 0, count);
        }
        return hex(digest.digest());
    }
    private static String hex(byte[] data) {
        StringBuilder value = new StringBuilder(data.length * 2);
        for (byte b : data) value.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        return value.toString();
    }
    private static String readText(String url, int limit, Transfer transfer) throws Exception {
        HttpURLConnection connection = connect(url, transfer);
        try (InputStream input = connection.getInputStream(); ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192]; int count;
            while ((count = input.read(buffer)) != -1) {
                transfer.check();
                if (output.size() + count > limit) throw new SecurityException();
                output.write(buffer, 0, count);
            }
            return new String(output.toByteArray(), StandardCharsets.UTF_8);
        } finally { connection.disconnect(); }
    }

    public static void validateDownloadUrl(URL url) {
        String host = url.getHost();
        if (!url.getProtocol().equals("https") || url.getUserInfo() != null || url.getRef() != null || (url.getPort() != -1 && url.getPort() != 443)
                || !(host.equals("api.github.com") || host.equals("github.com") || host.equals("release-assets.githubusercontent.com") || host.equals("objects.githubusercontent.com"))) throw new SecurityException();
    }

    private static HttpURLConnection connect(String address, Transfer transfer) throws Exception {
        URL url = new URL(address);
        for (int redirects = 0; redirects < 6; redirects++) {
            transfer.check();
            validateDownloadUrl(url);
            HttpURLConnection connection = (HttpURLConnection) url.openConnection();
            transfer.connection = connection;
            try {
                transfer.check();
                connection.setInstanceFollowRedirects(false);
                connection.setConnectTimeout(transfer.timeout(10000));
                connection.setReadTimeout(transfer.timeout(30000));
                connection.setRequestProperty("User-Agent", "Danygramm-Updater");
                int status = connection.getResponseCode();
                if (status == 200) return connection;
                String location = connection.getHeaderField("Location");
                if (status == 404) throw new java.io.FileNotFoundException();
                if ((status == 301 || status == 302 || status == 303 || status == 307 || status == 308) && location != null) url = new URL(url, location);
                else throw new IOException();
            } catch (Exception failure) {
                connection.disconnect();
                throw failure;
            }
            connection.disconnect();
        }
        throw new SecurityException();
    }

    private static void message(BaseFragment fragment, int resource) {
        if (fragment.getParentActivity() != null) fragment.showDialog(new AlertDialog.Builder(fragment.getParentActivity())
                .setTitle("Danygramm").setMessage(text(resource)).setPositiveButton(text(R.string.OK), null).create());
    }
}
