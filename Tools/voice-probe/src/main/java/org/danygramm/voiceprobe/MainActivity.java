package org.danygramm.voiceprobe;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.util.Locale;

public final class MainActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private Button start, cancel, copy;
    private TextView status, elapsed, summary, json;
    private ProgressBar progress;
    private ProbeRun.Token ownedRun;
    private long generation = -1;
    private boolean resumed;
    private boolean pausedCancellation;
    private String lastJson;
    private final Runnable poll = new Runnable() {
        @Override public void run() {
            if (!resumed) return;
            render();
            handler.postDelayed(this, 250);
        }
    };

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(Color.rgb(245, 248, 251));
        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        column.setPadding(dp(20), dp(20), dp(20), dp(24));
        scroll.addView(column);
        scroll.setOnApplyWindowInsetsListener((v, insets) -> {
            column.setPadding(dp(20) + insets.getSystemWindowInsetLeft(), dp(20) + insets.getSystemWindowInsetTop(),
                    dp(20) + insets.getSystemWindowInsetRight(), dp(24) + insets.getSystemWindowInsetBottom());
            return insets;
        });
        TextView heading = text(column, getString(R.string.heading), 25);
        heading.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        if (android.os.Build.VERSION.SDK_INT >= 28) heading.setAccessibilityHeading(true);
        text(column, getString(R.string.explanation), 17);
        TextView note = text(column, getString(R.string.quality_note), 15);
        note.setTextColor(Color.rgb(67, 79, 92));
        start = button(column, R.string.start);
        cancel = button(column, R.string.cancel);
        copy = button(column, R.string.copy);
        status = text(column, getString(R.string.ready), 20);
        status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(ProbeRun.BLOCKS);
        column.addView(progress, new LinearLayout.LayoutParams(-1, dp(12)));
        elapsed = text(column, "", 16);
        summary = text(column, "", 18);
        json = text(column, "", 13);
        json.setTypeface(Typeface.MONOSPACE);
        json.setTextIsSelectable(true);
        setContentView(scroll);
        start.setOnClickListener(v -> {
            ProbeRun.Token token = ProbeRun.start(getApplicationContext());
            if (token == null) return;
            ownedRun = token;
            generation = token.id;
            pausedCancellation = false;
            lastJson = null;
            json.setText("");
            summary.setText("");
            getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            render();
        });
        cancel.setOnClickListener(v -> {
            ProbeRun.Token token = ProbeRun.current();
            if (token != null && !token.done) token.cancelled.set(true);
            render();
        });
        copy.setOnClickListener(v -> copyResult());
        render();
    }

    @Override protected void onResume() {
        super.onResume();
        resumed = true;
        handler.post(poll);
    }

    @Override protected void onPause() {
        resumed = false;
        handler.removeCallbacks(poll);
        if (ownedRun != null && !ownedRun.done) {
            ownedRun.cancelled.set(true);
            ownedRun = null;
            generation = -1; // No late result from a paused generation may replace this screen.
            pausedCancellation = true;
            status.setText(R.string.paused_cancelled);
        }
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        super.onPause();
    }

    private void render() {
        ProbeRun.Token current = ProbeRun.current();
        boolean busy = current != null && !current.done;
        start.setEnabled(!busy);
        cancel.setEnabled(busy);
        copy.setEnabled(lastJson != null);
        progress.setVisibility(busy ? View.VISIBLE : View.GONE);
        if (ownedRun == null || ownedRun != current || generation != ownedRun.id) {
            if (busy) status.setText(R.string.previous_stopping);
            else if (lastJson == null) status.setText(pausedCancellation ? R.string.paused_cancelled : R.string.ready);
            return;
        }
        if (ownedRun.done) {
            getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            if (lastJson == null && ownedRun.result != null) showResult(ownedRun.result);
            return;
        }
        elapsed.setText(String.format(Locale.getDefault(), "Прошло %.1f с",
                (SystemClock.elapsedRealtime() - ownedRun.startedAt) / 1000.0));
        progress.setIndeterminate(ownedRun.phase < 3);
        progress.setProgress(ownedRun.completedBlocks);
        if (ownedRun.isCancelled()) status.setText(R.string.cancel_requested);
        else if (ownedRun.phase == 0) status.setText(R.string.phase_assets);
        else if (ownedRun.phase == 1) status.setText(R.string.phase_load);
        else if (ownedRun.phase == 2) status.setText(R.string.phase_enroll);
        else if (ownedRun.phase == 3) status.setText("Обрабатываем блок " + ownedRun.completedBlocks + " из 100…");
        else status.setText(R.string.phase_flush);
    }

    private void showResult(String result) {
        lastJson = result;
        json.setText(result);
        copy.setEnabled(true);
        try {
            JSONObject object = new JSONObject(result);
            if ("cancelled".equals(object.optString("status"))) { status.setText(R.string.cancelled); return; }
            if (!"ok".equals(object.optString("status"))) { status.setText(R.string.error); return; }
            status.setText("Тест завершён");
            summary.setText(String.format(Locale.getDefault(),
                    "4 с записи обработаны за %.2f с\nRTF: %.3f\np50: %.1f мс · p95: %.1f мс\nПиковая память процесса: %.0f МБ\n\nRTF меньше 1 означает обработку быстрее длительности записи.",
                    object.getDouble("run_total_ms") / 1000.0, object.getDouble("rtf"),
                    object.getDouble("p50_ms"), object.getDouble("p95_ms"),
                    object.getDouble("process_peak_rss_kib") / 1024.0));
        } catch (Exception error) { status.setText(R.string.error); }
    }

    private void copyResult() {
        if (lastJson == null) return;
        try {
            ClipboardManager manager = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
            manager.setPrimaryClip(ClipData.newPlainText("Danygramm voice speed test", lastJson));
            ClipData actual = manager.getPrimaryClip();
            boolean confirmed = actual != null && actual.getItemCount() > 0
                    && lastJson.contentEquals(actual.getItemAt(0).coerceToText(this));
            Toast.makeText(this, confirmed ? R.string.copy_ok : R.string.copy_failed, Toast.LENGTH_SHORT).show();
        } catch (RuntimeException error) { Toast.makeText(this, R.string.copy_failed, Toast.LENGTH_SHORT).show(); }
    }

    private TextView text(LinearLayout parent, String value, int size) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextColor(Color.rgb(22, 37, 51));
        view.setTextSize(size);
        view.setPadding(0, dp(8), 0, dp(8));
        parent.addView(view, new LinearLayout.LayoutParams(-1, -2));
        return view;
    }
    private Button button(LinearLayout parent, int resource) {
        Button button = new Button(this);
        button.setText(resource);
        button.setAllCaps(false);
        button.setMinHeight(dp(52));
        parent.addView(button, new LinearLayout.LayoutParams(-1, -2));
        return button;
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
}
