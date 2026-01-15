import { test, expect } from '@playwright/test';

// Test over HTTP hostname to match real browser conditions
test.describe('DocQA Frontend Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Use network hostname to simulate real non-HTTPS access
    await page.goto('http://gruntus:3001/');
    await page.evaluate(() => localStorage.clear());
    await page.reload();
  });

  test('page loads successfully', async ({ page }) => {
    // Check title
    await expect(page).toHaveTitle('DocQA - Document Intelligence');

    // Check sidebar heading is visible
    await expect(page.locator('header h1').first()).toBeVisible();
  });

  test('empty state shows load demo button', async ({ page }) => {
    // Should show "Document Q&A" heading in empty state
    await expect(page.getByRole('heading', { name: 'Document Q&A' })).toBeVisible();

    // Should show "Load demo documents" buttons (one in sidebar, one in main)
    const loadDemoButtons = page.getByRole('button', { name: /load demo documents/i });
    await expect(loadDemoButtons.first()).toBeVisible();
  });

  test('clicking load demo documents enables chat', async ({ page }) => {
    // Click the main load demo button
    const loadDemoButton = page.getByRole('main').getByRole('button', { name: /load demo documents/i });
    await loadDemoButton.click();

    // Wait for collection to load - check heading changes
    await expect(page.getByRole('heading', { name: /ask about credo4/i })).toBeVisible({ timeout: 5000 });

    // Chat input should now be enabled
    const chatInput = page.locator('textarea');
    await expect(chatInput).toBeVisible();
    await expect(chatInput).toBeEnabled();
  });

  test('can type in chat input', async ({ page }) => {
    // Load demo documents
    await page.getByRole('main').getByRole('button', { name: /load demo documents/i }).click();

    // Wait for collection
    await expect(page.getByRole('heading', { name: /ask about credo4/i })).toBeVisible({ timeout: 5000 });

    // Type a message
    const chatInput = page.locator('textarea');
    await chatInput.fill('What is CReDO?');

    // Verify the text was entered
    await expect(chatInput).toHaveValue('What is CReDO?');
  });

  test('sending message shows response (mock)', async ({ page }) => {
    // Load demo documents
    await page.getByRole('main').getByRole('button', { name: /load demo documents/i }).click();

    // Wait for collection
    await expect(page.getByRole('heading', { name: /ask about credo4/i })).toBeVisible({ timeout: 5000 });

    // Type and send a message
    const chatInput = page.locator('textarea');
    await chatInput.fill('What is CReDO?');

    // Press Enter to send
    await chatInput.press('Enter');

    // Should see the user message appear in chat
    await expect(page.locator('.message-user')).toBeVisible({ timeout: 5000 });

    // Should see assistant response (mock response streams "I found some relevant information")
    await expect(page.locator('.message-assistant')).toBeVisible({ timeout: 10000 });

    // Wait for streaming to complete and check content
    await expect(page.locator('text=/relevant information/i')).toBeVisible({ timeout: 15000 });
  });

  test('theme toggle works', async ({ page }) => {
    // Find theme toggle button in sidebar
    const themeToggle = page.locator('button[title*="mode"]');
    await expect(themeToggle).toBeVisible();

    // Check initial state (should be dark by default)
    const htmlElement = page.locator('html');
    await expect(htmlElement).toHaveClass(/dark/);

    // Click to toggle to light
    await themeToggle.click();
    await expect(htmlElement).not.toHaveClass(/dark/);

    // Click to toggle back to dark
    await themeToggle.click();
    await expect(htmlElement).toHaveClass(/dark/);
  });

  test('sidebar toggle works', async ({ page }) => {
    // Sidebar should be visible initially (width is w-72)
    const sidebarContainer = page.locator('.w-72').first();
    await expect(sidebarContainer).toBeVisible();

    // Find and click sidebar toggle button
    const sidebarToggle = page.locator('button[title*="sidebar"]');
    await sidebarToggle.click();

    // Sidebar should collapse (width becomes w-0)
    await expect(page.locator('.w-0')).toBeVisible();
  });

  test('suggested prompts are shown after loading demo', async ({ page }) => {
    // Load demo documents
    await page.getByRole('main').getByRole('button', { name: /load demo documents/i }).click();

    // Wait for collection
    await expect(page.getByRole('heading', { name: /ask about credo4/i })).toBeVisible({ timeout: 5000 });

    // Check suggested prompts appear
    await expect(page.getByRole('button', { name: 'What is CReDO?' })).toBeVisible();
    await expect(page.getByRole('button', { name: /cadent cost/i })).toBeVisible();
  });
});
