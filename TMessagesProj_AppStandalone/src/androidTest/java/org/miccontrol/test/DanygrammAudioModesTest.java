package org.miccontrol.test;

import static org.junit.Assert.*;
import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.BeforeClass;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.BuildVars;
import org.telegram.messenger.MessagesController;
import org.telegram.messenger.SharedConfig;
import org.telegram.messenger.voip.NativeInstance;

@RunWith(AndroidJUnit4.class)
public class DanygrammAudioModesTest {
    @BeforeClass public static void initialize() {
        TestActivitySession.onMain("initialize", ApplicationLoader::postInitApplication);
    }
    @Test public void finalReleaseHasNoDebugOrInheritedLogging() {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        assertEquals(0, context.getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE);
        assertFalse(BuildVars.DEBUG_VERSION);
        assertFalse(BuildVars.LOGS_ENABLED);
    }
    @Test public void oldPreferencesMigrateAndInvalidValuesAreSafe() {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        SharedPreferences preferences = context.getSharedPreferences("qa_audio_migration", Context.MODE_PRIVATE);
        preferences.edit().clear().commit();
        try {
            assertEquals(1, SharedConfig.readMicrophoneMode(preferences));
            preferences.edit().putBoolean("miccontrolVoiceIsolation", true).commit();
            assertEquals(2, SharedConfig.readMicrophoneMode(preferences));
            preferences.edit().putBoolean("miccontrolVoiceIsolation", false).commit();
            assertEquals(1, SharedConfig.readMicrophoneMode(preferences));
            for (int mode = 0; mode < 3; mode++) {
                preferences.edit().putInt("danygrammMicrophoneMode", mode).commit();
                assertEquals(mode, SharedConfig.readMicrophoneMode(preferences));
            }
            preferences.edit().putInt("danygrammMicrophoneMode", -10).commit();
            assertEquals(1, SharedConfig.readMicrophoneMode(preferences));
        } finally { preferences.edit().clear().commit(); }
    }
    @Test public void actualNativePipelineSuppressesNoiseAndHasAnExactBypass() {
        double[] values = NativeInstance.testMicrophoneModes();
        assertEquals(7, values.length);
        for (double value : values) assertTrue("non-finite audio metric", Double.isFinite(value));
        assertTrue("no-effects energy missing", values[0] > 0);
        assertTrue("WebRTC suppression did not reduce noise", values[1] > 0 && values[1] < values[0]);
        assertTrue("isolation not stronger than NS", values[2] >= 0 && values[2] < values[1]);
        assertEquals(0, values[3], 0);
        assertEquals(1, values[4], 0);
        assertEquals(1, values[5], 0);
        assertTrue("no-effects changed PCM", values[6] < 0.000001);
        Log.i("DanygrammAudio", "NS/none=" + values[1] / values[0] + " isolation/NS=" + values[2] / values[1] + " bypassError=" + values[6]);
    }
    @Test public void allThreeModesPersistAndReachJni() {
        SharedPreferences preferences = MessagesController.getGlobalMainSettings();
        Object legacy = preferences.getAll().get("miccontrolVoiceIsolation");
        Object saved = preferences.getAll().get("danygrammMicrophoneMode");
        int original = SharedConfig.microphoneMode;
        try {
            for (int i = 0; i < 30; i++) {
                int mode = i % 3;
                SharedConfig.setMicrophoneMode(mode); NativeInstance.setMicrophoneMode(mode);
                assertEquals(mode, SharedConfig.readMicrophoneMode(preferences));
                assertEquals(mode == 2, SharedConfig.voiceIsolationEnabled);
            }
        } finally {
            SharedConfig.setMicrophoneMode(original); NativeInstance.setMicrophoneMode(original);
            SharedPreferences.Editor editor = preferences.edit();
            if (legacy == null) editor.remove("miccontrolVoiceIsolation"); else editor.putBoolean("miccontrolVoiceIsolation", (Boolean) legacy);
            if (saved == null) editor.remove("danygrammMicrophoneMode"); else editor.putInt("danygrammMicrophoneMode", (Integer) saved);
            assertTrue(editor.commit());
        }
    }
}
