package org.miccontrol.test;

import static org.junit.Assert.*;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.drawable.Drawable;
import androidx.core.content.ContextCompat;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.telegram.messenger.R;
import java.io.File;
import java.io.FileOutputStream;

@RunWith(AndroidJUnit4.class)
public class DanygrammBrandingTest {
    @Test public void actualLauncherAndNotificationDrawablesRenderConsistently() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        Bitmap preview = Bitmap.createBitmap(640, 176, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(preview); canvas.drawColor(0xff25303a);
        int official = context.getResources().getIdentifier("ic_launcher_sa", "mipmap", context.getPackageName());
        Drawable[] icons = {context.getDrawable(official), context.getPackageManager().getApplicationIcon(context.getPackageName()),
                ContextCompat.getDrawable(context, R.drawable.miccontrol_launcher), ContextCompat.getDrawable(context, R.drawable.danygramm_notification)};
        String[] names = {"Upstream", "Danygramm", "Legacy", "Status (mono)"};
        Paint text = new Paint(Paint.ANTI_ALIAS_FLAG); text.setColor(Color.WHITE); text.setTextSize(17);
        for (int i = 0; i < icons.length; i++) {
            assertNotNull(icons[i]);
            icons[i].setBounds(i * 160 + 16, 8, i * 160 + 144, 136); icons[i].draw(canvas);
            canvas.drawText(names[i], i * 160 + 16, 164, text);
        }
        int red = 0;
        for (int y = 8; y < 136; y++) for (int x = 176; x < 304; x++) {
            int color = preview.getPixel(x, y);
            if (Color.red(color) > 150 && Color.green(color) < 110 && Color.blue(color) < 110) red++;
        }
        assertTrue("red wing stars missing", red > 15);
        assertTrue("red dominates the paper plane", red < 1500);
        File directory = new File(context.getExternalFilesDir(null), "qa-branding");
        assertTrue(directory.isDirectory() || directory.mkdirs());
        try (FileOutputStream output = new FileOutputStream(new File(directory, "actual-icons.png"))) {
            assertTrue(preview.compress(Bitmap.CompressFormat.PNG, 100, output));
        } finally { preview.recycle(); }
    }
}
