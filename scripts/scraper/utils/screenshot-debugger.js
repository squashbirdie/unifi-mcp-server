/**
 * Screenshot debugging utilities
 * Helps diagnose selector and scraping issues
 */

import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SCREENSHOT_DIR = path.join(__dirname, '../../screenshots');

/**
 * Ensure screenshot directory exists
 */
async function ensureScreenshotDir() {
  try {
    await fs.mkdir(SCREENSHOT_DIR, { recursive: true });
  } catch (error) {
    // Directory exists or can't be created
  }
}

/**
 * Take a screenshot with timestamp
 * @param {Page} page - Puppeteer page instance
 * @param {string} name - Screenshot name (without extension)
 * @param {Object} options - Screenshot options
 * @returns {Promise<string>} Path to screenshot
 */
export async function takeScreenshot(page, name, options = {}) {
  await ensureScreenshotDir();

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const filename = `${name}_${timestamp}.png`;
  const filepath = path.join(SCREENSHOT_DIR, filename);

  await page.screenshot({
    path: filepath,
    fullPage: options.fullPage !== false,
    ...options
  });

  console.log(`📸 Screenshot saved: ${filename}`);
  return filepath;
}

/**
 * Take screenshot and dump HTML for debugging
 * @param {Page} page - Puppeteer page instance
 * @param {string} name - Debug name
 * @returns {Promise<Object>} Paths to screenshot and HTML
 */
export async function debugSnapshot(page, name) {
  await ensureScreenshotDir();

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const baseName = `${name}_${timestamp}`;

  // Screenshot
  const screenshotPath = path.join(SCREENSHOT_DIR, `${baseName}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: true });

  // HTML dump
  const html = await page.content();
  const htmlPath = path.join(SCREENSHOT_DIR, `${baseName}.html`);
  await fs.writeFile(htmlPath, html);

  // DOM structure dump (for selector analysis)
  const domStructure = await page.evaluate(() => {
    function getNodeInfo(node, depth = 0) {
      if (depth > 5) return null; // Limit depth

      const info = {
        tag: node.tagName?.toLowerCase(),
        id: node.id || undefined,
        className: node.className || undefined,
        text: node.textContent?.substring(0, 50),
        attributes: {}
      };

      // Get relevant attributes
      if (node.attributes) {
        Array.from(node.attributes).forEach(attr => {
          if (['data-testid', 'data-test', 'role', 'aria-label', 'name', 'type'].includes(attr.name)) {
            info.attributes[attr.name] = attr.value;
          }
        });
      }

      // Get children (selective)
      const children = Array.from(node.children || [])
        .filter(child => child.tagName) // Only element nodes
        .slice(0, 10) // Limit children
        .map(child => getNodeInfo(child, depth + 1))
        .filter(Boolean);

      if (children.length > 0) {
        info.children = children;
      }

      return info;
    }

    return getNodeInfo(document.body);
  });

  const domPath = path.join(SCREENSHOT_DIR, `${baseName}_dom.json`);
  await fs.writeFile(domPath, JSON.stringify(domStructure, null, 2));

  console.log(`🐛 Debug snapshot saved:`);
  console.log(`   Screenshot: ${baseName}.png`);
  console.log(`   HTML: ${baseName}.html`);
  console.log(`   DOM: ${baseName}_dom.json`);

  return {
    screenshot: screenshotPath,
    html: htmlPath,
    dom: domPath
  };
}

/**
 * Highlight element on page and take screenshot
 * @param {Page} page - Puppeteer page instance
 * @param {string} selector - CSS selector to highlight
 * @param {string} name - Screenshot name
 */
export async function highlightAndCapture(page, selector, name) {
  // Inject highlighting style
  await page.evaluate((sel) => {
    const elements = document.querySelectorAll(sel);
    elements.forEach(el => {
      el.style.outline = '3px solid red';
      el.style.backgroundColor = 'rgba(255, 0, 0, 0.1)';
    });
  }, selector);

  const path = await takeScreenshot(page, `highlighted_${name}`);

  // Remove highlighting
  await page.evaluate((sel) => {
    const elements = document.querySelectorAll(sel);
    elements.forEach(el => {
      el.style.outline = '';
      el.style.backgroundColor = '';
    });
  }, selector);

  return path;
}

/**
 * Log all elements matching a selector
 * @param {Page} page - Puppeteer page instance
 * @param {string} selector - CSS selector
 * @returns {Promise<Array>} Element information
 */
export async function inspectElements(page, selector) {
  const elements = await page.evaluate((sel) => {
    return Array.from(document.querySelectorAll(sel)).map((el, index) => ({
      index,
      tag: el.tagName?.toLowerCase(),
      id: el.id || null,
      className: el.className || null,
      text: el.textContent?.substring(0, 100),
      attributes: Object.fromEntries(
        Array.from(el.attributes || []).map(attr => [attr.name, attr.value])
      ),
      rect: el.getBoundingClientRect()
    }));
  }, selector);

  console.log(`🔍 Found ${elements.length} elements matching "${selector}":`);
  elements.forEach((el, i) => {
    console.log(`  [${i}] <${el.tag}> ${el.text?.substring(0, 50)}`);
  });

  return elements;
}
