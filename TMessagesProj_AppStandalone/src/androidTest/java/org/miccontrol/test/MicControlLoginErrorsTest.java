package org.miccontrol.test;

import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertSame;
import static org.junit.Assert.assertTrue;

import android.app.Dialog;

import androidx.test.ext.junit.runners.AndroidJUnit4;

import org.junit.Before;
import org.junit.BeforeClass;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.UserConfig;
import org.telegram.tgnet.TLObject;
import org.telegram.tgnet.TLRPC;
import org.telegram.ui.ActionBar.AlertDialog;
import org.telegram.ui.Components.AlertsCreator;
import org.telegram.ui.LoginActivity;

import java.util.function.Consumer;

/** Exercises the real error handler and dialog host without submitting a login request. */
@RunWith(AndroidJUnit4.class)
public class MicControlLoginErrorsTest {
    private static final String SYNTHETIC_PHONE = "+70000000000";

    @BeforeClass
    public static void initializeApplication() {
        TestActivitySession.onMain("application initialization", ApplicationLoader::postInitApplication);
    }

    @Before
    public void requireDedicatedEmulator() {
        MicControlRuntimeTest.assumeNoActivatedAccount();
    }

    @Test
    public void publishedApiFailureIsVisible() {
        assertErrorIsVisible(400, "API_ID_PUBLISHED_FLOOD", new TLRPC.TL_auth_sendCode());
    }

    @Test
    public void invalidApiFailureIsVisible() {
        assertErrorIsVisible(400, "API_ID_INVALID", new TLRPC.TL_auth_sendCode());
    }

    @Test
    public void requiredClientUpdateIsVisible() {
        assertErrorIsVisible(406, "UPDATE_APP_TO_LOGIN", new TLRPC.TL_auth_sendCode());
    }

    @Test
    public void authRestartFailureIsVisible() {
        assertErrorIsVisible(500, "AUTH_RESTART", new TLRPC.TL_auth_sendCode());
    }

    @Test
    public void unknownSendCodeFailureIsVisible() {
        assertErrorIsVisible(400, "MICCONTROL_SYNTHETIC_LOGIN_ERROR", new TLRPC.TL_auth_sendCode());
    }

    @Test
    public void existingResendHandlerShowsDialogOnTheSameHost() {
        assertErrorIsVisible(400, "MICCONTROL_SYNTHETIC_RESEND_ERROR", new TLRPC.TL_auth_resendCode());
    }

    @Test
    public void nonSendCode406RemainsSilent() {
        withAttachedLogin(login -> {
            TLRPC.TL_error error = new TLRPC.TL_error();
            error.code = 406;
            error.text = "MICCONTROL_SYNTHETIC_SILENT_406";
            Dialog dialog = AlertsCreator.processError(login.getCurrentAccount(), error, login,
                    new TLRPC.TL_auth_resendCode(), SYNTHETIC_PHONE);
            assertNull("406 for other requests must retain its existing handling", dialog);
            assertNull("unrelated 406 must not attach a dialog", login.getVisibleDialog());
        });
    }

    @Test
    public void cancelledSendCodeDoesNotShowAnError() {
        withAttachedLogin(login -> {
            TLRPC.TL_error error = new TLRPC.TL_error();
            error.code = -1000;
            error.text = "MICCONTROL_SYNTHETIC_CANCEL";
            Dialog dialog = AlertsCreator.processError(login.getCurrentAccount(), error, login,
                    new TLRPC.TL_auth_sendCode(), SYNTHETIC_PHONE);
            assertNull("cancelled requests must remain silent", dialog);
            assertNull("cancelled requests must not attach a dialog", login.getVisibleDialog());
        });
    }

    private static void assertErrorIsVisible(int errorCode, String errorText, TLObject request) {
        withAttachedLogin(login -> {
            TLRPC.TL_error error = new TLRPC.TL_error();
            error.code = errorCode;
            error.text = errorText;
            Dialog dialog = AlertsCreator.processError(login.getCurrentAccount(), error, login,
                    request, SYNTHETIC_PHONE);
            try {
                assertNotNull("auth error was silently ignored: " + errorText, dialog);
                assertTrue("auth error dialog is not showing: " + errorText, dialog.isShowing());
                assertSame("dialog must belong to the real LoginActivity", dialog,
                        login.getVisibleDialog());
                assertTrue("expected Telegram's real AlertDialog", dialog instanceof AlertDialog);
                AlertDialog alert = (AlertDialog) dialog;
                assertNotNull("error message view missing", alert.getMessageTextView());
                assertTrue("error text is absent from the displayed message: " + errorText,
                        alert.getMessageTextView().getText().toString().contains(errorText));
            } finally {
                if (dialog != null) {
                    dialog.dismiss();
                }
            }
        });
    }

    private static void withAttachedLogin(Consumer<LoginActivity> assertion) {
        try (TestActivitySession session = TestActivitySession.launch()) {
            session.onActivity(activity -> {
                LoginActivity login = new LoginActivity(UserConfig.selectedAccount);
                // Attach the real dialog owner without creating PhoneView, which loads countries.
                login.setParentLayout(activity.getActionBarLayout());
                assertSame("login must use the actual resumed activity", activity,
                        login.getParentActivity());
                try {
                    assertion.accept(login);
                } finally {
                    Dialog remainingDialog = login.getVisibleDialog();
                    if (remainingDialog != null) {
                        remainingDialog.dismiss();
                    }
                    login.setParentLayout(null);
                }
            });
        }
    }
}
