package org.miccontrol.test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import android.content.Context;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.BeforeClass;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.R;
import org.telegram.utils.localization.Localization;

import java.lang.reflect.Field;

/** Verifies the actual binary dictionaries and resource-ID bindings used by LocaleController. */
@RunWith(AndroidJUnit4.class)
public class DanygrammLocalizationTest {
    private static final int[] EXPECTED_IDS = {
            R.string.DanygrammNoiseSuppression, R.string.DanygrammNoEffects,
            R.string.DanygrammSettingsInfo, R.string.DanygrammBackground,
            R.string.DanygrammTranslateTitle, R.string.DanygrammTranslateEnable
    };

    @BeforeClass public static void initialize() {
        TestActivitySession.onMain("localization initialization", ApplicationLoader::postInitApplication);
    }

    @Test public void englishFeatureStringsResolveFromInstalledBinaryAssets() {
        assertLocalization("localization_en.bin", new String[] {
                "Noise suppression", "No effects", "Background delivery and app updates",
                "Background notifications", "On-screen translation", "Translate incoming messages"
        });
    }

    @Test public void russianFeatureStringsResolveFromInstalledBinaryAssets() {
        assertLocalization("localization_ru.bin", new String[] {
                "Шумоподавление", "Без эффектов", "Работа в фоне и обновления приложения",
                "Фоновые уведомления", "Перевод на экране", "Переводить входящие сообщения"
        });
    }

    private static void assertLocalization(String asset, String[] expected) {
        TestActivitySession.onMain("installed localization " + asset, () -> {
            Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
            Localization localization = new Localization.Builder().addResLocalization(context, asset).build();
            // Do not merge English as a fallback: the Russian asset must contain
            // every new key itself, and both assets must agree with the ID map.
            int checked = 0;
            for (Field field : R.string.class.getFields()) {
                if (!field.getName().startsWith("Danygramm") || field.getType() != int.class) continue;
                try {
                    int resourceId = field.getInt(null);
                    String byName = localization.getByResName(field.getName());
                    String byId = localization.getByResId(context, resourceId);
                    assertNotNull(asset + " missing " + field.getName(), byName);
                    assertNotNull("resource binding missing " + field.getName(), byId);
                    assertEquals("name/ID lookup differ: " + field.getName(), byName, byId);
                    assertFalse("empty localized value: " + field.getName(), byId.isEmpty());
                    assertFalse("unresolved localized value: " + field.getName(), byId.contains("LOC_ERR"));
                    checked++;
                } catch (IllegalAccessException error) {
                    throw new AssertionError("cannot inspect string resource", error);
                }
            }
            assertTrue("Danygramm feature resources missing", checked >= EXPECTED_IDS.length);
            for (int i = 0; i < EXPECTED_IDS.length; i++) {
                // Independent literals catch empty/wrong-language dictionaries;
                // comparing two calls to a broken getString() would not.
                assertEquals(asset + " feature string " + i, expected[i],
                        localization.getByResId(context, EXPECTED_IDS[i]));
            }
        });
    }
}
