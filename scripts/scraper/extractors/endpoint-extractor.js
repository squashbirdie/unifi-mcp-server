/**
 * Endpoint Detail Extractor
 * Extracts detailed information for each API endpoint
 */

import { waitForStableElement, retryWithBackoff } from '../utils/wait-for-selectors.js';
import { takeScreenshot, debugSnapshot } from '../utils/screenshot-debugger.js';
import { extractSchema, extractParameters, extractExamples } from './schema-extractor.js';
import { delay } from '../utils/delay.js';

/**
 * Extract details for a single endpoint
 * @param {Page} page - Puppeteer page instance
 * @param {Object} endpoint - Endpoint info from navigation {name, href, path}
 * @param {Object} options - Extraction options
 * @returns {Promise<Object>} Endpoint details
 */
export async function extractEndpointDetails(page, endpoint, options = {}) {
  console.log(`Extracting: ${endpoint.name}`);

  // Navigate to endpoint page
  try {
    await page.goto(endpoint.href, {
      waitUntil: 'networkidle2',
      timeout: 30000
    });
  } catch (error) {
    console.error(`Failed to navigate to ${endpoint.href}:`, error.message);
    return null;
  }

  // Wait for content to load
  await delay(1000);

  // Take screenshot if debugging
  if (options.debug) {
    await takeScreenshot(page, `endpoint_${endpoint.name.replace(/[^a-z0-9]/gi, '_')}`);
  }

  // Extract endpoint details
  const details = await page.evaluate(() => {
    // Helper: Get text content from selectors
    const getText = (selectors) => {
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        if (el) return el.textContent?.trim();
      }
      return null;
    };

    // Helper: Get all matching elements
    const getElements = (selectors) => {
      for (const sel of selectors) {
        const elements = Array.from(document.querySelectorAll(sel));
        if (elements.length > 0) return elements;
      }
      return [];
    };

    // Extract HTTP method
    const method = getText([
      '[data-method]',
      '.http-method',
      '.method',
      '[class*="method"]',
      'code:first-of-type',
      'span.badge:first-of-type'
    ]) || null;

    // Extract endpoint path
    const path = getText([
      '[data-path]',
      '.endpoint-path',
      '.path',
      '[class*="path"]',
      'code.path',
      'code:nth-of-type(2)'
    ]) || null;

    // Extract description
    const description = getText([
      '[data-description]',
      '.endpoint-description',
      '.description',
      '[class*="description"]',
      'p:first-of-type',
      '.lead'
    ]) || null;

    // Find sections (parameters, request body, response, examples)
    const sections = {
      pathParams: null,
      queryParams: null,
      requestBody: null,
      responseBody: null,
      examples: null
    };

    // Look for sections by headers
    const headers = Array.from(document.querySelectorAll('h2, h3, h4, h5, h6, [role="heading"]'));

    headers.forEach(header => {
      const headerText = header.textContent?.toLowerCase() || '';
      let sectionType = null;

      if (headerText.includes('path') && (headerText.includes('param') || headerText.includes('variable'))) {
        sectionType = 'pathParams';
      } else if (headerText.includes('query') && headerText.includes('param')) {
        sectionType = 'queryParams';
      } else if (headerText.includes('request') && (headerText.includes('body') || headerText.includes('payload'))) {
        sectionType = 'requestBody';
      } else if (headerText.includes('response') && (headerText.includes('body') || headerText.includes('payload'))) {
        sectionType = 'responseBody';
      } else if (headerText.includes('example')) {
        sectionType = 'examples';
      }

      if (sectionType) {
        // Find content until next header
        let content = '';
        let currentNode = header.nextElementSibling;

        while (currentNode && !currentNode.matches('h1, h2, h3, h4, h5, h6, [role="heading"]')) {
          content += currentNode.outerHTML || '';
          currentNode = currentNode.nextElementSibling;
        }

        // Create a temporary container to query
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = content;

        // Store reference to the section
        if (!sections[sectionType]) {
          sections[sectionType] = tempDiv;
        }
      }
    });

    // Return extracted data along with section HTML for further processing
    return {
      method: method?.toUpperCase(),
      path,
      description,
      sectionsHTML: {
        pathParams: sections.pathParams?.innerHTML || null,
        queryParams: sections.queryParams?.innerHTML || null,
        requestBody: sections.requestBody?.innerHTML || null,
        responseBody: sections.responseBody?.innerHTML || null,
        examples: sections.examples?.innerHTML || null
      }
    };
  });

  // Process sections with schema extractor
  const processedDetails = {
    method: details.method,
    path: details.path,
    description: details.description,
    pathParameters: [],
    queryParameters: [],
    requestBody: null,
    responseBody: null,
    examples: { request: null, response: null }
  };

  // Extract path parameters
  if (details.sectionsHTML.pathParams) {
    processedDetails.pathParameters = await extractParametersFromHTML(
      page,
      details.sectionsHTML.pathParams
    );
  }

  // Extract query parameters
  if (details.sectionsHTML.queryParams) {
    processedDetails.queryParameters = await extractParametersFromHTML(
      page,
      details.sectionsHTML.queryParams
    );
  }

  // Extract request body schema
  if (details.sectionsHTML.requestBody) {
    processedDetails.requestBody = await extractSchemaFromHTML(
      page,
      details.sectionsHTML.requestBody
    );
  }

  // Extract response body schema
  if (details.sectionsHTML.responseBody) {
    processedDetails.responseBody = await extractSchemaFromHTML(
      page,
      details.sectionsHTML.responseBody
    );
  }

  // Extract examples
  if (details.sectionsHTML.examples) {
    processedDetails.examples = await extractExamplesFromHTML(
      page,
      details.sectionsHTML.examples
    );
  }

  return processedDetails;
}

/**
 * Extract parameters from HTML string
 * @param {Page} page - Puppeteer page instance
 * @param {string} html - HTML content
 * @returns {Promise<Array>}
 */
async function extractParametersFromHTML(page, html) {
  return await page.evaluate((htmlContent) => {
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = htmlContent;

    // Look for table
    const table = tempDiv.querySelector('table');
    if (table) {
      const headers = Array.from(table.querySelectorAll('thead th, tr:first-child th'))
        .map(th => th.textContent?.trim().toLowerCase());

      const rows = Array.from(table.querySelectorAll('tbody tr, tr')).slice(1);

      return rows.map(row => {
        const cells = Array.from(row.querySelectorAll('td'));
        const param = {};

        headers.forEach((header, index) => {
          const value = cells[index]?.textContent?.trim();
          if (!value) return;

          if (header.includes('name') || header.includes('parameter')) {
            param.name = value;
          } else if (header.includes('type')) {
            param.type = value;
          } else if (header.includes('required')) {
            param.required = value.toLowerCase() === 'yes' || value.toLowerCase() === 'true';
          } else if (header.includes('description')) {
            param.description = value;
          } else if (header.includes('default')) {
            param.default = value;
          }
        });

        return param.name ? param : null;
      }).filter(Boolean);
    }

    return [];
  }, html);
}

/**
 * Extract schema from HTML string
 * @param {Page} page - Puppeteer page instance
 * @param {string} html - HTML content
 * @returns {Promise<Object|Array>}
 */
async function extractSchemaFromHTML(page, html) {
  return await page.evaluate((htmlContent) => {
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = htmlContent;

    // Look for JSON in code blocks
    const codeBlocks = tempDiv.querySelectorAll('pre code, code pre, pre');
    for (const block of codeBlocks) {
      try {
        const parsed = JSON.parse(block.textContent?.trim() || '');
        return parsed;
      } catch (e) {
        // Not JSON
      }
    }

    // Look for tables
    const table = tempDiv.querySelector('table');
    if (table) {
      const headers = Array.from(table.querySelectorAll('thead th, tr:first-child th'))
        .map(th => th.textContent?.trim().toLowerCase());

      const rows = Array.from(table.querySelectorAll('tbody tr, tr')).slice(1);

      const fields = rows.map(row => {
        const cells = Array.from(row.querySelectorAll('td'));
        const field = {};

        headers.forEach((header, index) => {
          const value = cells[index]?.textContent?.trim();
          if (!value) return;

          if (header.includes('field') || header.includes('name')) {
            field.name = value;
          } else if (header.includes('type')) {
            field.type = value;
          } else if (header.includes('description')) {
            field.description = value;
          } else if (header.includes('required')) {
            field.required = value.toLowerCase() === 'yes' || value.toLowerCase() === 'true';
          }
        });

        return field.name ? field : null;
      }).filter(Boolean);

      return fields.length > 0 ? fields : null;
    }

    return null;
  }, html);
}

/**
 * Extract examples from HTML string
 * @param {Page} page - Puppeteer page instance
 * @param {string} html - HTML content
 * @returns {Promise<Object>}
 */
async function extractExamplesFromHTML(page, html) {
  return await page.evaluate((htmlContent) => {
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = htmlContent;

    const examples = { request: null, response: null };

    const codeBlocks = tempDiv.querySelectorAll('pre code, pre');

    codeBlocks.forEach((block, index) => {
      const code = block.textContent?.trim();
      if (!code) return;

      // Check labels
      const label = block.previousElementSibling?.textContent?.toLowerCase() || '';

      if (label.includes('request')) {
        examples.request = code;
      } else if (label.includes('response')) {
        examples.response = code;
      } else if (index === 0) {
        examples.request = code;
      } else if (index === 1) {
        examples.response = code;
      }
    });

    return examples;
  }, html);
}

/**
 * Extract all endpoints with retry logic
 * @param {Page} page - Puppeteer page instance
 * @param {Array} endpoints - Array of endpoint info
 * @param {Object} options - Extraction options
 * @returns {Promise<Array>} Array of extracted endpoint details
 */
export async function extractAllEndpoints(page, endpoints, options = {}) {
  const results = [];
  const maxConcurrent = options.maxConcurrent || 1; // Process one at a time by default

  for (let i = 0; i < endpoints.length; i += maxConcurrent) {
    const batch = endpoints.slice(i, i + maxConcurrent);

    const batchResults = await Promise.all(
      batch.map(endpoint =>
        retryWithBackoff(
          () => extractEndpointDetails(page, endpoint, options),
          {
            maxRetries: 3,
            initialDelay: 1000,
            onRetry: (error, attempt) => {
              console.log(`Retry ${attempt} for ${endpoint.name}: ${error.message}`);
            }
          }
        ).catch(error => {
          console.error(`Failed to extract ${endpoint.name}:`, error.message);
          return null;
        })
      )
    );

    results.push(...batchResults.filter(Boolean));

    // Add delay between batches
    if (i + maxConcurrent < endpoints.length) {
      await delay(1000);
    }
  }

  return results;
}
