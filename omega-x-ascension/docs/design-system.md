# OMEGA-X ASCENSION — Designly UI contract

## Design intent

OMEGA-X should feel like a quiet, capable assistant, not a sci-fi control panel. The conversation is the primary surface; tools are available in a separate workspace so the user does not have to scan every capability before sending a message.

## Hierarchy and layout

1. One primary focal point per state: the welcome headline on an empty conversation, the latest response in an active conversation.
2. Keep the message composer anchored at the bottom of the mobile viewport. Respect status/navigation bars, safe-area insets, short viewports, and the on-screen keyboard.
3. Suggested tasks are secondary, arranged in a consistent two-column grid on phones. Connection status, disclaimers, and logs remain tertiary.
4. Keep the chat content column readable and centered; messages themselves stay left-aligned. Avoid horizontal overflow and avoid forcing the entire page to scroll to reach the composer.
5. Keep Tools, Browser, Logs, and About accessible from the Tools page and reachable by keyboard/touch.

## Visual language

- Canvas: charcoal #212121; sidebar #171717; composer #2f2f2f; dividers #414141.
- Text should be legible by luminance contrast, not by adding more accent colors. Target WCAG AA contrast (4.5:1 normal text, 3:1 large text). Verify final color pairs on the rendered interface.
- Use a restrained neutral palette. Avoid decorative glow, particles, neon gradients, and sci-fi ornament unless a feature has a clear functional reason.
- Use four typographic roles at most: headline, body, metadata, and action.
- Every interactive item needs a visible focus state, a clear label, and a touch-friendly target. Honor reduced-motion preferences.
- Preserve the OMEGA-X name and distinguish live, disabled, and unavailable capabilities truthfully.

## Interaction and security contract

- New chat, chat history, composer, navigation, and tool groups must remain usable at Android portrait widths.
- Never show JWTs or refresh credentials after enrollment. Do not put signing secrets in APK resources, local JS, or web storage.
- Explain the one-time setup requirement clearly; after Android Keystore confirms the refresh credential, reconnect automatically and hide setup inputs.
- The sandbox command-execution tool is intentionally disabled until per-tenant OS isolation is implemented and adversarially tested. Do not present it as a working unrestricted terminal. Browser access and workspace file capabilities must remain separate and policy-limited.
- No mock answer is allowed to masquerade as a real provider response.

## QA gates

Before a release, run JavaScript syntax checks, Designly art-direction lint, Python compile/tests, the isolated API-to-worker integration test, APK asset/signature verification, and Android emulator smoke tests. Review the actual rendered app at phone and desktop widths; a passing DOM smoke test is necessary but not a substitute for a visual check.
