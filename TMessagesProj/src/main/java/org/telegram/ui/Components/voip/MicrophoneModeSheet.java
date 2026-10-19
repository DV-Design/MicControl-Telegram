package org.telegram.ui.Components.voip;

import static org.telegram.messenger.AndroidUtilities.dp;

import android.content.Context;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;

import androidx.core.view.ViewCompat;

import org.telegram.messenger.AndroidUtilities;
import org.telegram.messenger.LocaleController;
import org.telegram.messenger.R;
import org.telegram.ui.ActionBar.BottomSheet;
import org.telegram.ui.ActionBar.Theme;
import org.telegram.ui.Cells.RadioColorCell;
import org.telegram.ui.Components.LayoutHelper;

/** The call screen uses a dark surface regardless of the app's current theme. */
public class MicrophoneModeSheet extends BottomSheet {
    private static final int BACKGROUND = 0xff20242b;
    private static final int SELECTED_BACKGROUND = 0xff2d414f;
    private static final int PRESSED_BACKGROUND = 0xff3c4d5b;
    private static final int TEXT = 0xfff5f7fa;
    private static final int SECONDARY_TEXT = 0xffb7c0cc;
    private static final int RADIO = 0xffadb8c6;
    private static final int ACCENT = 0xff7dc4ff;

    private static final Theme.ResourcesProvider DARK_RESOURCES = new Theme.ResourcesProvider() {
        @Override
        public int getColor(int key) {
            if (key == Theme.key_dialogBackground || key == Theme.key_windowBackgroundWhite
                    || key == Theme.key_windowBackgroundGray) {
                return BACKGROUND;
            } else if (key == Theme.key_dialogTextBlack) {
                return TEXT;
            } else if (key == Theme.key_windowBackgroundWhiteGrayText) {
                return SECONDARY_TEXT;
            } else if (key == Theme.key_dialogRadioBackground) {
                return RADIO;
            } else if (key == Theme.key_dialogRadioBackgroundChecked) {
                return ACCENT;
            }
            return Theme.getColor(key);
        }

        @Override
        public boolean isDark() {
            return true;
        }
    };

    public interface OnModeSelectedListener {
        void onModeSelected(int mode);
    }

    private final RadioColorCell[] modeCells = new RadioColorCell[3];

    public static int modeName(int mode) {
        return mode == 2 ? R.string.MicControlVoiceIsolation : mode == 0 ? R.string.DanygrammNoEffects : R.string.DanygrammNoiseSuppression;
    }

    public MicrophoneModeSheet(Context context, int microphoneMode, OnModeSelectedListener listener) {
        super(context, false, DARK_RESOURCES);
        setBackgroundColor(BACKGROUND);
        fixNavigationBar(BACKGROUND);
        setUseLightStatusBar(false);

        LinearLayout content = new LinearLayout(context);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setBackgroundColor(BACKGROUND);
        content.setPadding(0, dp(12), 0, dp(12));

        TextView title = new TextView(context);
        title.setText(LocaleController.getString(R.string.MicControlMicrophone));
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        title.setTypeface(AndroidUtilities.bold());
        title.setTextColor(TEXT);
        title.setGravity(LocaleController.isRTL ? Gravity.RIGHT : Gravity.LEFT);
        ViewCompat.setAccessibilityHeading(title, true);
        content.addView(title, LayoutHelper.createLinear(LayoutHelper.MATCH_PARENT, LayoutHelper.WRAP_CONTENT,
                24, 0, 24, 16));

        for (int i = 0; i < modeCells.length; i++) {
            final int mode = 2 - i;
            final String name = LocaleController.getString(modeName(mode));
            final String description = LocaleController.getString(mode == 2 ? R.string.DanygrammIsolationInfo
                    : mode == 1 ? R.string.DanygrammNoiseSuppressionInfo : R.string.DanygrammNoEffectsInfo);
            RadioColorCell cell = modeCells[i] = new RadioColorCell(context, DARK_RESOURCES);
            cell.setCheckColor(RADIO, ACCENT);
            cell.setTextAndText2AndValue(name, description, mode == microphoneMode);
            cell.setContentDescription(name + ". " + description);
            cell.setFocusable(true);
            for (int child = 0; child < cell.getChildCount(); child++) {
                cell.getChildAt(child).setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
            }
            content.addView(cell, LayoutHelper.createLinear(LayoutHelper.MATCH_PARENT, LayoutHelper.WRAP_CONTENT,
                    12, 0, 12, 4));
            cell.setOnClickListener(v -> {
                updateSelection(mode);
                if (listener != null) {
                    listener.onModeSelected(mode);
                }
                dismiss();
            });
        }
        updateSelection(microphoneMode);

        TextView hint = new TextView(context);
        hint.setText(LocaleController.getString(R.string.DanygrammModesInfo));
        hint.setTextSize(TypedValue.COMPLEX_UNIT_SP, 14);
        hint.setTextColor(SECONDARY_TEXT);
        hint.setGravity(LocaleController.isRTL ? Gravity.RIGHT : Gravity.LEFT);
        content.addView(hint, LayoutHelper.createLinear(LayoutHelper.MATCH_PARENT, LayoutHelper.WRAP_CONTENT,
                24, 12, 24, 0));
        setCustomView(content);
    }

    private void updateSelection(int mode) {
        for (int i = 0; i < modeCells.length; i++) {
            boolean selected = 2 - i == mode;
            modeCells[i].setChecked(selected, false);
            modeCells[i].setBackground(Theme.createSimpleSelectorRoundRectDrawable(dp(12),
                    selected ? SELECTED_BACKGROUND : BACKGROUND, PRESSED_BACKGROUND));
        }
    }
}
