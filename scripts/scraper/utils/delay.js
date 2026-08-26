/**
 * Delay utility
 * Replacement for deprecated page.waitForTimeout in Puppeteer v24+
 */

/**
 * Wait for a specified number of milliseconds
 * @param {number} ms - Milliseconds to wait
 * @returns {Promise<void>}
 */
export const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));
