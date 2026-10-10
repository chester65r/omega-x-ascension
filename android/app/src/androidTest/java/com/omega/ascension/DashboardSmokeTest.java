package com.omega.ascension;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import android.content.Intent;
import android.widget.EditText;
import android.webkit.WebView;

import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.junit.FixMethodOrder;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.MethodSorters;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

@FixMethodOrder(MethodSorters.NAME_ASCENDING)
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
                latch.await(10, TimeUnit.SECONDS));
        return result.get();
    }

    @Test
    public void test01BundledDashboardLoadsAndMainTabsWork() throws Exception {
        try (ActivityScenario<MainActivity> scenario =
                     ActivityScenario.launch(MainActivity.class)) {
            AtomicReference<WebView> webViewRef = new AtomicReference<>();
            scenario.onActivity(activity -> webViewRef.set(activity.findViewById(R.id.webview)));
            WebView webView = webViewRef.get();
            assertNotNull("MainActivity must contain its WebView", webView);

            boolean loaded = false;
            for (int attempt = 0; attempt < 80; attempt++) {
                AtomicReference<Boolean> loadedRef = new AtomicReference<>(false);
                scenario.onActivity(activity -> loadedRef.set(activity.isDashboardLoaded()));
                if (Boolean.TRUE.equals(loadedRef.get())) {
                    loaded = true;
                    break;
                }
                Thread.sleep(250);
            }
            assertTrue("MainActivity did not finish loading its trusted bundled dashboard", loaded);

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
            assertEquals("Bundled HTML and critical screens must load in WebView (actual=" + ready + ")", "true", ready);

            String tabConsistency = evaluate(webView,
                    "Array.from(document.querySelectorAll('.tab')).map(e => e.dataset.tab).join(',') === " +
                    "Array.from(document.querySelectorAll('section.tab-content')).map(e => e.id).join(',')");
            assertEquals("Each navigation tab must map to an existing section (actual=" + tabConsistency + ")", "true", tabConsistency);

            String aboutWorks = evaluate(webView,
                    "document.querySelector('[data-tab=\"about\"]').click();" +
                    "document.getElementById('about').classList.contains('active')");
            assertEquals("About tab must activate in the running WebView (actual=" + aboutWorks + ")", "true", aboutWorks);

            String assistantWorks = evaluate(webView,
                    "document.querySelector('[data-tab=\"assistant\"]').click();" +
                    "document.getElementById('assistant').classList.contains('active') && " +
                    "document.getElementById('assistant-form') !== null");
            assertEquals("Personal Assistant tab and form must work (actual=" + assistantWorks + ")", "true", assistantWorks);

            String browserWorks = evaluate(webView,
                    "document.querySelector('[data-tab=\"browser\"]').click();" +
                    "document.getElementById('browser').classList.contains('active') && " +
                    "document.getElementById('browser-results') !== null && " +
                    "document.getElementById('browser-frame') !== null");
            assertEquals("Browser tab and its results/preview containers must exist (actual=" + browserWorks + ")", "true", browserWorks);
        }
    }


    @Test
    public void test02NativeBrowserLaunchesWithAddressBarAndWebView() {
        Intent intent = new Intent(
                InstrumentationRegistry.getInstrumentation().getTargetContext(),
                BrowserActivity.class);
        intent.putExtra(BrowserActivity.EXTRA_URL, "https://example.com/");
        try (ActivityScenario<BrowserActivity> scenario = ActivityScenario.launch(intent)) {
            AtomicReference<WebView> browserRef = new AtomicReference<>();
            AtomicReference<EditText> addressViewRef = new AtomicReference<>();
            AtomicReference<String> addressTextRef = new AtomicReference<>();
            scenario.onActivity(activity -> {
                WebView browser = activity.findViewById(R.id.native_browser_webview);
                browserRef.set(browser);
                if (browser != null) browser.stopLoading();
                EditText address = activity.findViewById(R.id.native_browser_address);
                addressViewRef.set(address);
                addressTextRef.set(address == null ? "" : address.getText().toString());
            });
            assertNotNull("Native browser must contain a WebView", browserRef.get());
            assertNotNull("Native browser must contain an address bar", addressViewRef.get());
            assertTrue("Native browser must preserve a valid HTTPS address",
                    addressTextRef.get() != null && addressTextRef.get().startsWith("https://example.com"));
        }
    }
}
