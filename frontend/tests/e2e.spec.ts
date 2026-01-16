import { test, expect } from '@playwright/test';

/**
 * End-to-end test that verifies the full RAG pipeline works.
 * This test requires:
 * - Backend running on port 8000
 * - Ollama running with qwen2.5:14b model
 * - Digital Twin PRD collection indexed (id=5)
 */
test.describe('DocQA End-to-End', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://gruntus:3001/');
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForLoadState('networkidle');
  });

  test('CReDO query returns meaningful response about British climate resilience', async ({ page }) => {
    // Step 1: Load demo documents
    const loadDemoButton = page.getByRole('main').getByRole('button', { name: /load demo documents/i });
    await loadDemoButton.click();
    await expect(page.getByRole('heading', { name: /ask about digital twin prd/i })).toBeVisible({ timeout: 5000 });

    // Step 2: Enter the query "What is CReDO?"
    const chatInput = page.locator('textarea');
    await chatInput.fill('What is CReDO?');

    // Step 3: Submit the query
    await chatInput.press('Enter');

    // Verify the user message appears
    await expect(page.locator('text=What is CReDO?')).toBeVisible({ timeout: 2000 });

    // Step 4: Wait for the assistant response to complete
    // When streaming, there's a pulsing cursor with class 'animate-pulse-soft'
    // When done, it disappears
    const assistantMessage = page.locator('.message-assistant').last();
    await expect(assistantMessage).toBeVisible({ timeout: 10000 });

    // Wait for streaming cursor to disappear (streaming complete)
    const streamingCursor = assistantMessage.locator('.animate-pulse-soft');
    await expect(streamingCursor).toBeHidden({ timeout: 120000 });

    // Step 5: Verify the response is about CReDO the British climate resilience project
    const responseText = await assistantMessage.textContent();

    // The response MUST mention these key aspects of the real CReDO project:
    // - Climate (resilience, climate-related)
    // - Infrastructure (critical infrastructure, networks)
    // - UK/British context (or mentions specific UK entities like CADENT, UK Power Networks)

    const lowerResponse = responseText?.toLowerCase() || '';

    // Must mention climate
    const mentionsClimate = lowerResponse.includes('climate');

    // Must mention infrastructure, resilience, network, sector, or hazard
    const mentionsRelevantTopic =
      lowerResponse.includes('infrastructure') ||
      lowerResponse.includes('resilience') ||
      lowerResponse.includes('network') ||
      lowerResponse.includes('sector') ||
      lowerResponse.includes('hazard') ||
      lowerResponse.includes('platform');

    // Should not be a generic/hallucinated response about something else
    const isNotGeneric = !lowerResponse.includes('crowd-driven research') &&
                         !lowerResponse.includes('curriculum');

    console.log('Response preview:', responseText?.substring(0, 500));

    expect(mentionsClimate, 'Response should mention climate').toBe(true);
    expect(mentionsRelevantTopic, 'Response should mention infrastructure/resilience/network/sector/hazard/platform').toBe(true);
    expect(isNotGeneric, 'Response should not be generic hallucination').toBe(true);
  });

  test('Cadent cost of failure query correctly identifies out-of-scope', async ({ page }) => {
    // This tests the hybrid retrieval fix - entity-based search missed the key exclusion text
    // because the text unit was linked to wrong entities. Direct text unit search fixes this.

    // Step 1: Load demo documents
    const loadDemoButton = page.getByRole('main').getByRole('button', { name: /load demo documents/i });
    await loadDemoButton.click();
    await expect(page.getByRole('heading', { name: /ask about digital twin prd/i })).toBeVisible({ timeout: 5000 });

    // Step 2: Enter the scope query
    const chatInput = page.locator('textarea');
    await chatInput.fill('is cadent in the MVP scope for cost of flood failures');

    // Step 3: Submit the query
    await chatInput.press('Enter');

    // Step 4: Wait for response to complete
    const assistantMessage = page.locator('.message-assistant').last();
    await expect(assistantMessage).toBeVisible({ timeout: 10000 });
    const streamingCursor = assistantMessage.locator('.animate-pulse-soft');
    await expect(streamingCursor).toBeHidden({ timeout: 120000 });

    // Step 5: Verify the response correctly says NO (Cadent CoF is NOT in MVP scope)
    const responseText = await assistantMessage.textContent();
    const lowerResponse = responseText?.toLowerCase() || '';

    console.log('Cadent response preview:', responseText?.substring(0, 500));

    // The correct answer is NO - must contain exclusion language
    const hasExclusion =
      lowerResponse.includes('not') ||
      lowerResponse.includes('no cost of failure') ||
      lowerResponse.includes('does not include') ||
      lowerResponse.includes('excluded');

    // Should NOT incorrectly say yes/included without qualification
    const incorrectlyAffirmative =
      (lowerResponse.includes('yes') || lowerResponse.includes('is included')) &&
      !lowerResponse.includes('not') &&
      !lowerResponse.includes('but');

    expect(hasExclusion, 'Response should indicate Cadent CoF is NOT in MVP scope').toBe(true);
    expect(incorrectlyAffirmative, 'Response should not incorrectly affirm Cadent CoF is in scope').toBe(false);
  });
});
