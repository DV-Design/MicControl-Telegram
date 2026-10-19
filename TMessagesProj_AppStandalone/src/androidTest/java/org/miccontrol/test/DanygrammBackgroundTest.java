package org.miccontrol.test;

import static org.junit.Assert.*;
import android.app.NotificationManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.os.SystemClock;
import android.service.notification.StatusBarNotification;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.BeforeClass;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.MessagesController;
import org.telegram.messenger.NotificationsService;
import org.telegram.messenger.R;
import org.telegram.messenger.UserConfig;
import org.telegram.tgnet.TLRPC;
import java.lang.reflect.Field;
import java.util.Objects;

@RunWith(AndroidJUnit4.class)
public class DanygrammBackgroundTest {
    @BeforeClass public static void initialize() {
        TestActivitySession.onMain("background initialization", ApplicationLoader::postInitApplication);
    }
    @Test public void backgroundServiceIsPrivateAndUsesUntimedMessagingPurpose() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        ServiceInfo info = context.getPackageManager().getServiceInfo(new ComponentName(context, NotificationsService.class), PackageManager.GET_META_DATA);
        assertFalse(info.exported);
        assertEquals(ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE, info.getForegroundServiceType());
        assertEquals(PackageManager.PERMISSION_GRANTED, context.checkSelfPermission("android.permission.FOREGROUND_SERVICE_SPECIAL_USE"));
    }
    @Test public void foregroundConnectionSurvivesBackgroundAndStopsAfterAccountIsRemoved() throws Exception {
        MicControlRuntimeTest.assumeNoActivatedAccount();
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        UserConfig account = UserConfig.getInstance(UserConfig.selectedAccount);
        TLRPC.User original = account.getCurrentUser();
        long originalClientUserId = account.clientUserId;
        Object savedUser = account.getPreferences().getAll().get("user");
        Field currentUser = UserConfig.class.getDeclaredField("currentUser");
        currentUser.setAccessible(true);
        Field sync = UserConfig.class.getDeclaredField("sync");
        sync.setAccessible(true);
        Object accountLock = sync.get(account);
        SharedPreferences preferences = MessagesController.getGlobalNotificationsSettings();
        Object oldSetting = preferences.getAll().get("pushService");
        int microphone = context.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO);
        try (TestActivitySession session = TestActivitySession.launch()) {
            Throwable primaryFailure = null;
            try {
                session.onActivity(activity -> {
                    // In-memory identity only: no login, session, saveConfig or RPC.
                    TLRPC.TL_user fixture = new TLRPC.TL_user(); fixture.id = 900011; fixture.first_name = "Offline service fixture";
                    setInMemoryIdentity(account, currentUser, accountLock, fixture, fixture.id);
                    preferences.edit().putBoolean("pushService", true).commit();
                    NotificationsService.reconcile(activity);
                });
                awaitRunning(true);
                StatusBarNotification notification = awaitForegroundNotification(context);
                assertEquals(R.drawable.danygramm_notification, notification.getNotification().getSmallIcon().getResId());
                assertNotNull(notification.getNotification().getLargeIcon());
                assertTrue((notification.getNotification().flags & android.app.Notification.FLAG_FOREGROUND_SERVICE) != 0);
                session.backgroundAndResume();
                assertTrue("service stopped while app was backgrounded", NotificationsService.running);
                assertEquals("background delivery changed microphone permission", microphone, context.checkSelfPermission(android.Manifest.permission.RECORD_AUDIO));
                TestActivitySession.onMain("remove fixture identity", () -> {
                    setInMemoryIdentity(account, currentUser, accountLock, original, originalClientUserId);
                    NotificationsService.reconcile(context);
                });
                awaitRunning(false);
            } catch (Exception | Error failure) {
                primaryFailure = failure;
                throw failure;
            } finally {
                try {
                    TestActivitySession.onMain("restore account and stop service", () -> {
                        try {
                            setInMemoryIdentity(account, currentUser, accountLock, original, originalClientUserId);
                        } finally {
                            context.stopService(new Intent(context, NotificationsService.class));
                        }
                    });
                } catch (RuntimeException | Error cleanupFailure) {
                    if (primaryFailure == null) throw cleanupFailure;
                    primaryFailure.addSuppressed(cleanupFailure);
                }
            }
        } finally {
            // Restore the preference even if activity, reflection or service cleanup fails.
            SharedPreferences.Editor editor = preferences.edit();
            if (oldSetting == null) editor.remove("pushService"); else editor.putBoolean("pushService", (Boolean) oldSetting);
            editor.commit();
        }
        assertSame(original, account.getCurrentUser());
        assertEquals(originalClientUserId, account.clientUserId);
        assertTrue("in-memory fixture was persisted", Objects.equals(savedUser, account.getPreferences().getAll().get("user")));
        assertFalse(account.isClientActivated());
    }

    private static void setInMemoryIdentity(UserConfig account, Field currentUser, Object lock,
            TLRPC.User user, long clientUserId) {
        synchronized (lock) {
            try {
                // Avoid setCurrentUser: it rejects null and schedules premium/network work.
                currentUser.set(account, user);
                account.clientUserId = clientUserId;
            } catch (IllegalAccessException failure) {
                throw new AssertionError("could not restore in-memory fixture identity", failure);
            }
        }
    }
    private static void awaitRunning(boolean expected) throws Exception {
        long deadline = SystemClock.elapsedRealtime() + 10000;
        while (NotificationsService.running != expected && SystemClock.elapsedRealtime() < deadline) Thread.sleep(30);
        assertEquals("foreground service state", expected, NotificationsService.running);
    }

    private static StatusBarNotification awaitForegroundNotification(Context context) throws InterruptedException {
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        long deadline = SystemClock.elapsedRealtime() + 15000;
        do {
            for (StatusBarNotification notification : manager.getActiveNotifications()) {
                if (notification.getId() == 3071) return notification;
            }
            Thread.sleep(100);
        } while (SystemClock.elapsedRealtime() < deadline);
        throw new AssertionError("foreground connection notification 3071 missing after 15s; running="
                + NotificationsService.running + "; notificationsAllowed="
                + androidx.core.app.NotificationManagerCompat.from(context).areNotificationsEnabled());
    }
}
