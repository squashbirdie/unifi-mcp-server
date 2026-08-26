/**
 * Navigation Structure Extractor
 * Discovers the API documentation structure from navigation menu
 */

import { waitForAnySelector, waitForStableElement } from '../utils/wait-for-selectors.js';
import { takeScreenshot, debugSnapshot } from '../utils/screenshot-debugger.js';
import { delay } from '../utils/delay.js';

/**
 * Extract navigation structure from API docs page
 * @param {Page} page - Puppeteer page instance
 * @param {Object} options - Extraction options
 * @returns {Promise<Object>} Navigation structure with categories and endpoints
 */
export async function extractNavigationStructure(page, options = {}) {
  console.log('Extracting navigation structure...');

  // Wait for page to be fully loaded
  await page.waitForLoadState?.('networkidle').catch(() => {});
  await delay(2000);

  // Take debug screenshot
  if (options.debug) {
    await takeScreenshot(page, 'navigation_initial');
  }

  // Try multiple selector strategies to find navigation
  const navSelectors = [
    '[data-testid*="nav"]',
    '[data-test*="nav"]',
    'nav',
    '[role="navigation"]',
    'aside',
    '.sidebar',
    '.navigation',
    '.api-nav',
    '.docs-nav'
  ];

  let navElement;
  try {
    const foundSelector = await waitForAnySelector(page, navSelectors, { timeout: 10000 });
    console.log(`✓ Found navigation using selector: ${foundSelector}`);
    navElement = foundSelector;
  } catch (error) {
    console.warn('Could not find navigation with standard selectors');

    // Fallback: Look for any element with lots of links
    navElement = await page.evaluate(() => {
      const candidates = Array.from(document.querySelectorAll('div, aside, nav'));
      const scored = candidates.map(el => ({
        element: el,
        linkCount: el.querySelectorAll('a').length,
        text: el.textContent || ''
      }));

      // Find element with most links that contains API-related text
      const best = scored
        .filter(c => c.linkCount > 5)
        .filter(c => c.text.toLowerCase().includes('api') || c.text.toLowerCase().includes('endpoint'))
        .sort((a, b) => b.linkCount - a.linkCount)[0];

      if (!best) return null;

      // Create a unique selector for this element
      const el = best.element;
      if (el.id) return `#${el.id}`;
      if (el.className) {
        const classes = el.className.split(' ').filter(c => c.length > 0);
        if (classes.length > 0) return `.${classes.join('.')}`;
      }

      return null;
    });

    if (!navElement) {
      throw new Error('Could not locate navigation structure on page');
    }

    console.log(`✓ Found navigation using heuristic: ${navElement}`);
  }

  // Extract navigation structure
  const navigation = await page.evaluate((navSel) => {
    const navContainer = document.querySelector(navSel);
    if (!navContainer) return null;

    // Find all links in navigation
    const links = Array.from(navContainer.querySelectorAll('a'));

    // Group links by category (heuristic: look for headers or grouping elements)
    const structure = {
      categories: [],
      uncategorized: []
    };

    // Try to find category headers
    const headers = Array.from(navContainer.querySelectorAll('h1, h2, h3, h4, h5, h6, [role="heading"]'));

    if (headers.length > 0) {
      // Process each header and its following links
      headers.forEach(header => {
        const categoryName = header.textContent?.trim();
        if (!categoryName) return;

        const category = {
          name: categoryName,
          endpoints: []
        };

        // Find links that come after this header but before the next header
        let currentNode = header.nextElementSibling;
        while (currentNode && !currentNode.matches('h1, h2, h3, h4, h5, h6, [role="heading"]')) {
          const categoryLinks = currentNode.querySelectorAll('a');
          categoryLinks.forEach(link => {
            const href = link.href || '';
            const text = link.textContent?.trim() || '';
            const dataAttrs = Object.fromEntries(
              Array.from(link.attributes)
                .filter(attr => attr.name.startsWith('data-'))
                .map(attr => [attr.name, attr.value])
            );

            category.endpoints.push({
              name: text,
              href: href,
              path: new URL(href).pathname + new URL(href).hash,
              ...dataAttrs
            });
          });

          currentNode = currentNode.nextElementSibling;
        }

        if (category.endpoints.length > 0) {
          structure.categories.push(category);
        }
      });
    } else {
      // No clear headers - try to group by parent elements
      const groupElements = Array.from(navContainer.querySelectorAll('ul, ol, div[class*="group"], div[class*="section"]'));

      groupElements.forEach((group, index) => {
        const groupLinks = Array.from(group.querySelectorAll('a'));
        if (groupLinks.length === 0) return;

        // Try to find a label for this group
        const label = group.querySelector('[class*="label"], [class*="title"], [class*="heading"]')?.textContent?.trim() ||
                      group.previousElementSibling?.textContent?.trim() ||
                      `Category ${index + 1}`;

        const category = {
          name: label,
          endpoints: groupLinks.map(link => ({
            name: link.textContent?.trim() || '',
            href: link.href || '',
            path: link.href ? new URL(link.href).pathname + new URL(link.href).hash : ''
          }))
        };

        structure.categories.push(category);
      });
    }

    // Collect uncategorized links
    const categorizedHrefs = new Set();
    structure.categories.forEach(cat => {
      cat.endpoints.forEach(ep => categorizedHrefs.add(ep.href));
    });

    links.forEach(link => {
      if (!categorizedHrefs.has(link.href)) {
        structure.uncategorized.push({
          name: link.textContent?.trim() || '',
          href: link.href || '',
          path: link.href ? new URL(link.href).pathname + new URL(link.href).hash : ''
        });
      }
    });

    return structure;
  }, navElement);

  if (!navigation || (navigation.categories.length === 0 && navigation.uncategorized.length === 0)) {
    console.error('Failed to extract navigation structure');

    if (options.debug) {
      await debugSnapshot(page, 'navigation_extraction_failed');
    }

    throw new Error('No navigation links found');
  }

  // Summary
  console.log(`✓ Extracted ${navigation.categories.length} categories`);
  navigation.categories.forEach(cat => {
    console.log(`  - ${cat.name}: ${cat.endpoints.length} endpoints`);
  });
  if (navigation.uncategorized.length > 0) {
    console.log(`  - Uncategorized: ${navigation.uncategorized.length} endpoints`);
  }

  return navigation;
}

/**
 * Extract method and path information from endpoint text
 * @param {string} text - Endpoint text (e.g., "GET /api/sites")
 * @returns {Object} {method, path}
 */
export function parseEndpointText(text) {
  const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'];

  let method = null;
  let path = text;

  // Check if text starts with HTTP method
  for (const m of methods) {
    if (text.toUpperCase().startsWith(m)) {
      method = m;
      path = text.substring(m.length).trim();
      break;
    }
  }

  // Extract path if it looks like a URL path
  const pathMatch = path.match(/\/[^\s]*/);
  if (pathMatch) {
    path = pathMatch[0];
  }

  return { method, path };
}
