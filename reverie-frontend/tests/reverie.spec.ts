import { test, expect } from '@playwright/test';

const WHISPER = 'Divine command: Inspect the western archives immediately.';

/**
 * These specs run with NO Python backend, which is deliberate: it is the only
 * way to assert that an unacknowledged whisper degrades to UNCONFIRMED instead
 * of being silently reported as having reached consensus.
 */
test.describe('REVERIE Simulation E2E Test Suite', () => {
  test.beforeEach(async ({ page }) => {
    // The Whisper Feed lives on /dashboard. The previous spec loaded the
    // landing page, which has no such tab and does not auto-redirect.
    await page.goto('/dashboard');
  });

  test('renders the dashboard title', async ({ page }) => {
    await expect(page.locator('h1', { hasText: 'REVERIE' })).toBeVisible();
  });

  test('renders an optimistic ghost bubble for an unconfirmed whisper', async ({ page }) => {
    await page.getByRole('button', { name: /Whisper Feed/i }).click();

    const inputField = page.getByPlaceholder('Inject divine suggestion or whisper...');
    await expect(inputField).toBeVisible();
    await inputField.fill(WHISPER);
    await page.locator('button[type="submit"]', { hasText: /^Whisper$/i }).click();

    // The ghost is identified by aria-busy, not by an inline opacity style.
    // Opacity is now a token-backed utility class (opacity-50), so asserting on
    // `[style*="opacity: 0.5"]` as the old spec did would never match.
    const ghost = page.locator('article[aria-busy="true"]', { hasText: WHISPER });
    await expect(ghost).toBeVisible();
    await expect(ghost).toHaveClass(/opacity-50/);
    // Verify it is genuinely half-opaque as rendered, not merely class-tagged.
    await expect(ghost).toHaveCSS('opacity', '0.5');
    await expect(ghost).toContainText(/AWAITING CONSENSUS/i);
  });

  test('degrades an unacknowledged whisper to UNCONFIRMED rather than faking consensus', async ({
    page,
  }) => {
    await page.getByRole('button', { name: /Whisper Feed/i }).click();

    const inputField = page.getByPlaceholder('Inject divine suggestion or whisper...');
    await inputField.fill(WHISPER);
    await page.locator('button[type="submit"]', { hasText: /^Whisper$/i }).click();

    // No backend means no {"ack": [...]} frame, so the ghost timeout must fire
    // and mark the whisper unconfirmed. It must NOT silently become confirmed.
    const message = page.locator('article', { hasText: WHISPER });
    await expect(message).toContainText(/UNCONFIRMED/i, { timeout: 15_000 });
    await expect(message).not.toHaveAttribute('aria-busy', 'true');
  });
});
