package org.miccontrol.test;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assume.assumeFalse;

import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ProviderInfo;
import android.content.pm.ServiceInfo;
import android.content.res.XmlResourceParser;
import android.view.View;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.BeforeClass;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.ApplicationLoaderImpl;
import org.telegram.messenger.MessagesController;
import org.telegram.messenger.SharedConfig;
import org.telegram.messenger.UserConfig;
import org.telegram.messenger.voip.NativeInstance;
import org.telegram.tgnet.ConnectionsManager;
import org.telegram.tgnet.NativeByteBuffer;
import org.telegram.tgnet.TLRPC;
import org.telegram.ui.IntroActivity;
import org.telegram.ui.LaunchActivity;
import org.telegram.ui.LoginActivity;
import org.xmlpull.v1.XmlPullParser;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

/** Runs inside the standalone candidate, using its real native libraries and resources. */
@RunWith(AndroidJUnit4.class)
public class MicControlRuntimeTest {
    private static final String PACKAGE = "org.miccontrol.messenger.web";
    private static final String ANDROID_NS = "http://schemas.android.com/apk/res/android";
    private static final String VOICE_ISOLATION_KEY = "miccontrolVoiceIsolation";

    @BeforeClass
    public static void initializeApplication() {
        TestActivitySession.onMain("application initialization", ApplicationLoader::postInitApplication);
    }

    @Test
    public void installedManifestKeepsMicControlSeparateFromTelegram() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        assertEquals(PACKAGE, context.getPackageName());
        PackageManager manager = context.getPackageManager();
        ApplicationInfo application = manager.getApplicationInfo(PACKAGE, 0);
        assertEquals("MicControl", manager.getApplicationLabel(application).toString());
        assertEquals(ApplicationLoaderImpl.class.getName(), application.className);

        PackageInfo info = manager.getPackageInfo(PACKAGE, PackageManager.GET_PROVIDERS);
        assertNotNull("content providers missing", info.providers);
        boolean fileProviderFound = false;
        for (ProviderInfo provider : info.providers) {
            assertNotNull("provider authority missing", provider.authority);
            for (String authority : provider.authority.split(";")) {
                assertTrue("foreign provider authority: " + authority,
                        authority.startsWith(PACKAGE + "."));
                fileProviderFound |= authority.equals(PACKAGE + ".provider");
            }
        }
        assertTrue("file sharing provider missing", fileProviderFound);

        ServiceInfo authenticator = manager.getServiceInfo(new ComponentName(context,
                "org.telegram.messenger.AuthenticatorService"), PackageManager.GET_META_DATA);
        try (XmlResourceParser xml = authenticator.loadXmlMetaData(manager,
                "android.accounts.AccountAuthenticator")) {
            assertNotNull("authenticator metadata missing", xml);
            int event;
            do {
                event = xml.next();
            } while (event != XmlPullParser.START_TAG && event != XmlPullParser.END_DOCUMENT);
            assertEquals("account-authenticator", xml.getName());
            assertEquals("org.miccontrol.messenger", xml.getAttributeValue(ANDROID_NS,
                    "accountType"));
        }
    }

    @Test
    public void unauthenticatedLandingSurvivesBackgroundAndRecreation() {
        assumeNoActivatedAccount();
        try (TestActivitySession session = TestActivitySession.launch()) {
            session.onActivity(MicControlRuntimeTest::assertLandingVisible);
            session.backgroundAndResume();
            session.onActivity(MicControlRuntimeTest::assertLandingVisible);
            session.recreate();
            session.onActivity(MicControlRuntimeTest::assertLandingVisible);
        }
    }

    @Test
    public void nativeBuffersRoundTripUnicodeAndBinaryLengthBoundaries() throws Exception {
        NativeByteBuffer buffer = new NativeByteBuffer(64 * 1024);
        try {
            assertNotNull("JNI returned no buffer", buffer.buffer);
            assertTrue("JNI buffer must be direct", buffer.buffer.isDirect());
            String text = "Привет, Telegram! العربية 😀\u0000";
            for (int size : new int[]{0, 1, 253, 254, 255, 16387}) {
                byte[] binary = new byte[size];
                for (int i = 0; i < binary.length; i++) {
                    binary[i] = (byte) (i * 31 + 17);
                }
                buffer.rewind();
                buffer.writeInt32(0x1234abcd);
                buffer.writeInt64(0x123456789abcdefL);
                buffer.writeBool(true);
                buffer.writeBool(false);
                buffer.writeString(text);
                buffer.writeByteArray(binary);
                int encodedLength = buffer.position();
                assertEquals("TL alignment for payload " + size, 0, encodedLength % 4);
                buffer.rewind();
                assertEquals(0x1234abcd, buffer.readInt32(true));
                assertEquals(0x123456789abcdefL, buffer.readInt64(true));
                assertTrue(buffer.readBool(true));
                assertFalse(buffer.readBool(true));
                assertEquals(text, buffer.readString(true));
                assertArrayEquals("payload length " + size, binary, buffer.readByteArray(true));
                assertEquals("consumed TL length", encodedLength, buffer.position());
            }
        } finally {
            buffer.reuse();
        }
    }

    @Test
    public void telegramPeerSchemaPreserves64BitIdentifiersInNativeBuffer() throws Exception {
        TLRPC.TL_peerUser peer = new TLRPC.TL_peerUser();
        peer.user_id = 0x123456789abcdefL;
        NativeByteBuffer buffer = new NativeByteBuffer(peer.getObjectSize());
        try {
            peer.serializeToStream(buffer);
            assertEquals("constructor plus int64", 12, buffer.position());
            buffer.rewind();
            TLRPC.Peer decoded = TLRPC.Peer.TLdeserialize(buffer, buffer.readInt32(true), true);
            assertTrue(decoded instanceof TLRPC.TL_peerUser);
            assertEquals(peer.user_id, decoded.user_id);
            assertEquals(buffer.limit(), buffer.position());
        } finally {
            buffer.reuse();
        }
    }

    @Test
    public void nativeTlsClientHelloHasConsistentRecordAndServerName() {
        String domain = "miccontrol.example";
        byte[] hello = ConnectionsManager.nativeTestGenerateClientHello(domain);
        assertNotNull(hello);
        assertTrue("truncated ClientHello", hello.length >= 76);
        assertEquals("handshake record", 0x16, hello[0] & 0xff);
        assertEquals("TLS record major", 3, hello[1] & 0xff);
        assertEquals("TLS record minor", 1, hello[2] & 0xff);
        assertEquals("record length", hello.length - 5, u16(hello, 3));
        assertEquals("ClientHello type", 1, hello[5] & 0xff);
        int handshakeLength = (hello[6] & 0xff) << 16 | (hello[7] & 0xff) << 8
                | (hello[8] & 0xff);
        assertEquals("handshake length", hello.length - 9, handshakeLength);
        assertEquals("legacy session id length", 32, hello[43] & 0xff);
        assertTrue("requested server name absent", contains(hello,
                domain.getBytes(StandardCharsets.US_ASCII)));
    }

    @Test
    public void nativeVoipImplementationsLoadFromCandidateApk() {
        String[] versions = NativeInstance.getAllVersions();
        assertNotNull("VoIP versions missing", versions);
        assertTrue("no VoIP implementation registered", versions.length > 0);
        for (String version : versions) {
            assertNotNull(version);
            assertFalse("empty VoIP version: " + Arrays.toString(versions), version.trim().isEmpty());
        }
    }

    @Test
    public void voiceIsolationSettingPersistsAndJniSetterAcceptsRepeatedChanges() {
        SharedPreferences preferences = MessagesController.getGlobalMainSettings();
        boolean hadPreference = preferences.contains(VOICE_ISOLATION_KEY);
        boolean originalPreference = preferences.getBoolean(VOICE_ISOLATION_KEY, false);
        boolean originalMode = SharedConfig.voiceIsolationEnabled;
        try {
            for (int i = 0; i < 50; i++) {
                boolean enabled = (i & 1) == 0;
                SharedConfig.setVoiceIsolationEnabled(enabled);
                NativeInstance.setVoiceIsolationEnabled(enabled);
                assertEquals(enabled, SharedConfig.voiceIsolationEnabled);
                assertEquals(enabled, preferences.getBoolean(VOICE_ISOLATION_KEY, !enabled));
            }
        } finally {
            SharedConfig.setVoiceIsolationEnabled(originalMode);
            NativeInstance.setVoiceIsolationEnabled(originalMode);
            SharedPreferences.Editor editor = preferences.edit();
            if (hadPreference) {
                editor.putBoolean(VOICE_ISOLATION_KEY, originalPreference);
            } else {
                editor.remove(VOICE_ISOLATION_KEY);
            }
            assertTrue("restore preference to disk", editor.commit());
        }
    }

    static void assumeNoActivatedAccount() {
        for (int account = 0; account < UserConfig.MAX_ACCOUNT_COUNT; account++) {
            assumeFalse("use a dedicated emulator without signed-in accounts",
                    UserConfig.getInstance(account).isClientActivated());
        }
    }

    private static void assertLandingVisible(LaunchActivity activity) {
        assertFalse(activity.isFinishing());
        View content = activity.findViewById(android.R.id.content);
        assertNotNull("activity content missing", content);
        assertTrue("activity content detached", content.isAttachedToWindow());
        assertTrue("activity content hidden", content.isShown());
        assertNotNull("navigation layout missing", activity.getActionBarLayout());
        Object fragment = activity.getActionBarLayout().getLastFragment();
        assertTrue("expected intro or saved login, got " + fragment,
                fragment instanceof IntroActivity || fragment instanceof LoginActivity);
    }

    private static int u16(byte[] data, int offset) {
        return (data[offset] & 0xff) << 8 | (data[offset + 1] & 0xff);
    }

    private static boolean contains(byte[] data, byte[] needle) {
        for (int i = 0; i <= data.length - needle.length; i++) {
            int j = 0;
            while (j < needle.length && data[i + j] == needle[j]) {
                j++;
            }
            if (j == needle.length) {
                return true;
            }
        }
        return false;
    }
}
