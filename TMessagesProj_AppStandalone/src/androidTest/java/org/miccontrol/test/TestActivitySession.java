package org.miccontrol.test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNotSame;
import static org.junit.Assert.assertTrue;

import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;

import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.runner.lifecycle.ActivityLifecycleCallback;
import androidx.test.runner.lifecycle.ActivityLifecycleMonitor;
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry;
import androidx.test.runner.lifecycle.Stage;

import org.telegram.ui.LaunchActivity;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;
import java.util.function.Predicate;

/** Observes real lifecycle events without requiring the animated Intro's UI queue to idle. */
final class TestActivitySession implements AutoCloseable {
    private final Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
    private final ActivityLifecycleMonitor monitor = ActivityLifecycleMonitorRegistry.getInstance();
    private volatile LaunchActivity activity;

    static TestActivitySession launch() {
        TestActivitySession session = new TestActivitySession();
        try {
            session.activity = session.awaitStage("cold launch", Stage.RESUMED, candidate -> true,
                    () -> session.context.startActivity(session.intent()
                            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK)));
            return session;
        } catch (RuntimeException | Error failure) {
            try {
                session.close();
            } catch (RuntimeException | Error cleanupFailure) {
                failure.addSuppressed(cleanupFailure);
            }
            throw failure;
        }
    }

    void onActivity(Consumer<LaunchActivity> assertion) {
        onMain("activity assertion", () -> {
            assertNotNull("no launched activity", activity);
            assertEquals("activity must be resumed", Stage.RESUMED,
                    monitor.getLifecycleStageOf(activity));
            assertion.accept(activity);
        });
    }

    void backgroundAndResume() {
        LaunchActivity original = activity;
        awaitStage("task background", Stage.STOPPED, candidate -> candidate == original,
                () -> assertTrue("moveTaskToBack rejected", original.moveTaskToBack(true)));
        activity = awaitStage("task resume", Stage.RESUMED, candidate -> candidate == original,
                () -> context.startActivity(intent().addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)));
    }

    void recreate() {
        LaunchActivity original = activity;
        activity = awaitStage("activity recreation", Stage.RESUMED,
                candidate -> candidate != original, original::recreate);
        onMain("recreation identity and destruction", () -> {
            assertNotSame("recreation kept the same instance", original, activity);
            assertEquals("old activity must be destroyed", Stage.DESTROYED,
                    monitor.getLifecycleStageOf(original));
        });
    }

    @Override
    public void close() {
        LaunchActivity current = activity;
        try {
            if (current != null && !callOnMain("cleanup state", current::isDestroyed)) {
                awaitStage("activity cleanup", Stage.DESTROYED,
                        candidate -> candidate == current, current::finish);
            }
        } finally {
            activity = null;
        }
    }

    private Intent intent() {
        return new Intent(context, LaunchActivity.class).setAction(Intent.ACTION_MAIN)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    }

    private LaunchActivity awaitStage(String label, Stage expected,
            Predicate<LaunchActivity> matches, Runnable action) {
        CountDownLatch completed = new CountDownLatch(1);
        AtomicReference<LaunchActivity> result = new AtomicReference<>();
        AtomicReference<Stage> lastStage = new AtomicReference<>();
        ActivityLifecycleCallback callback = (changed, stage) -> {
            if (changed instanceof LaunchActivity) {
                LaunchActivity candidate = (LaunchActivity) changed;
                if (activity == null || activity.isDestroyed() || stage == Stage.RESUMED) {
                    activity = candidate;
                }
                lastStage.set(stage);
                if (stage == expected && matches.test(candidate)) {
                    result.set(candidate);
                    completed.countDown();
                }
            }
        };
        try {
            onMain(label + " request", () -> {
                monitor.addLifecycleCallback(callback);
                action.run();
            });
            boolean observed = completed.await(45, TimeUnit.SECONDS);
            assertTrue(label + " did not reach " + expected + " within 45s; last="
                    + lastStage.get(), observed);
            return result.get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new AssertionError(label + " interrupted", e);
        } finally {
            onMain(label + " observer cleanup", () -> monitor.removeLifecycleCallback(callback));
        }
    }

    static void onMain(String label, Runnable action) {
        callOnMain(label, () -> {
            action.run();
            return null;
        });
    }

    private static <T> T callOnMain(String label, Callable<T> action) {
        FutureTask<T> task = new FutureTask<>(action);
        assertTrue("could not post " + label, new Handler(Looper.getMainLooper()).post(task));
        try {
            return task.get(15, TimeUnit.SECONDS);
        } catch (ExecutionException e) {
            if (e.getCause() instanceof Error) {
                throw (Error) e.getCause();
            }
            throw new AssertionError(label + " failed", e.getCause());
        } catch (TimeoutException e) {
            task.cancel(false);
            throw new AssertionError(label + " did not complete on main thread within 15s", e);
        } catch (InterruptedException e) {
            task.cancel(false);
            Thread.currentThread().interrupt();
            throw new AssertionError(label + " interrupted", e);
        }
    }
}
