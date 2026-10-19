package org.miccontrol.test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertSame;
import static org.junit.Assert.assertTrue;

import android.app.UiAutomation;
import android.content.Context;
import android.content.DialogInterface;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Rect;
import android.os.SystemClock;
import android.util.Log;
import android.view.InputDevice;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.TextView;

import androidx.core.graphics.ColorUtils;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.Before;
import org.junit.BeforeClass;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.telegram.messenger.AndroidUtilities;
import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.MessagesController;
import org.telegram.messenger.SharedConfig;
import org.telegram.ui.ActionBar.Theme;
import org.telegram.ui.Cells.RadioColorCell;
import org.telegram.ui.Components.voip.MicrophoneModeSheet;

import java.io.File;
import java.io.FileOutputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BooleanSupplier;

/** Real native sheet coverage; does not start a call or submit authentication requests. */
@RunWith(AndroidJUnit4.class)
public class MicControlMicrophoneModeSheetTest {
    private static final String TAG = "MicControlSheetTest";
    private static final String MODE_KEY = "miccontrolVoiceIsolation";

    @BeforeClass
    public static void initializeApplication() {
        TestActivitySession.onMain("application initialization", ApplicationLoader::postInitApplication);
    }

    @Before
    public void requireDedicatedEmulator() {
        MicControlRuntimeTest.assumeNoActivatedAccount();
    }

    @Test
    public void lightThemeStandardIsReadableAndCanSelectIsolation() throws Exception {
        exerciseSheet("Blue", false);
    }

    @Test
    public void lightThemeIsolationIsReadableAndCanSelectStandard() throws Exception {
        exerciseSheet("Blue", true);
    }

    @Test
    public void darkThemeStandardIsReadableAndCanSelectIsolation() throws Exception {
        exerciseSheet("Dark Blue", false);
    }

    @Test
    public void darkThemeIsolationIsReadableAndCanSelectStandard() throws Exception {
        exerciseSheet("Dark Blue", true);
    }

    private static void exerciseSheet(String themeName, boolean initialIsolation) throws Exception {
        String label = (themeName.equals("Blue") ? "light" : "dark")
                + (initialIsolation ? "-isolation" : "-standard");
        AtomicReference<MicrophoneModeSheet> sheet = new AtomicReference<>();
        AtomicReference<Boolean> selectedMode = new AtomicReference<>();
        AtomicInteger callbacks = new AtomicInteger();
        AtomicInteger dismissals = new AtomicInteger();
        CountDownLatch selected = new CountDownLatch(1);
        CountDownLatch dismissed = new CountDownLatch(1);
        ThemeSnapshot original = new ThemeSnapshot();
        TestActivitySession.onMain("capture global appearance", original::capture);
        try (TestActivitySession session = TestActivitySession.launch()) {
            try {
                session.onActivity(activity -> {
                    Theme.selectedAutoNightType = Theme.AUTO_NIGHT_TYPE_NONE;
                    Theme.ThemeInfo theme = Theme.getTheme(themeName);
                    assertNotNull("built-in theme missing: " + themeName, theme);
                    Theme.applyTheme(theme, false, false);
                    assertEquals("requested global theme must actually be applied",
                            !themeName.equals("Blue"), Theme.isCurrentThemeDark());
                    MicrophoneModeSheet dialog = new MicrophoneModeSheet(activity,
                            initialIsolation, enabled -> {
                                selectedMode.set(enabled);
                                callbacks.incrementAndGet();
                                selected.countDown();
                            });
                    sheet.set(dialog);
                    dialog.setOnDismissListener((DialogInterface.OnDismissListener) ignored -> {
                        dismissals.incrementAndGet();
                        dismissed.countDown();
                    });
                    dialog.show();
                });
                MicrophoneModeSheet dialog = sheet.get();
                awaitOnMain("sheet opening animation", () -> dialog.isShowing()
                        && dialog.getSheetAnimationType() == 0
                        && dialog.getContainerView().getTranslationY() == 0f
                        && dialog.getContainerView().getWidth() > 0
                        && dialog.getWindow().getDecorView().hasWindowFocus());
                TestActivitySession.onMain("initial radio semantics", () ->
                        assertSelection(findViews(dialog.getContainerView(), RadioColorCell.class),
                                initialIsolation));

                UiAutomation automation = InstrumentationRegistry.getInstrumentation().getUiAutomation();
                Bitmap screenshot = automation.takeScreenshot();
                assertNotNull("native screenshot unavailable", screenshot);
                double[] minimumContrast = {Double.POSITIVE_INFINITY};
                try {
                    saveScreenshot(screenshot, label);
                    TestActivitySession.onMain("rendered text contrast", () ->
                            minimumContrast[0] = assertRenderedTextContrast(dialog, screenshot));
                } finally {
                    screenshot.recycle();
                }

                int[] target = new int[2];
                TestActivitySession.onMain("tap target", () -> {
                    List<RadioColorCell> rows = findViews(dialog.getContainerView(), RadioColorCell.class);
                    RadioColorCell row = rows.get(initialIsolation ? 0 : 1);
                    Rect bounds = visibleBounds(row);
                    target[0] = bounds.centerX();
                    target[1] = bounds.centerY();
                    assertEquals("opening alone must not change mode", 0, callbacks.get());
                });
                tap(automation, target[0], target[1]);
                assertTrue("real touch did not select a mode", selected.await(15, TimeUnit.SECONDS));
                assertTrue("dialog did not dismiss after selection", dismissed.await(15, TimeUnit.SECONDS));
                TestActivitySession.onMain("selection and dismissal", () -> {
                    assertEquals("selection callback count", 1, callbacks.get());
                    assertEquals("selected mode callback", !initialIsolation, selectedMode.get());
                    // Android omits View accessibility metadata once the window is detached.
                    // Attached radio semantics were checked before tapping; retain state here.
                    assertCheckedState(findViews(dialog.getContainerView(), RadioColorCell.class),
                            !initialIsolation);
                    assertEquals("dismiss callback count", 1, dismissals.get());
                    assertFalse("dialog window remains showing", dialog.isShowing());
                    assertFalse("dialog window remains attached",
                            dialog.getWindow().getDecorView().isAttachedToWindow());
                    original.assertModeUnchanged();
                });
                Log.i(TAG, String.format(Locale.ROOT,
                        "%s textCount=6 minContrast=%.2f touchCallback=true checkedState=true dismissed=true",
                        label, minimumContrast[0]));
            } finally {
                boolean[] needsDismissal = {false};
                TestActivitySession.onMain("sheet cleanup", () -> {
                    MicrophoneModeSheet remaining = sheet.get();
                    if (remaining != null && remaining.isShowing()) {
                        needsDismissal[0] = true;
                        remaining.dismiss();
                    }
                });
                if (needsDismissal[0]) {
                    assertTrue("cleanup did not dismiss dialog", dismissed.await(15, TimeUnit.SECONDS));
                }
            }
        } finally {
            TestActivitySession.onMain("restore global appearance", original::restore);
        }
    }

    private static void assertSelection(List<RadioColorCell> rows, boolean isolation) {
        assertCheckedState(rows, isolation);
        for (int i = 0; i < rows.size(); i++) {
            RadioColorCell row = rows.get(i);
            boolean expected = (i == 1) == isolation;
            assertTrue("choice must be clickable and focusable", row.isClickable() && row.isFocusable());
            assertTrue("touch target height below 48dp", row.getHeight() >= AndroidUtilities.dp(48));
            assertTrue("touch target width below 48dp", row.getWidth() >= AndroidUtilities.dp(48));
            AccessibilityNodeInfo node = row.createAccessibilityNodeInfo();
            try {
                assertTrue("radio must expose checkable semantics", node.isCheckable());
                assertEquals("accessible selection " + i, expected, node.isChecked());
                assertEquals("android.widget.RadioButton", node.getClassName().toString());
                assertNotNull("accessible choice description missing", node.getContentDescription());
                for (TextView text : findViews(row, TextView.class)) {
                    assertTrue("accessible description omits visible label",
                            node.getContentDescription().toString().contains(text.getText()));
                    assertEquals("child text duplicates accessible radio label",
                            View.IMPORTANT_FOR_ACCESSIBILITY_NO, text.getImportantForAccessibility());
                }
            } finally {
                node.recycle();
            }
        }
    }

    private static void assertCheckedState(List<RadioColorCell> rows, boolean isolation) {
        assertEquals("two microphone choices", 2, rows.size());
        for (int i = 0; i < rows.size(); i++) {
            assertEquals("radio selection " + i, (i == 1) == isolation, rows.get(i).isChecked());
        }
    }

    private static double assertRenderedTextContrast(MicrophoneModeSheet dialog, Bitmap screenshot) {
        List<TextView> texts = findViews(dialog.getContainerView(), TextView.class);
        assertEquals("title, two labels, two descriptions and hint", 6, texts.size());
        double minimum = Double.POSITIVE_INFINITY;
        for (TextView text : texts) {
            assertTrue("empty displayed label", text.getText().length() > 0);
            Rect bounds = visibleBounds(text);
            assertEquals("text clipped horizontally", text.getWidth(), bounds.width());
            assertEquals("text clipped vertically", text.getHeight(), bounds.height());
            // Sample the actual composited surface beside this text, beyond its right padding.
            // Every parent has an opaque surface and a clear trailing margin in both layouts.
            Rect surface = visibleBounds((View) text.getParent());
            int x = surface.right - AndroidUtilities.dp(3);
            int y = bounds.centerY();
            assertTrue("background sample outside screenshot",
                    x >= 0 && y >= 0 && x < screenshot.getWidth() && y < screenshot.getHeight());
            int background = screenshot.getPixel(x, y);
            assertEquals("sheet surface must be opaque", 255, Color.alpha(background));
            double contrast = ColorUtils.calculateContrast(text.getCurrentTextColor(), background);
            assertTrue("rendered text contrast below 4.5 for " + text.getText() + ": " + contrast,
                    contrast >= 4.5);
            minimum = Math.min(minimum, contrast);
        }
        return minimum;
    }

    private static Rect visibleBounds(View view) {
        Rect bounds = new Rect();
        assertTrue("view is not actually visible: " + view.getClass().getSimpleName(),
                view.isShown() && view.getGlobalVisibleRect(bounds));
        assertEquals("view clipped horizontally", view.getWidth(), bounds.width());
        assertEquals("view clipped vertically", view.getHeight(), bounds.height());
        int[] location = new int[2];
        view.getLocationOnScreen(location);
        return new Rect(location[0], location[1], location[0] + view.getWidth(),
                location[1] + view.getHeight());
    }

    private static <T extends View> List<T> findViews(View root, Class<T> type) {
        List<T> result = new ArrayList<>();
        if (type.isInstance(root)) {
            result.add(type.cast(root));
        }
        if (root instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) root;
            for (int i = 0; i < group.getChildCount(); i++) {
                result.addAll(findViews(group.getChildAt(i), type));
            }
        }
        return result;
    }

    private static void awaitOnMain(String label, BooleanSupplier condition) {
        long deadline = SystemClock.uptimeMillis() + 15000;
        boolean[] satisfied = {false};
        do {
            TestActivitySession.onMain(label, () -> satisfied[0] = condition.getAsBoolean());
            if (satisfied[0]) return;
            SystemClock.sleep(16);
        } while (SystemClock.uptimeMillis() < deadline);
        throw new AssertionError(label + " did not complete within 15s");
    }

    private static void tap(UiAutomation automation, int x, int y) {
        long downTime = SystemClock.uptimeMillis();
        MotionEvent down = MotionEvent.obtain(downTime, downTime, MotionEvent.ACTION_DOWN, x, y, 0);
        MotionEvent up = MotionEvent.obtain(downTime, downTime + 30, MotionEvent.ACTION_UP, x, y, 0);
        try {
            down.setSource(InputDevice.SOURCE_TOUCHSCREEN);
            up.setSource(InputDevice.SOURCE_TOUCHSCREEN);
            assertTrue("touch down injection failed", automation.injectInputEvent(down, true));
            assertTrue("touch up injection failed", automation.injectInputEvent(up, true));
        } finally {
            down.recycle();
            up.recycle();
        }
    }

    private static void saveScreenshot(Bitmap screenshot, String label) throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File directory = new File(context.getExternalFilesDir(null), "qa-microphone-mode");
        assertTrue("could not create screenshot directory", directory.isDirectory() || directory.mkdirs());
        File file = new File(directory, label + ".png");
        try (FileOutputStream stream = new FileOutputStream(file)) {
            assertTrue("could not encode screenshot", screenshot.compress(Bitmap.CompressFormat.PNG, 100, stream));
        }
        Log.i(TAG, "screenshot=" + file.getAbsolutePath());
    }

    private static final class ThemeSnapshot {
        private Theme.ThemeInfo day;
        private Theme.ThemeInfo active;
        private boolean night;
        private int autoNight;
        private boolean mode;
        private Object persistedMode;
        private Object persistedTheme;

        void capture() {
            day = Theme.getCurrentTheme();
            active = Theme.getActiveTheme();
            night = Theme.isCurrentThemeNight();
            autoNight = Theme.selectedAutoNightType;
            mode = SharedConfig.voiceIsolationEnabled;
            SharedPreferences preferences = MessagesController.getGlobalMainSettings();
            persistedMode = preferences.getAll().get(MODE_KEY);
            persistedTheme = preferences.getAll().get("theme");
        }

        void assertModeUnchanged() {
            assertEquals("component test changed global microphone mode", mode, SharedConfig.voiceIsolationEnabled);
            assertEquals("component test persisted a microphone change", persistedMode,
                    MessagesController.getGlobalMainSettings().getAll().get(MODE_KEY));
        }

        void restore() {
            Theme.applyTheme(day, false, false);
            if (active != day) Theme.applyTheme(active, false, night);
            Theme.selectedAutoNightType = autoNight;
            assertSame("active theme was not restored", active, Theme.getActiveTheme());
            assertSame("day theme was not restored", day, Theme.getCurrentTheme());
            assertEquals("component test persisted a theme change", persistedTheme,
                    MessagesController.getGlobalMainSettings().getAll().get("theme"));
            assertModeUnchanged();
        }
    }
}
