package org.miccontrol.test;

import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assume.assumeTrue;

import android.util.Log;

import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.filters.LargeTest;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.telegram.tgnet.ConnectionsManager;
import org.telegram.tgnet.TLObject;
import org.telegram.tgnet.TLRPC;
import org.telegram.messenger.UserConfig;
import org.telegram.ui.LaunchActivity;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Explicitly enabled read-only MTProto probe; never signs in or sends messages. */
@LargeTest
@RunWith(AndroidJUnit4.class)
public class MicControlNetworkTest {
    @Test
    public void unauthenticatedMtprotoFetchesTelegramConfig() throws Exception {
        assumeTrue("enable with -e miccontrolNetwork true", Boolean.parseBoolean(
                InstrumentationRegistry.getArguments().getString("miccontrolNetwork", "false")));
        MicControlRuntimeTest.initializeApplication();
        MicControlRuntimeTest.assumeNoActivatedAccount();

        try (ActivityScenario<LaunchActivity> ignored = ActivityScenario.launch(LaunchActivity.class)) {
            ConnectionsManager manager = ConnectionsManager.getInstance(UserConfig.selectedAccount);
            CountDownLatch completed = new CountDownLatch(1);
            AtomicReference<TLObject> result = new AtomicReference<>();
            AtomicReference<TLRPC.TL_error> error = new AtomicReference<>();
            int token = manager.sendRequest(new TLRPC.TL_help_getConfig(), (response, failure) -> {
                result.set(response);
                error.set(failure);
                completed.countDown();
            }, ConnectionsManager.RequestFlagWithoutLogin
                    | ConnectionsManager.RequestFlagEnableUnauthorized
                    | ConnectionsManager.RequestFlagFailOnServerErrors);
            try {
                assertTrue("help.getConfig timed out after 45s; connection state="
                        + manager.getConnectionState(), completed.await(45, TimeUnit.SECONDS));
                TLRPC.TL_error failure = error.get();
                assertNull(failure == null ? "" : "help.getConfig error " + failure.code
                        + ": " + failure.text, failure);
                assertTrue("expected Telegram config, got " + result.get(),
                        result.get() instanceof TLRPC.TL_config);
                TLRPC.TL_config config = (TLRPC.TL_config) result.get();
                assertTrue("invalid server date", config.date > 0);
                assertTrue("invalid config expiry", config.expires > config.date);
                assertTrue("invalid datacenter", config.this_dc > 0);
                assertNotNull(config.dc_options);
                assertTrue("empty datacenter endpoints", !config.dc_options.isEmpty());
                for (TLRPC.TL_dcOption dc : config.dc_options) {
                    assertTrue("invalid endpoint datacenter", dc.id > 0);
                    assertTrue("invalid endpoint port", dc.port > 0 && dc.port <= 65535);
                    assertNotNull("missing endpoint address", dc.ip_address);
                    assertTrue("empty endpoint address", !dc.ip_address.isEmpty());
                }
                Log.i("MicControlTest", "MTProto help.getConfig: dc=" + config.this_dc
                        + ", test_mode=" + config.test_mode
                        + ", endpoints=" + config.dc_options.size());
            } finally {
                manager.cancelRequest(token, false);
            }
        }
    }
}
