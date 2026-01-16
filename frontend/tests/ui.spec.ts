import { test, expect } from '@playwright/test';

// UI-only tests - verify buttons, inputs, state management
// These do NOT verify backend responses are correct
test.describe('DocQA UI Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Use the network hostname to simulate real non-HTTPS access
    await page.goto('http://gruntus:3001/');
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForLoadState('networkidle');
  });

  test('suggested prompt buttons fill the chat input when clicked', async ({ page }) => {
    // Load demo documents
    const loadDemoButton = page.getByRole('main').getByRole('button', { name: /load demo documents/i });
    await loadDemoButton.click();

    // Wait for collection to load
    await expect(page.getByRole('heading', { name: /ask about credo4/i })).toBeVisible({ timeout: 5000 });

    // Get the chat input
    const chatInput = page.locator('textarea');
    await expect(chatInput).toBeVisible();

    // Verify input is empty initially
    await expect(chatInput).toHaveValue('');

    // Click the "What is CReDO?" suggested prompt button
    const promptButton = page.getByRole('button', { name: 'What is CReDO?' });
    await expect(promptButton).toBeVisible();
    await promptButton.click();

    // CRITICAL: The input should now contain the prompt text
    await expect(chatInput).toHaveValue('What is CReDO?', { timeout: 2000 });
  });

  test('pressing Enter in chat input sends the message', async ({ page }) => {
    // Load demo documents
    await page.getByRole('main').getByRole('button', { name: /load demo documents/i }).click();
    await expect(page.getByRole('heading', { name: /ask about credo4/i })).toBeVisible({ timeout: 5000 });

    // Type a message
    const chatInput = page.locator('textarea');
    await chatInput.fill('Test message');

    // Count messages before
    const messagesBefore = await page.locator('[class*="message-"]').count();

    // Press Enter
    await chatInput.press('Enter');

    // Wait a moment for state to update
    await page.waitForTimeout(500);

    // CRITICAL: The input should be cleared after sending
    await expect(chatInput).toHaveValue('', { timeout: 2000 });

    // CRITICAL: A user message should appear
    const userMessage = page.locator('text=Test message');
    await expect(userMessage).toBeVisible({ timeout: 2000 });
  });

  test('clicking send button sends the message', async ({ page }) => {
    // Load demo documents
    await page.getByRole('main').getByRole('button', { name: /load demo documents/i }).click();
    await expect(page.getByRole('heading', { name: /ask about credo4/i })).toBeVisible({ timeout: 5000 });

    // Type a message
    const chatInput = page.locator('textarea');
    await chatInput.fill('Another test message');

    // Find and click the send button (the arrow button next to input)
    const sendButton = page.locator('button').filter({ has: page.locator('svg path[d*="12 19"]') });
    await expect(sendButton).toBeVisible();
    await sendButton.click();

    // CRITICAL: The input should be cleared after sending
    await expect(chatInput).toHaveValue('', { timeout: 2000 });

    // CRITICAL: The message should appear in chat
    await expect(page.locator('text=Another test message')).toBeVisible({ timeout: 2000 });
  });

  test('chat is disabled before loading a collection', async ({ page }) => {
    // Without loading demo, the input should be disabled
    const chatInput = page.locator('textarea');
    await expect(chatInput).toBeDisabled();

    // The placeholder should indicate selection is needed
    await expect(chatInput).toHaveAttribute('placeholder', /select a collection/i);
  });

  test('new conversation button creates a new conversation', async ({ page }) => {
    // Load demo documents
    await page.getByRole('main').getByRole('button', { name: /load demo documents/i }).click();
    await expect(page.getByRole('heading', { name: /ask about credo4/i })).toBeVisible({ timeout: 5000 });

    // Send a message to start a conversation
    const chatInput = page.locator('textarea');
    await chatInput.fill('First message');
    await chatInput.press('Enter');
    await expect(page.locator('text=First message')).toBeVisible({ timeout: 2000 });

    // Find and click "New conversation" button in sidebar
    const newConvButton = page.getByRole('button', { name: /new conversation/i });
    await expect(newConvButton).toBeVisible();
    await newConvButton.click();

    // CRITICAL: Messages should be cleared
    await expect(page.locator('text=First message')).not.toBeVisible({ timeout: 2000 });
  });
});
