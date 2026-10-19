package org.miccontrol.test;

import static org.junit.Assert.*;
import static org.junit.Assume.assumeTrue;
import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import androidx.core.content.FileProvider;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.telegram.messenger.DanygrammUpdater;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.security.MessageDigest;

@RunWith(AndroidJUnit4.class)
public class DanygrammUpdateTest {
    private static final String BASE = "https://github.com/DV-Design/MicControl-Telegram/releases/download/danygramm-1.0/";
    private static JSONObject metadata(File apk, int version) throws Exception {
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        try (FileInputStream stream = new FileInputStream(apk)) {
            byte[] buffer = new byte[65536]; int count;
            while ((count = stream.read(buffer)) != -1) hash.update(buffer, 0, count);
        }
        StringBuilder hex = new StringBuilder(); for (byte b : hash.digest()) hex.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        return new JSONObject().put("package", DanygrammUpdater.PACKAGE).put("versionCode", version)
                .put("apk", "Danygramm-arm64.apk").put("size", apk.length()).put("sha256", hex.toString());
    }
    private static void rejected(Throwing task) throws Exception {
        try { task.run(); fail("untrusted update accepted"); } catch (SecurityException expected) { }
    }
    private interface Throwing { void run() throws Exception; }
    @Test public void releaseTagsAndRedirectsStayWithinTrustedHttpsEndpoints() throws Exception {
        JSONObject json = new JSONObject().put("package", DanygrammUpdater.PACKAGE).put("versionCode", 71799)
                .put("apk", "Danygramm-arm64.apk").put("size", 1)
                .put("sha256", "0000000000000000000000000000000000000000000000000000000000000000");
        String repository = "https://github.com/DV-Design/MicControl-Telegram/releases/download/";
        for (String tag : new String[]{"", ".", "..", "a/b", "%2e%2e"}) {
            rejected(() -> new DanygrammUpdater.Update(json, repository + tag + "/"));
        }
        for (String host : new String[]{"github.com", "api.github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}) {
            DanygrammUpdater.validateDownloadUrl(new java.net.URL("https://" + host + "/asset"));
        }
        for (String url : new String[]{"http://github.com/asset", "https://github.com.evil.test/asset", "https://user@github.com/asset", "https://github.com:444/asset", "https://github.com/asset#fragment"}) {
            rejected(() -> DanygrammUpdater.validateDownloadUrl(new java.net.URL(url)));
        }
        json.put("versionCode", (long) Integer.MAX_VALUE + 1);
        rejected(() -> new DanygrammUpdater.Update(json, BASE));
    }
    @Test public void actualSignedApkIsAcceptedButTamperAndDowngradeAreRejected() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        PackageInfo installed = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
        File apk = new File(context.getApplicationInfo().sourceDir);
        JSONObject json = metadata(apk, installed.versionCode);
        DanygrammUpdater.Update update = new DanygrammUpdater.Update(json, BASE);
        DanygrammUpdater.verifyApk(context, apk, update, installed.versionCode - 1L);
        rejected(() -> DanygrammUpdater.verifyApk(context, apk, update, installed.versionCode));
        json.put("sha256", "0000000000000000000000000000000000000000000000000000000000000000");
        DanygrammUpdater.Update tampered = new DanygrammUpdater.Update(json, BASE);
        rejected(() -> DanygrammUpdater.verifyApk(context, apk, tampered, installed.versionCode - 1L));
        json.put("package", "org.telegram.messenger");
        rejected(() -> new DanygrammUpdater.Update(json, BASE));
        json.put("package", DanygrammUpdater.PACKAGE).put("apk", "../untrusted.apk");
        rejected(() -> new DanygrammUpdater.Update(json, BASE));
        json.put("apk", "Danygramm-arm64.apk").put("size", 1024L * 1024 * 1024);
        rejected(() -> new DanygrammUpdater.Update(json, BASE));
        rejected(() -> new DanygrammUpdater.Update(json, "https://example.org/"));
    }
    @Test public void apkWithSamePackageButDifferentSigningKeyIsRejected() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File fixture = new File(context.getExternalFilesDir(null), "qa_wrong_signer.apk");
        assumeTrue("Explicit foreign-signer fixture required", fixture.isFile());
        PackageInfo archive = context.getPackageManager().getPackageArchiveInfo(fixture.getPath(), PackageManager.GET_SIGNING_CERTIFICATES);
        assertNotNull(archive); assertEquals(DanygrammUpdater.PACKAGE, archive.packageName);
        DanygrammUpdater.Update update = new DanygrammUpdater.Update(metadata(fixture, archive.versionCode), BASE);
        rejected(() -> DanygrammUpdater.verifyApk(context, fixture, update, archive.versionCode - 1L));
    }
    @Test public void verifiedUpdateCacheHasAWorkingPrivateFileProviderUri() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File directory = new File(context.getFilesDir(), "cache"); directory.mkdirs();
        File file = new File(directory, "qa-update-provider.apk");
        try {
            try (FileOutputStream stream = new FileOutputStream(file)) { stream.write(1); }
            android.net.Uri uri = FileProvider.getUriForFile(context, context.getPackageName() + ".provider", file);
            assertEquals("content", uri.getScheme());
            assertEquals(context.getPackageName() + ".provider", uri.getAuthority());
        } finally { file.delete(); }
    }
}
