package org.telegram.ui.Components;

import com.google.android.gms.tasks.Task;
import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.common.model.RemoteModelManager;
import com.google.mlkit.nl.translate.TranslateLanguage;
import com.google.mlkit.nl.translate.TranslateRemoteModel;
import org.telegram.messenger.LocalChatTranslation;
import org.telegram.messenger.LocaleController;
import org.telegram.messenger.R;
import org.telegram.ui.ActionBar.AlertDialog;
import org.telegram.ui.ActionBar.BaseFragment;
import java.util.ArrayList;
import java.util.Locale;

public final class LocalTranslationOptions {
    public static String languageName(String language) {
        return Locale.forLanguageTag(language).getDisplayName(LocaleController.getInstance().getCurrentLocale());
    }
    private static String text(int id) { return LocaleController.getString(id); }
    public static void show(BaseFragment fragment, LocalChatTranslation translation) {
        if (fragment.getParentActivity() == null) return;
        CharSequence[] items = {
                text(translation.isEnabled() ? R.string.DanygrammTranslateOriginal : R.string.DanygrammTranslateEnable),
                text(R.string.DanygrammTranslateLanguage) + ": " + languageName(translation.targetLanguage()),
                text(translation.allowsMobileDownload() ? R.string.DanygrammTranslateAnyNetwork : R.string.DanygrammTranslateWifi),
                text(R.string.DanygrammTranslateRetry), text(R.string.DanygrammTranslateDeleteModels)
        };
        fragment.showDialog(new AlertDialog.Builder(fragment.getParentActivity(), fragment.getResourceProvider())
                .setTitle(text(R.string.DanygrammTranslateTitle))
                .setMessage(text(R.string.DanygrammTranslateInfo) + "\n\n" + text(translation.statusResource()))
                .setItems(items, (dialog, which) -> {
                    if (which == 0) translation.setEnabled(!translation.isEnabled());
                    else if (which == 1) languages(fragment, translation);
                    else if (which == 2) {
                        if (translation.allowsMobileDownload()) translation.setMobileDownload(false);
                        else fragment.showDialog(new AlertDialog.Builder(fragment.getParentActivity(), fragment.getResourceProvider())
                                .setTitle(text(R.string.DanygrammTranslateAnyNetwork))
                                .setMessage(text(R.string.DanygrammTranslateMobileConfirm))
                                .setPositiveButton(text(R.string.OK), (confirm, button) -> translation.setMobileDownload(true))
                                .setNegativeButton(text(R.string.Cancel), null).create());
                    }
                    else if (which == 3) translation.retry();
                    else if (which == 4) deleteModels(fragment, translation);
                }).setNegativeButton(text(R.string.Close), null).create());
    }
    private static void languages(BaseFragment fragment, LocalChatTranslation translation) {
        ArrayList<String> languages = new ArrayList<>(TranslateLanguage.getAllLanguages());
        java.text.Collator collator = java.text.Collator.getInstance(LocaleController.getInstance().getCurrentLocale());
        languages.sort((a, b) -> collator.compare(languageName(a), languageName(b)));
        CharSequence[] labels = new CharSequence[languages.size()];
        for (int i = 0; i < labels.length; i++) labels[i] = (languages.get(i).equals(translation.targetLanguage()) ? "✓ " : "") + languageName(languages.get(i));
        fragment.showDialog(new AlertDialog.Builder(fragment.getParentActivity(), fragment.getResourceProvider()).setTitle(text(R.string.DanygrammTranslateLanguage))
                .setItems(labels, (dialog, which) -> translation.setTargetLanguage(languages.get(which)))
                .setNegativeButton(text(R.string.Cancel), null).create());
    }
    private static void deleteModels(BaseFragment fragment, LocalChatTranslation translation) {
        fragment.showDialog(new AlertDialog.Builder(fragment.getParentActivity(), fragment.getResourceProvider()).setTitle(text(R.string.DanygrammTranslateDeleteModels))
                .setMessage(text(R.string.DanygrammTranslateDeleteInfo))
                .setPositiveButton(text(R.string.Delete), (dialog, which) -> {
                    translation.setEnabled(false);
                    RemoteModelManager manager = RemoteModelManager.getInstance();
                    manager.getDownloadedModels(TranslateRemoteModel.class).addOnSuccessListener(models -> {
                        ArrayList<Task<Void>> tasks = new ArrayList<>();
                        for (TranslateRemoteModel model : models) tasks.add(manager.deleteDownloadedModel(model));
                        Tasks.whenAll(tasks).addOnFailureListener(error -> failure(fragment));
                    }).addOnFailureListener(error -> failure(fragment));
                }).setNegativeButton(text(R.string.Cancel), null).create());
    }
    private static void failure(BaseFragment fragment) {
        if (!fragment.isFinished && !fragment.isPaused() && fragment.getParentActivity() != null)
            fragment.showDialog(new AlertDialog.Builder(fragment.getParentActivity(), fragment.getResourceProvider())
                .setMessage(text(R.string.DanygrammTranslateFailed)).setPositiveButton(text(R.string.OK), null).create());
    }
}
