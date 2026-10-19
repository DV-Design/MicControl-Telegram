package org.miccontrol.test;

import static org.junit.Assert.*;
import static org.junit.Assume.assumeTrue;
import android.content.SharedPreferences;
import android.os.SystemClock;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.nl.translate.Translation;
import com.google.mlkit.nl.translate.Translator;
import com.google.mlkit.nl.translate.TranslatorOptions;
import com.google.mlkit.common.model.DownloadConditions;
import org.junit.BeforeClass;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.LocalChatTranslation;
import org.telegram.messenger.MessageObject;
import org.telegram.messenger.MessagesController;
import org.telegram.messenger.UserConfig;
import org.telegram.tgnet.TLRPC;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicBoolean;

@RunWith(AndroidJUnit4.class)
public class DanygrammTranslationTest {
    private static final long DIALOG = 900011;
    private static final String SOURCE = "Hello! The meeting is tomorrow at ten in the morning.";
    @BeforeClass public static void initialize() {
        TestActivitySession.onMain("initialize translation", ApplicationLoader::postInitApplication);
    }
    private static MessageObject incoming(String text) {
        TLRPC.TL_message message = new TLRPC.TL_message();
        message.id = 8001; message.dialog_id = DIALOG;
        message.peer_id = new TLRPC.TL_peerUser(); message.peer_id.user_id = DIALOG;
        message.from_id = new TLRPC.TL_peerUser(); message.from_id.user_id = DIALOG;
        message.message = text; message.date = 1700000000;
        return new MessageObject(UserConfig.selectedAccount, message, false, false);
    }
    @Test public void displayedTranslationKeepsOriginalTextAndEntities() {
        TestActivitySession.onMain("display translation", () -> {
            MessageObject message = incoming(SOURCE);
            TLRPC.TL_messageEntityBold bold = new TLRPC.TL_messageEntityBold(); bold.offset = 0; bold.length = 5;
            message.messageOwner.entities.add(bold);
            message.setLocalTranslation(SOURCE, "Привет! Встреча завтра утром.");
            assertTrue("visible cells require a content rebind", message.forceUpdate);
            assertTrue(message.hasLocalTranslation());
            assertEquals("Привет! Встреча завтра утром.", message.messageText.toString());
            assertEquals(SOURCE, message.messageOwner.message);
            assertSame(bold, message.messageOwner.entities.get(0));
            assertTrue(message.getEntities().isEmpty());
            message.forceUpdate = false;
            message.clearLocalTranslation();
            assertTrue("original restoration requires a content rebind", message.forceUpdate);
            assertEquals(SOURCE, message.messageText.toString());
            assertSame(bold, message.getEntities().get(0));
        });
    }
    @Test public void cachedSummarizationRemainsSeparateFromLocalDisplay() {
        TestActivitySession.onMain("summary and local display", () -> {
            String source = SOURCE + " " + SOURCE + " " + SOURCE;
            MessageObject message = incoming(source);
            message.messageOwner.summary_from_language = "en";
            message.messageOwner.summaryText = new TLRPC.TL_textWithEntities();
            message.messageOwner.summaryText.text = "An existing cached summary.";
            message.messageOwner.summarizedOpen = true;
            message.setLocalTranslation(source, "Локальный перевод исходного сообщения.");
            assertTrue(message.summarized);
            assertEquals("An existing cached summary.", message.messageText.toString());
            assertFalse(message.hasLocalTranslation());
            message.messageOwner.summarizedOpen = false;
            message.updateTranslation(true);
            assertTrue(message.hasLocalTranslation());
            assertEquals("Локальный перевод исходного сообщения.", message.messageText.toString());
            message.clearLocalTranslation();
            assertEquals(source, message.messageText.toString());
            assertEquals(source, message.messageOwner.message);
        });
    }
    @Test public void localOriginalAndPauseDoNotChangePremiumTranslationPreferences() {
        MicControlRuntimeTest.assumeNoActivatedAccount();
        SharedPreferences preferences = MessagesController.getMainSettings(UserConfig.selectedAccount);
        String key = "danygrammLocalTranslate_" + DIALOG;
        Object oldEnabled = preferences.getAll().get(key);
        Object oldServer = preferences.getAll().get("translating_dialog_languages2");
        Object oldHidden = preferences.getAll().get("hidden_translation_at");
        AtomicReference<LocalChatTranslation> session = new AtomicReference<>();
        try {
            assertTrue(preferences.edit().putBoolean(key, false).commit());
            TestActivitySession.onMain("scoped local mode", () -> {
                LocalChatTranslation local = new LocalChatTranslation(UserConfig.selectedAccount, DIALOG, () -> {});
                session.set(local);
                assertFalse(local.isSelectedInThisSession());
                local.setEnabled(true);
                assertTrue(local.isSelectedInThisSession());
                local.setEnabled(false);
                assertTrue("original mode must still suppress server translation in this chat", local.isSelectedInThisSession());
                local.setActive(false);
                assertTrue("pause must keep the local mode choice", local.isSelectedInThisSession());
                local.setActive(true);
                local.close();
                assertFalse(local.isSelectedInThisSession());
                assertEquals(oldServer, preferences.getAll().get("translating_dialog_languages2"));
                assertEquals(oldHidden, preferences.getAll().get("hidden_translation_at"));
            });
        } finally {
            TestActivitySession.onMain("close scoped mode", () -> { if (session.get() != null) session.get().close(); });
            restorePreference(preferences, key, oldEnabled);
        }
    }
    @Test public void targetChangeRejectsOldActualLanguageIdentificationCallbacks() throws Exception {
        MicControlRuntimeTest.assumeNoActivatedAccount();
        SharedPreferences preferences = MessagesController.getMainSettings(UserConfig.selectedAccount);
        String key = "danygrammLocalTranslate_" + DIALOG;
        Object oldEnabled = preferences.getAll().get(key), oldTarget = preferences.getAll().get(key + "_language");
        AtomicReference<LocalChatTranslation> session = new AtomicReference<>();
        AtomicReference<MessageObject> message = new AtomicReference<>();
        AtomicBoolean submittedCurrentTarget = new AtomicBoolean();
        CountDownLatch completed = new CountDownLatch(1);
        try {
            TestActivitySession.onMain("replace target before SDK callbacks", () -> {
                MessageObject incoming = incoming(SOURCE);
                message.set(incoming);
                LocalChatTranslation local = new LocalChatTranslation(UserConfig.selectedAccount, DIALOG, () -> {
                    LocalChatTranslation current = session.get();
                    if (submittedCurrentTarget.get() && current != null && "en".equals(current.targetLanguage())
                            && current.statusResource() == org.telegram.messenger.R.string.DanygrammTranslateReady) completed.countDown();
                });
                session.set(local);
                local.setTargetLanguage("ru"); local.setEnabled(true); local.check(incoming, true);
                // The real SDK listener runs on the main executor after this action returns.
                local.setTargetLanguage("en"); submittedCurrentTarget.set(true); local.check(incoming, true);
            });
            assertTrue("current target did not complete", completed.await(30, TimeUnit.SECONDS));
            TestActivitySession.onMain("old target must not replace current text", () -> {
                assertEquals("en", session.get().targetLanguage());
                assertFalse(message.get().hasLocalTranslation());
                assertEquals(SOURCE, message.get().messageText.toString());
                assertEquals(SOURCE, message.get().messageOwner.message);
            });
        } finally {
            TestActivitySession.onMain("close target race", () -> { if (session.get() != null) session.get().close(); });
            restorePreference(preferences, key, oldEnabled);
            restorePreference(preferences, key + "_language", oldTarget);
        }
    }
    @Test public void captionsTranslateAndRestoreWithoutUsingOldEntityOffsets() {
        TestActivitySession.onMain("caption translation", () -> {
            MessageObject message = incoming("A beautiful morning.");
            message.messageOwner.media = new TLRPC.TL_messageMediaPhoto();
            message.type = MessageObject.TYPE_PHOTO;
            message.setLocalTranslation("A beautiful morning.", "Прекрасное утро.");
            assertNotNull(message.caption);
            assertEquals("Прекрасное утро.", message.caption.toString());
            assertEquals("A beautiful morning.", message.messageOwner.message);
            message.clearLocalTranslation();
            assertEquals("A beautiful morning.", message.caption.toString());
        });
    }
    @Test public void outgoingMessagesAndEditedSourcesCannotReceiveStaleTranslations() {
        TestActivitySession.onMain("outgoing and edits", () -> {
            MessageObject outgoing = incoming(SOURCE); outgoing.messageOwner.out = true;
            assertFalse(LocalChatTranslation.eligible(outgoing));
            outgoing.setLocalTranslation(SOURCE, "Нельзя менять исходящее");
            assertFalse(outgoing.hasLocalTranslation());
            assertEquals(SOURCE, outgoing.messageOwner.message);
            MessageObject edited = incoming(SOURCE);
            edited.setLocalTranslation(SOURCE, "Привет");
            edited.messageOwner.message = "An edited message.";
            edited.updateTranslation(true);
            assertFalse(edited.hasLocalTranslation());
            assertEquals("An edited message.", edited.messageText.toString());
            edited.setLocalTranslation(SOURCE, "Late stale result");
            assertFalse(edited.hasLocalTranslation());
        });
    }
    @Test public void actualMlKitModelsTranslateKnownText() throws Exception {
        assumeTrue("Explicit online model download required", "true".equals(InstrumentationRegistry.getArguments().getString("danygrammTranslationModels")));
        Translator translator = Translation.getClient(new TranslatorOptions.Builder().setSourceLanguage("en").setTargetLanguage("ru").build());
        try {
            Tasks.await(translator.downloadModelIfNeeded(new DownloadConditions.Builder().requireWifi().build()), 180, TimeUnit.SECONDS);
            String result = Tasks.await(translator.translate(SOURCE), 30, TimeUnit.SECONDS);
            assertRussian(result);
        } finally { translator.close(); }
    }
    @Test public void chatSessionTranslatesOfflineAndDisablingRestoresOriginal() throws Exception {
        assumeTrue("Explicit cached-model run required", "true".equals(InstrumentationRegistry.getArguments().getString("danygrammTranslationOffline")));
        MicControlRuntimeTest.assumeNoActivatedAccount();
        MessageObject message = incoming(SOURCE);
        AtomicReference<LocalChatTranslation> session = new AtomicReference<>();
        CountDownLatch complete = new CountDownLatch(1);
        SharedPreferences preferences = MessagesController.getMainSettings(UserConfig.selectedAccount);
        String key = "danygrammLocalTranslate_" + DIALOG;
        Object oldEnabled = preferences.getAll().get(key), oldTarget = preferences.getAll().get(key + "_language");
        try {
            TestActivitySession.onMain("start local chat translation", () -> {
                LocalChatTranslation local = new LocalChatTranslation(UserConfig.selectedAccount, DIALOG, () -> {
                    if (message.hasLocalTranslation()) complete.countDown();
                });
                session.set(local); local.setTargetLanguage("ru"); local.setEnabled(true); local.check(message, true);
            });
            assertTrue("cached model did not translate within 30s", complete.await(30, TimeUnit.SECONDS));
            TestActivitySession.onMain("check display and restore", () -> {
                assertRussian(message.messageText.toString());
                assertEquals(SOURCE, message.messageOwner.message);
                MessageObject duplicate = incoming(SOURCE);
                duplicate.messageOwner.id = 8002;
                session.get().check(duplicate, true);
                assertTrue("cached same-source message must update immediately", duplicate.hasLocalTranslation());
                assertTrue("cached translations must rebind visible cells", duplicate.forceUpdate);
                session.get().setEnabled(false);
                assertFalse(message.hasLocalTranslation());
                assertEquals(SOURCE, message.messageText.toString());
                assertFalse(duplicate.hasLocalTranslation());
                assertEquals(SOURCE, duplicate.messageText.toString());
            });
        } finally {
            TestActivitySession.onMain("close local translation", () -> { if (session.get() != null) session.get().close(); });
            SharedPreferences.Editor editor = preferences.edit();
            if (oldEnabled == null) editor.remove(key); else editor.putBoolean(key, (Boolean) oldEnabled);
            if (oldTarget == null) editor.remove(key + "_language"); else editor.putString(key + "_language", (String) oldTarget);
            assertTrue(editor.commit());
        }
    }
    private static void restorePreference(SharedPreferences preferences, String key, Object value) {
        SharedPreferences.Editor editor = preferences.edit();
        if (value == null) editor.remove(key);
        else if (value instanceof Boolean) editor.putBoolean(key, (Boolean) value);
        else editor.putString(key, (String) value);
        assertTrue(editor.commit());
    }
    private static void assertRussian(String result) {
        assertNotEquals(SOURCE, result);
        assertTrue("translation lacks expected Russian words", result.toLowerCase(java.util.Locale.ROOT).contains("завтра")
                && result.toLowerCase(java.util.Locale.ROOT).contains("встреч"));
    }
}
