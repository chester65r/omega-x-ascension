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
                    "document.getElementById('chat-sidebar') !== null && " +
                    "document.getElementById('assistant-new-chat') !== null && " +
                    "document.getElementById('chat-history') !== null && " +
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
                    "document.querySelector('[data-command-item][data-command-tab=\\\"about\\\"]').click();" +
                    "document.getElementById('tools').classList.contains('active') && " +
                    "document.getElementById('about').classList.contains('tool-panel') && " +
                    "document.getElementById('tool-about').open");
            assertEquals("About tab must activate in the running WebView (actual=" + aboutWorks + ")", "true", aboutWorks);

            String assistantWorks = evaluate(webView,
                    "document.querySelector('[data-tab=\"assistant\"]').click();" +
                    "document.getElementById('assistant').classList.contains('active') && " +
                    "document.getElementById('assistant-form') !== null");
            assertEquals("Personal Assistant tab and form must work (actual=" + assistantWorks + ")", "true", assistantWorks);

            String chatSidebarWorks = evaluate(webView,
                    "(() => { document.getElementById('sidebar-toggle').click(); " +
                    "const opened = document.body.classList.contains('sidebar-open') && !document.getElementById('sidebar-backdrop').hidden; " +
                    "document.getElementById('sidebar-close').click(); " +
                    "return opened && !document.body.classList.contains('sidebar-open') && document.getElementById('sidebar-backdrop').hidden; })()");
            assertEquals("Mobile sidebar must open and close without leaving an overlay (actual=" + chatSidebarWorks + ")", "true", chatSidebarWorks);

            String newChatWorks = evaluate(webView,
                    "document.getElementById('assistant-new-chat').click();" +
                    "document.getElementById('assistant').classList.contains('active') && " +
                    "document.getElementById('assistant-prompt').placeholder === 'Message OMEGA…' && " +
                    "document.getElementById('assistant-messages').children.length === 0 && " +
                    "!document.querySelector('.assistant-card').classList.contains('has-messages')");
            assertEquals("New chat must reset the thread and keep the assistant tab active (actual=" + newChatWorks + ")", "true", newChatWorks);

            String browserWorks = evaluate(webView,
                    "document.querySelector('[data-command-item][data-command-tab=\\\"browser\\\"]').click();" +
                    "document.getElementById('tools').classList.contains('active') && " +
                    "document.getElementById('browser').classList.contains('tool-panel') && " +
                    "document.getElementById('tool-browser').open && " +
                    "document.getElementById('browser-results') !== null && " +
                    "document.getElementById('browser-frame') !== null");
            assertEquals("Browser tab and its results/preview containers must exist (actual=" + browserWorks + ")", "true", browserWorks);

            String browserAgentResearch = evaluate(webView,
                    "document.getElementById('browser-agent-research') !== null && " +
                    "document.getElementById('browser-agent-research').textContent.includes('Research with agent') && " +
                    "document.getElementById('browser-agent-research').disabled === false");
            assertEquals("Browser tab must expose the agent research action in the bundled WebView (actual=" + browserAgentResearch + ")", "true", browserAgentResearch);

            String paletteOpens = evaluate(webView,
                    "document.getElementById('command-trigger').click();" +
                    "!document.getElementById('command-palette-backdrop').hidden && " +
                    "document.activeElement.id === 'command-search'");
            assertEquals("Quick command palette must open and focus search (actual=" + paletteOpens + ")", "true", paletteOpens);

            String paletteFilters = evaluate(webView,
                    "var search = document.getElementById('command-search');" +
                    "search.value = 'browser'; search.dispatchEvent(new Event('input', {bubbles:true}));" +
                    "Array.from(document.querySelectorAll('[data-command-item]')).find(e => e.dataset.commandTab === 'browser').hidden === false && " +
                    "Array.from(document.querySelectorAll('[data-command-item]')).find(e => e.dataset.commandTab === 'about').hidden === true && " +
                    "document.getElementById('command-empty').hidden === true");
            assertEquals("Command search must filter results accurately (actual=" + paletteFilters + ")", "true", paletteFilters);

            String paletteNavigates = evaluate(webView,
                    "Array.from(document.querySelectorAll('[data-command-item]')).find(e => e.dataset.commandTab === 'browser').click();" +
                    "document.getElementById('tools').classList.contains('active') && " +
                    "document.getElementById('tool-browser').open && " +
                    "document.getElementById('command-palette-backdrop').hidden");
            assertEquals("A command must navigate and close the palette (actual=" + paletteNavigates + ")", "true", paletteNavigates);

            String allToolGroupsWork = evaluate(webView,
                    "(() => { " +
                    "const search = document.getElementById('command-search'); search.value = ''; search.dispatchEvent(new Event('input', {bubbles:true})); " +
                    "const names = ['overview', 'runs', 'browser', 'local-ai', 'agents', 'logs', 'about']; " +
                    "for (const name of names) { " +
                    "const command = document.querySelector('[data-command-item][data-command-tab=\\\"' + name + '\\\"]'); " +
                    "const panel = document.getElementById(name); const group = document.getElementById('tool-' + name); " +
                    "if (!command || !panel || !group) return false; command.click(); " +
                    "if (!document.getElementById('tools').classList.contains('active') || !panel.classList.contains('tool-panel') || !group.open) return false; " +
                    "} return true; })()");
            assertEquals("Every tool group must be reachable through command navigation (actual=" + allToolGroupsWork + ")", "true", allToolGroupsWork);
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
