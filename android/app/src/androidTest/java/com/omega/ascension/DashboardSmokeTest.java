package com.omega.ascension;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import android.webkit.WebView;

import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.Test;
import org.junit.runner.RunWith;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

@RunWith(AndroidJUnit4.class)
public class DashboardSmokeTest {

    private String evaluate(WebView webView, String script) throws Exception {
        CountDownLatch latch = new CountDownLatch(1);
        AtomicReference<String> result = new AtomicReference<>();
        InstrumentationRegistry.getInstrumentation().runOnMainSync(
                () -> webView.evaluateJavascript(script, value -> {
                    result.set(value);
                    latch.countDown();
                }));
        assertTrue("WebView JavaScript evaluation timed out",
                latch.await(5, TimeUnit.SECONDS));
        return result.get();
    }

    @Test
    public void bundledDashboardLoadsAndMainTabsWork() throws Exception {
        try (ActivityScenario<MainActivity> scenario =
                     ActivityScenario.launch(MainActivity.class)) {
            AtomicReference<WebView> webViewRef = new AtomicReference<>();
            scenario.onActivity(activity -> webViewRef.set(activity.findViewById(R.id.webview)));
            WebView webView = webViewRef.get();
            assertNotNull("MainActivity must contain its WebView", webView);

            String ready = "false";
            String readyCheck =
                    "document.readyState === 'complete' && " +
                    "document.title === 'OMEGA-X ASCENSION' && " +
                    "document.getElementById('assistant') !== null && " +
                    "document.getElementById('browser-results') !== null && " +
                    "document.getElementById('logs') !== null && " +
                    "document.getElementById('about') !== null";
            for (int attempt = 0; attempt < 40; attempt++) {
                ready = evaluate(webView, readyCheck);
                if ("true".equals(ready)) {
                    break;
                }
                Thread.sleep(250);
            }
            assertEquals("Bundled HTML and critical screens must load in WebView", "true", ready);

            String tabConsistency = evaluate(webView,
                    "Array.from(document.querySelectorAll('.tab')).map(e => e.dataset.tab).join(',') === " +
                    "Array.from(document.querySelectorAll('section.tab-content')).map(e => e.id).join(',')");
            assertEquals("Each navigation tab must map to an existing section", "true", tabConsistency);

            String aboutWorks = evaluate(webView,
                    "document.querySelector('[data-tab=\"about\"]').click();" +
                    "document.getElementById('about').classList.contains('active')");
            assertEquals("About tab must activate in the running WebView", "true", aboutWorks);

            String assistantWorks = evaluate(webView,
                    "document.querySelector('[data-tab=\"assistant\"]').click();" +
                    "document.getElementById('assistant').classList.contains('active') && " +
                    "document.getElementById('assistant-form') !== null");
            assertEquals("Personal Assistant tab and form must work", "true", assistantWorks);

            String browserWorks = evaluate(webView,
                    "document.querySelector('[data-tab=\"browser\"]').click();" +
                    "document.getElementById('browser').classList.contains('active') && " +
                    "document.getElementById('browser-results') !== null && " +
                    "document.getElementById('browser-frame') !== null");
            assertEquals("Browser tab and its results/preview containers must exist", "true", browserWorks);
        }
    }
}
