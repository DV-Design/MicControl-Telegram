package org.miccontrol.test;

import static org.junit.Assert.*;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.view.View;
import android.view.ViewGroup;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityNodeProvider;
import android.widget.FrameLayout;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.MessageObject;
import org.telegram.messenger.UserConfig;
import org.telegram.tgnet.TLRPC;
import org.telegram.ui.Cells.ChatMessageCell;
import org.telegram.ui.ActionBar.Theme;
import java.io.File;
import java.io.FileOutputStream;

/** Real cell rebind on the same incoming object, without an account or network RPC. */
@RunWith(AndroidJUnit4.class)
public class DanygrammTranslationUiTest {
    // Different line counts make a skipped rebind observable in the bubble's height,
    // even though the cell and its MessageObject retain exactly the same identity.
    private static final String SOURCE = "Hello!\nThe meeting\nis tomorrow\nmorning.";
    private static final String TRANSLATED = "Привет! Встреча завтра утром.";

    @Test public void actualCellRebindsTranslationAndOriginalOnTheSameMessage() {
        MicControlRuntimeTest.assumeNoActivatedAccount();
        TestActivitySession.onMain("translation cell initialization", ApplicationLoader::postInitApplication);
        try (TestActivitySession session = TestActivitySession.launch()) {
            session.onActivity(activity -> {
                // ChatActivity initializes full chat drawables before creating its cells.
                // The unauthenticated activity otherwise initializes only common resources.
                Theme.createChatResources(activity, false);
                assertNotNull("incoming bubble drawable was not initialized", Theme.chat_msgInDrawable);
                TLRPC.TL_message source = new TLRPC.TL_message();
                source.id = 8003; source.dialog_id = 900011; source.date = 1700000000;
                source.peer_id = new TLRPC.TL_peerUser(); source.peer_id.user_id = 900011;
                source.from_id = new TLRPC.TL_peerUser(); source.from_id.user_id = 900011;
                source.message = SOURCE;
                MessageObject message = new MessageObject(UserConfig.selectedAccount, source, false, false);
                FrameLayout host = new FrameLayout(activity);
                host.setBackgroundColor(0xffe6ebee);
                ViewGroup decor = (ViewGroup) activity.getWindow().getDecorView();
                decor.addView(host, new ViewGroup.LayoutParams(-1, -1));
                Bitmap original = null, translated = null, restored = null;
                try {
                    int width = activity.getResources().getDisplayMetrics().widthPixels;
                    int height = activity.getResources().getDisplayMetrics().heightPixels;
                    host.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                            View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY));
                    host.layout(0, 0, width, height);
                    ChatMessageCell cell = new ChatMessageCell(activity, UserConfig.selectedAccount, false, null, null);
                    host.addView(cell, new FrameLayout.LayoutParams(-1, -2));
                    assertTrue("cell must exercise the attached production binding path", cell.isAttachedToWindow());
                    File directory = new File(activity.getExternalFilesDir(null), "qa-translation-ui");
                    assertTrue(directory.isDirectory() || directory.mkdirs());
                    original = render(cell, message, width, SOURCE);
                    save(original, new File(directory, "original.png"));
                    message.setLocalTranslation(SOURCE, TRANSLATED);
                    translated = render(cell, message, width, TRANSLATED);
                    save(translated, new File(directory, "translated.png"));
                    assertNotEquals("rebind must update bubble height for the changed line count",
                            original.getHeight(), translated.getHeight());
                    assertFalse("translated cell still draws original pixels", original.sameAs(translated));
                    message.clearLocalTranslation();
                    restored = render(cell, message, width, SOURCE);
                    save(restored, new File(directory, "restored.png"));
                    assertEquals(original.getHeight(), restored.getHeight());
                    assertEquals(SOURCE, source.message);
                    assertFalse("restored cell still draws translated pixels", translated.sameAs(restored));
                } finally {
                    message.clearLocalTranslation();
                    decor.removeView(host);
                    if (original != null) original.recycle();
                    if (translated != null) translated.recycle();
                    if (restored != null) restored.recycle();
                }
            });
        }
    }

    private static Bitmap render(ChatMessageCell cell, MessageObject message, int width, String expected) {
        cell.setMessageObject(message, null, false, false, true);
        cell.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(0, View.MeasureSpec.UNSPECIFIED));
        cell.layout(0, 0, width, cell.getMeasuredHeight());
        assertSame(message, cell.getMessageObject());
        assertNotNull(message.textLayoutBlocks);
        StringBuilder layoutText = new StringBuilder();
        for (MessageObject.TextLayoutBlock block : message.textLayoutBlocks) layoutText.append(block.textLayout.getText());
        assertEquals("actual cell text layout", expected, layoutText.toString());
        AccessibilityNodeInfo node = cell.getAccessibilityNodeProvider()
                .createAccessibilityNodeInfo(AccessibilityNodeProvider.HOST_VIEW_ID);
        assertNotNull("cell accessibility node missing", node);
        try {
            CharSequence text = node.getText() != null ? node.getText() : node.getContentDescription();
            assertNotNull("cell accessibility text missing", text);
            assertTrue("cell accessibility retained stale message text", text.toString().contains(expected));
        } finally { node.recycle(); }
        assertTrue(cell.getMeasuredHeight() > 0);
        Bitmap bitmap = Bitmap.createBitmap(width, cell.getMeasuredHeight(), Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap); canvas.drawColor(0xffe6ebee); cell.draw(canvas);
        int textColor = Theme.chat_msgTextPaint.getColor();
        int ink = 0;
        for (int y = Math.max(0, cell.getTextY()); y < Math.min(bitmap.getHeight(), cell.getTextY() + message.textHeight()); y++) {
            for (int x = Math.max(0, cell.getTextX()); x < bitmap.getWidth(); x++) {
                if (bitmap.getPixel(x, y) == textColor) ink++;
            }
        }
        assertTrue("native bubble did not draw message glyphs", ink > 20);
        return bitmap;
    }

    private static void save(Bitmap bitmap, File file) {
        try (FileOutputStream output = new FileOutputStream(file)) {
            assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, output));
        } catch (java.io.IOException error) { throw new AssertionError("cell screenshot", error); }
    }
}
