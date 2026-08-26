/**
 * Robust selector waiting utilities
 * Provides fallback strategies for dynamic content
 */

import { delay } from './delay.js';

/**
 * Wait for any of multiple selectors (first one wins)
 * @param {Page} page - Puppeteer page instance
 * @param {Array<string>} selectors - Array of CSS selectors to try
 * @param {Object} options - Waiting options
 * @returns {Promise<string>} The selector that matched
 */
export async function waitForAnySelector(page, selectors, options = {}) {
  const timeout = options.timeout || 10000;
  const startTime = Date.now();

  while (Date.now() - startTime < timeout) {
    for (const selector of selectors) {
      try {
        await page.waitForSelector(selector, { timeout: 500 });
        return selector;
      } catch (error) {
        // Try next selector
      }
    }

    // Wait a bit before trying again
    await delay(100);
  }

  throw new Error(`None of the selectors found: ${selectors.join(', ')}`);
}

/**
 * Wait for selector with text content match
 * @param {Page} page - Puppeteer page instance
 * @param {string} selector - CSS selector
 * @param {string|RegExp} textMatch - Text to match
 * @param {Object} options - Waiting options
 * @returns {Promise<ElementHandle>}
 */
export async function waitForSelectorWithText(page, selector, textMatch, options = {}) {
  const timeout = options.timeout || 10000;

  await page.waitForFunction(
    (sel, text) => {
      const elements = Array.from(document.querySelectorAll(sel));
      return elements.some(el => {
        const content = el.textContent || '';
        if (text instanceof RegExp) {
          return text.test(content);
        }
        return content.includes(text);
      });
    },
    { timeout },
    selector,
    textMatch
  );

  return page.evaluateHandle(
    (sel, text) => {
      const elements = Array.from(document.querySelectorAll(sel));
      return elements.find(el => {
        const content = el.textContent || '';
        if (text instanceof RegExp) {
          return text.test(content);
        }
        return content.includes(text);
      });
    },
    selector,
    textMatch
  );
}

/**
 * Wait for element to be visible and stable (not animating)
 * @param {Page} page - Puppeteer page instance
 * @param {string} selector - CSS selector
 * @param {Object} options - Waiting options
 */
export async function waitForStableElement(page, selector, options = {}) {
  const timeout = options.timeout || 10000;

  // Wait for element to exist
  await page.waitForSelector(selector, { timeout });

  // Wait for element to be visible
  await page.waitForFunction(
    (sel) => {
      const element = document.querySelector(sel);
      if (!element) return false;

      const rect = element.getBoundingClientRect();
      const style = window.getComputedStyle(element);

      return (
        rect.width > 0 &&
        rect.height > 0 &&
        style.visibility !== 'hidden' &&
        style.display !== 'none' &&
        style.opacity !== '0'
      );
    },
    { timeout },
    selector
  );

  // Wait for element position to stabilize (not animating)
  let lastRect = null;
  let stableCount = 0;

  while (stableCount < 3) {
    const rect = await page.evaluate((sel) => {
      const element = document.querySelector(sel);
      const { top, left, width, height } = element.getBoundingClientRect();
      return { top, left, width, height };
    }, selector);

    if (
      lastRect &&
      rect.top === lastRect.top &&
      rect.left === lastRect.left &&
      rect.width === lastRect.width &&
      rect.height === lastRect.height
    ) {
      stableCount++;
    } else {
      stableCount = 0;
    }

    lastRect = rect;
    await delay(100);
  }
}

/**
 * Retry function with exponential backoff
 * @param {Function} fn - Async function to retry
 * @param {Object} options - Retry options
 * @returns {Promise<any>}
 */
export async function retryWithBackoff(fn, options = {}) {
  const maxRetries = options.maxRetries || 3;
  const initialDelay = options.initialDelay || 1000;
  const maxDelay = options.maxDelay || 10000;
  const onRetry = options.onRetry || (() => {});

  let lastError;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      if (attempt < maxRetries - 1) {
        const delay = Math.min(initialDelay * Math.pow(2, attempt), maxDelay);
        onRetry(error, attempt + 1, delay);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }

  throw lastError;
}
