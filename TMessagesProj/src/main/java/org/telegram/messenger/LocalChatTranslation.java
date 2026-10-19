package org.telegram.messenger;

import android.content.SharedPreferences;
import android.text.TextUtils;
import com.google.mlkit.common.model.DownloadConditions;
import com.google.mlkit.common.model.RemoteModelManager;
import com.google.mlkit.nl.languageid.LanguageIdentification;
import com.google.mlkit.nl.languageid.LanguageIdentifier;
import com.google.mlkit.nl.translate.TranslateLanguage;
import com.google.mlkit.nl.translate.TranslateRemoteModel;
import com.google.mlkit.nl.translate.Translation;
import com.google.mlkit.nl.translate.Translator;
import com.google.mlkit.nl.translate.TranslatorOptions;
import java.util.ArrayDeque;
import java.lang.ref.WeakReference;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.WeakHashMap;

/** Chat-scoped, on-device display translation. Never changes a TL message or sends text. */
public final class LocalChatTranslation implements AutoCloseable {
    private static final int MAX_MODELS = 4;
    // All callbacks use the main executor. Reservations also cover downloads
    // whose chat was closed while ML Kit's non-cancellable task is still running.
    private static final Set<String> downloadingModels = new HashSet<>();
    private final long dialogId;
    private final TranslateController server;
    private final SharedPreferences preferences;
    private final String key;
    private final Runnable changed;
    private final ArrayDeque<Request> queue = new ArrayDeque<>();
    private final Set<String> pending = new LinkedHashSet<>(), failed = new LinkedHashSet<>();
    private final Set<MessageObject> visible = Collections.newSetFromMap(new WeakHashMap<>());
    private final LinkedHashMap<MessageObject, Boolean> applied = new LinkedHashMap<>();
    private final android.util.LruCache<String, String> cache = new android.util.LruCache<>(128);
    private final LinkedHashMap<String, Translator> translators = new LinkedHashMap<>(4, 0.75f, true);
    private final Set<String> preparedPairs = new HashSet<>();
    private LanguageIdentifier identifier;
    private boolean enabled, active = true, closed, processing, attached, retryRequired;
    private boolean localSelectedInThisSession;
    private String target;
    private int generation, status = R.string.DanygrammTranslateReady;
    private Runnable timeout;
    private Request currentRequest;

    private static final class Request {
        final MessageObject message;
        final String source, target, key;
        Request(MessageObject message, String target) {
            this.message = message; this.target = target;
            source = message.messageOwner.message; key = target + '\n' + source;
        }
    }
    public LocalChatTranslation(int account, long dialogId, Runnable changed) {
        this.dialogId = dialogId; this.changed = changed;
        server = MessagesController.getInstance(account).getTranslateController();
        preferences = MessagesController.getMainSettings(account);
        key = "danygrammLocalTranslate_" + dialogId;
        target = supportedLanguage(preferences.getString(key + "_language", TranslateController.currentLanguage()));
        enabled = preferences.getBoolean(key, false);
        localSelectedInThisSession = enabled;
        updateGuard();
    }
    public static String supportedLanguage(String tag) {
        String language = tag == null ? null : TranslateLanguage.fromLanguageTag(tag.replace('_', '-'));
        return language == null ? TranslateLanguage.ENGLISH : language;
    }
    public boolean isEnabled() { return enabled; }
    public boolean isSelectedInThisSession() { return localSelectedInThisSession && !closed; }
    public String targetLanguage() { return target; }
    public boolean allowsMobileDownload() { return preferences.getBoolean("danygrammTranslationMobile", false); }
    public int statusResource() { return status; }
    public void setEnabled(boolean value) {
        if (closed || enabled == value) return;
        localSelectedInThisSession = true;
        enabled = value;
        preferences.edit().putBoolean(key, value).apply();
        reset(); updateGuard(); changed.run();
    }
    public void setTargetLanguage(String language) {
        if (closed) return;
        String value = supportedLanguage(language);
        if (target.equals(value)) return;
        target = value; preferences.edit().putString(key + "_language", value).apply();
        reset(); changed.run();
    }
    public void setMobileDownload(boolean value) {
        if (closed) return;
        preferences.edit().putBoolean("danygrammTranslationMobile", value).apply();
        retry();
    }
    public void retry() { if (!closed) { reset(); changed.run(); } }
    public void setActive(boolean value) {
        if (active == value || closed) return;
        active = value; reset(); updateGuard(); changed.run();
    }
    private void updateGuard() {
        boolean needed = localSelectedInThisSession && !closed;
        if (needed == attached) return;
        attached = needed;
        if (needed) server.attachLocalDisplay(dialogId); else server.detachLocalDisplay(dialogId);
    }
    public static boolean eligible(MessageObject message) {
        if (message == null || message.messageOwner == null || message.messageOwner.out || message.isOutOwner()
                || message.messageOwner.summarizedOpen || message.isRestrictedMessage || message.isSponsored()) return false;
        int type = message.type;
        return (type == MessageObject.TYPE_TEXT || type == MessageObject.TYPE_PHOTO || type == MessageObject.TYPE_VIDEO
                || type == MessageObject.TYPE_FILE || type == MessageObject.TYPE_MUSIC)
                && !TextUtils.isEmpty(message.messageOwner.message) && message.messageOwner.message.length() <= 4096;
    }
    public void beginVisiblePass() { visible.clear(); }
    public void check(MessageObject message, boolean onScreen) {
        if (message == null) return;
        if (onScreen) visible.add(message); else visible.remove(message);
        if (!enabled || !active || closed || !onScreen || !eligible(message)) return;
        if (message.getDialogId() != dialogId) return;
        if (message.hasLocalTranslation(this)) return;
        message.clearLocalTranslation();
        if (message.translated && !message.messageOwner.summarizedOpen) {
            message.updateTranslation(true);
            message.forceUpdate = true;
            changed.run();
        }
        Request request = new Request(message, target);
        String cached = cache.get(request.key);
        if (cached != null) { apply(request, cached); return; }
        if (retryRequired || pending.contains(request.key) || failed.contains(request.key) || queue.size() >= 16) return;
        pending.add(request.key); queue.add(request); next();
    }
    private void next() {
        if (processing || closed || !enabled || !active || retryRequired) return;
        Request request;
        do {
            request = queue.poll();
            if (request == null) return;
            if (visible.contains(request.message) && eligible(request.message)
                    && request.message.getDialogId() == dialogId
                    && TextUtils.equals(request.source, request.message.messageOwner.message)) break;
            pending.remove(request.key);
        } while (true);
        final Request work = request;
        final int token = generation;
        currentRequest = work;
        processing = true; status = R.string.DanygrammTranslateWorking; changed.run();
        timeout = () -> { if (valid(work, token)) finish(work, token, null, R.string.DanygrammTranslateFailed); };
        AndroidUtilities.runOnUIThread(timeout, 90000);
        final WeakReference<LocalChatTranslation> owner = new WeakReference<>(this);
        final WeakReference<Request> item = new WeakReference<>(work);
        try {
            if (identifier == null) identifier = LanguageIdentification.getClient();
            identifier.identifyLanguage(work.source).addOnSuccessListener(languageTag -> {
                LocalChatTranslation session = current(owner, item, token);
                if (session != null) session.identified(item.get(), token, languageTag);
            }).addOnFailureListener(error -> complete(owner, item, token, null));
        } catch (RuntimeException error) {
            finish(work, token, null, R.string.DanygrammTranslateFailed);
        }
    }
    private void identified(Request work, int token, String languageTag) {
        String source = TranslateLanguage.fromLanguageTag(languageTag);
        if (source == null) { finish(work, token, work.source, R.string.DanygrammTranslateUnsupported); return; }
        if (source.equals(work.target)) { finish(work, token, work.source, R.string.DanygrammTranslateReady); return; }
        String pair = source + ":" + work.target;
        final Translator client;
        try {
            Translator existing = translators.get(pair);
            if (existing == null) {
                if (translators.size() >= 3) {
                    String oldest = translators.keySet().iterator().next();
                    translators.remove(oldest).close(); preparedPairs.remove(oldest);
                }
                existing = Translation.getClient(new TranslatorOptions.Builder()
                        .setSourceLanguage(source).setTargetLanguage(work.target).build());
                translators.put(pair, existing);
            }
            client = existing;
            if (preparedPairs.contains(pair)) { translate(work, token, client); return; }
            final WeakReference<LocalChatTranslation> owner = new WeakReference<>(this);
            final WeakReference<Request> item = new WeakReference<>(work);
            RemoteModelManager.getInstance().getDownloadedModels(TranslateRemoteModel.class)
                    .addOnSuccessListener(models -> {
                        LocalChatTranslation session = current(owner, item, token);
                        if (session != null) session.prepare(item.get(), token, source, pair, client, models);
                    }).addOnFailureListener(error -> complete(owner, item, token, null));
        } catch (RuntimeException error) {
            finish(work, token, null, R.string.DanygrammTranslateFailed);
        }
    }
    private void prepare(Request work, int token, String source, String pair,
            Translator client, Set<TranslateRemoteModel> models) {
        Set<String> installed = new HashSet<>();
        for (TranslateRemoteModel model : models) installed.add(model.getLanguage());
        installed.remove(TranslateLanguage.ENGLISH);
        final Set<String> missing = new HashSet<>();
        if (!TranslateLanguage.ENGLISH.equals(source)) missing.add(source);
        if (!TranslateLanguage.ENGLISH.equals(work.target)) missing.add(work.target);
        missing.removeAll(installed);
        if (missing.isEmpty()) {
            preparedPairs.add(pair); translate(work, token, client); return;
        }
        Set<String> total = new HashSet<>(installed);
        total.addAll(downloadingModels); total.addAll(missing);
        if (total.size() > MAX_MODELS) {
            finish(work, token, null, R.string.DanygrammTranslateModelLimit); return;
        }
        status = R.string.DanygrammTranslateModels; changed.run();
        final WeakReference<LocalChatTranslation> owner = new WeakReference<>(this);
        final WeakReference<Request> item = new WeakReference<>(work);
        DownloadConditions.Builder conditions = new DownloadConditions.Builder();
        if (!allowsMobileDownload()) conditions.requireWifi();
        downloadingModels.addAll(missing);
        try {
            client.downloadModelIfNeeded(conditions.build()).addOnSuccessListener(unused -> {
                downloadingModels.removeAll(missing);
                LocalChatTranslation session = current(owner, item, token);
                if (session != null) {
                    session.preparedPairs.add(pair);
                    session.translate(item.get(), token, client);
                }
            }).addOnFailureListener(error -> {
                downloadingModels.removeAll(missing);
                complete(owner, item, token, null);
            });
        } catch (RuntimeException error) {
            downloadingModels.removeAll(missing);
            finish(work, token, null, R.string.DanygrammTranslateFailed);
        }
    }
    private void translate(Request work, int token, Translator client) {
        status = R.string.DanygrammTranslateWorking; changed.run();
        final WeakReference<LocalChatTranslation> owner = new WeakReference<>(this);
        final WeakReference<Request> item = new WeakReference<>(work);
        try {
            client.translate(work.source).addOnSuccessListener(text -> complete(owner, item, token, text))
                    .addOnFailureListener(error -> complete(owner, item, token, null));
        } catch (RuntimeException error) {
            finish(work, token, null, R.string.DanygrammTranslateFailed);
        }
    }
    private boolean valid(Request request, int token) {
        return request != null && request == currentRequest && token == generation
                && processing && enabled && active && !closed;
    }
    private static LocalChatTranslation current(WeakReference<LocalChatTranslation> owner,
            WeakReference<Request> item, int token) {
        LocalChatTranslation session = owner.get();
        return session != null && session.valid(item.get(), token) ? session : null;
    }
    private static void complete(WeakReference<LocalChatTranslation> owner,
            WeakReference<Request> item, int token, String text) {
        LocalChatTranslation session = current(owner, item, token);
        if (session != null) session.finish(item.get(), token, text,
                text == null ? R.string.DanygrammTranslateFailed : R.string.DanygrammTranslateReady);
    }
    private void finish(Request request, int token, String result, int resultStatus) {
        if (!valid(request, token) || !pending.contains(request.key)) return;
        AndroidUtilities.cancelRunOnUIThread(timeout);
        timeout = null;
        if (result == null) {
            failed.add(request.key);
            if (failed.size() > 32) failed.remove(failed.iterator().next());
        } else {
            cache.put(request.key, result);
            if (visible.contains(request.message)) apply(request, result);
        }
        pending.remove(request.key); processing = false; currentRequest = null; status = resultStatus;
        // Invalidate listeners after a timeout as the SDK download task itself
        // has no public cancellation API and may complete later.
        if (result == null) {
            retryRequired = true;
            generation++; queue.clear(); pending.clear(); closeClients();
        }
        changed.run(); next();
    }
    private void apply(Request request, String translated) {
        if (TextUtils.equals(request.source, translated) || !eligible(request.message)
                || !TextUtils.equals(request.source, request.message.messageOwner.message)) return;
        request.message.setLocalTranslation(request.source, translated, this);
        applied.put(request.message, true);
        if (applied.size() > 128) {
            MessageObject oldest = applied.keySet().iterator().next();
            applied.remove(oldest); oldest.clearLocalTranslation(this);
        }
        changed.run();
    }
    private void closeClients() {
        if (identifier != null) identifier.close();
        identifier = null;
        for (Translator translator : translators.values()) translator.close();
        translators.clear(); preparedPairs.clear();
    }
    private void reset() {
        generation++;
        if (timeout != null) AndroidUtilities.cancelRunOnUIThread(timeout);
        timeout = null; processing = false; currentRequest = null; retryRequired = false;
        queue.clear(); pending.clear(); failed.clear(); visible.clear();
        for (MessageObject message : applied.keySet()) message.clearLocalTranslation(this);
        applied.clear(); closeClients(); status = R.string.DanygrammTranslateReady;
    }
    @Override public void close() {
        if (closed) return;
        closed = true; reset(); updateGuard(); cache.evictAll();
    }
}
