package org.telegram.ui;

import android.app.NotificationManager;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.PowerManager;
import android.provider.Settings;
import androidx.core.app.NotificationManagerCompat;
import org.telegram.messenger.DanygrammUpdater;
import org.telegram.messenger.LocaleController;
import org.telegram.messenger.NotificationsService;
import org.telegram.messenger.R;
import org.telegram.ui.ActionBar.AlertDialog;
import org.telegram.ui.ActionBar.BaseFragment;

public final class DanygrammSettings {
    private static String text(int id) { return LocaleController.getString(id); }
    public static void show(BaseFragment fragment) {
        android.app.Activity activity = fragment.getParentActivity();
        if (activity == null) return;
        String packageName = activity.getPackageName();
        boolean notifications = NotificationManagerCompat.from(activity).areNotificationsEnabled();
        boolean battery = ((PowerManager) activity.getSystemService(android.content.Context.POWER_SERVICE)).isIgnoringBatteryOptimizations(packageName);
        boolean fullScreen = Build.VERSION.SDK_INT < 34 || ((NotificationManager) activity.getSystemService(android.content.Context.NOTIFICATION_SERVICE)).canUseFullScreenIntent();
        String on = text(R.string.DanygrammOn), off = text(R.string.DanygrammOff);
        boolean active = NotificationsService.isEnabled() && NotificationsService.running;
        String background = active ? on : off;
        if (NotificationsService.isEnabled() && !active) background = text(R.string.DanygrammBackgroundStopped);
        if (!NotificationsService.hasAccount()) background = text(R.string.DanygrammBackgroundNeedsAccount);
        CharSequence[] items = {
                text(R.string.DanygrammBackground) + ": " + background,
                text(R.string.DanygrammSystemNotifications) + ": " + (notifications ? on : off),
                text(R.string.DanygrammIncomingCalls) + ": " + (fullScreen ? on : off),
                text(R.string.DanygrammBattery) + ": " + (battery ? on : off),
                text(R.string.DanygrammCheckUpdates)
        };
        AlertDialog.Builder builder = new AlertDialog.Builder(activity);
        builder.setTitle("Danygramm");
        builder.setMessage(text(R.string.DanygrammBackgroundInfo));
        builder.setItems(items, (dialog, which) -> {
            try {
                if (which == 0) {
                    boolean enabled = !active;
                    if (!NotificationsService.setEnabled(activity, enabled)) {
                        showBackgroundError(fragment);
                        return;
                    }
                    org.telegram.messenger.AndroidUtilities.runOnUIThread(() -> {
                        if (enabled && !NotificationsService.running) showBackgroundError(fragment);
                        else show(fragment);
                    }, 300);
                    return;
                } else if (which == 4) {
                    DanygrammUpdater.check(fragment, true);
                    return;
                }
                Intent intent;
                if (which == 1 && Build.VERSION.SDK_INT >= 26) intent = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, packageName);
                else if (which == 2 && Build.VERSION.SDK_INT >= 34) intent = new Intent(Settings.ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT, Uri.parse("package:" + packageName));
                else if (which == 3) intent = new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS);
                else intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + packageName));
                activity.startActivity(intent);
            } catch (RuntimeException ignored) {
                try {
                    activity.startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + packageName)));
                } catch (RuntimeException unavailable) {
                    fragment.showDialog(new AlertDialog.Builder(activity).setTitle("Danygramm")
                            .setMessage(text(R.string.DanygrammSettingsUnavailable))
                            .setPositiveButton(text(R.string.OK), null).create());
                }
            }
        });
        builder.setNegativeButton(text(R.string.Close), null);
        fragment.showDialog(builder.create());
    }

    private static void showBackgroundError(BaseFragment fragment) {
        if (fragment.getParentActivity() == null) return;
        fragment.showDialog(new AlertDialog.Builder(fragment.getParentActivity()).setTitle("Danygramm")
                .setMessage(text(NotificationsService.hasAccount() ? R.string.DanygrammBackgroundStartError : R.string.DanygrammBackgroundNeedsAccount))
                .setPositiveButton(text(R.string.OK), null).create());
    }
}
