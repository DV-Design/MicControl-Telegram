/*
 * This is the source code of Telegram for Android v. 1.3.x.
 * It is licensed under GNU GPL v. 2 or later.
 * You should have received a copy of the license in this archive (see LICENSE).
 *
 * Copyright Nikolai Kudashov, 2013-2018.
 */

package org.telegram.messenger;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import androidx.core.app.NotificationCompat;
import org.telegram.tgnet.ConnectionsManager;
import org.telegram.ui.LaunchActivity;

/** Maintains background delivery without an external push project. */
public class NotificationsService extends Service implements NotificationCenter.NotificationCenterDelegate {
    public static volatile boolean running;
    private static final String CHANNEL = "danygramm_background";
    private static final int ID = 3071;

    public static boolean hasAccount() {
        for (int i = 0; i < UserConfig.MAX_ACCOUNT_COUNT; i++) {
            if (UserConfig.getInstance(i).isClientActivated()) return true;
        }
        return false;
    }

    public static boolean isEnabled() {
        return MessagesController.getGlobalNotificationsSettings().getBoolean("pushService", true);
    }

    /** Called by a visible settings action. A rejected start must not leave the toggle enabled. */
    public static boolean setEnabled(Context context, boolean enabled) {
        if (enabled && !hasAccount()) return false;
        saveEnabled(enabled);
        boolean accepted = reconcile(context);
        if (enabled && !accepted) {
            saveEnabled(false);
            return false;
        }
        return true;
    }

    private static void saveEnabled(boolean enabled) {
        MessagesController.getGlobalNotificationsSettings().edit().putBoolean("pushService", enabled)
                .putBoolean("pushConnection", enabled).apply();
        for (int i = 0; i < UserConfig.MAX_ACCOUNT_COUNT; i++) {
            if (UserConfig.getInstance(i).isClientActivated()) {
                ConnectionsManager.getInstance(i).setPushConnectionEnabled(enabled);
            }
        }
    }

    public static boolean reconcile(Context context) {
        Intent intent = new Intent(context, NotificationsService.class);
        if (!isEnabled() || !hasAccount()) {
            context.stopService(intent);
            return false;
        }
        if (running) return true;
        try {
            if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(intent);
            else context.startService(intent);
            return true;
        } catch (RuntimeException ignored) {
            // Background starts may be disallowed. A visible resume can retry the saved preference.
            return false;
        }
    }

    @Override public void onCreate() {
        super.onCreate();
        try {
            NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            if (Build.VERSION.SDK_INT >= 26) {
                NotificationChannel channel = new NotificationChannel(CHANNEL,
                        getString(R.string.DanygrammBackground), NotificationManager.IMPORTANCE_LOW);
                channel.setShowBadge(false);
                channel.setSound(null, null);
                manager.createNotificationChannel(channel);
            }
            PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, LaunchActivity.class),
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            android.app.Notification notification = new NotificationCompat.Builder(this, CHANNEL)
                    .setSmallIcon(R.drawable.danygramm_notification).setContentTitle("Danygramm")
                    .setLargeIcon(brandIcon(this))
                    .setContentText(getString(R.string.DanygrammBackgroundRunning))
                    .setContentIntent(open).setCategory(NotificationCompat.CATEGORY_SERVICE)
                    .setOngoing(true).setOnlyAlertOnce(true).setSilent(true).build();
            if (Build.VERSION.SDK_INT >= 34) startForeground(ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
            else startForeground(ID, notification);
            running = true;
        } catch (RuntimeException denied) {
            // startForeground can fail asynchronously after startForegroundService returned.
            saveEnabled(false);
            stopSelf();
            return;
        }
        ApplicationLoader.postInitApplication();
        for (int i = 0; i < UserConfig.MAX_ACCOUNT_COUNT; i++) {
            NotificationCenter.getInstance(i).addObserver(this, NotificationCenter.appDidLogout);
        }
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (!running || !isEnabled() || !hasAccount()) {
            stopSelf();
            return START_NOT_STICKY;
        }
        for (int i = 0; i < UserConfig.MAX_ACCOUNT_COUNT; i++) {
            if (UserConfig.getInstance(i).isClientActivated()) ConnectionsManager.getInstance(i).setPushConnectionEnabled(true);
        }
        return START_STICKY;
    }

    @Override public void didReceivedNotification(int id, int account, Object... args) {
        if (id == NotificationCenter.appDidLogout && !hasAccount()) stopSelf();
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    public static android.graphics.Bitmap brandIcon(Context context) {
        android.graphics.drawable.Drawable icon = androidx.core.content.ContextCompat.getDrawable(context, R.drawable.miccontrol_launcher);
        android.graphics.Bitmap bitmap = android.graphics.Bitmap.createBitmap(128, 128, android.graphics.Bitmap.Config.ARGB_8888);
        icon.setBounds(0, 0, 128, 128);
        icon.draw(new android.graphics.Canvas(bitmap));
        return bitmap;
    }

    @Override public void onDestroy() {
        running = false;
        for (int i = 0; i < UserConfig.MAX_ACCOUNT_COUNT; i++) {
            NotificationCenter.getInstance(i).removeObserver(this, NotificationCenter.appDidLogout);
        }
        super.onDestroy();
    }
}
