/**
 * Schema Extractor
 * Extracts JSON schemas and field tables from API documentation
 */

/**
 * Extract schema from a container element
 * @param {ElementHandle} container - Container element
 * @param {Page} page - Puppeteer page instance
 * @returns {Promise<Object|Array>} Schema or field list
 */
export async function extractSchema(container, page) {
  return await page.evaluate((element) => {
    if (!element) return null;

    // Strategy 1: Look for JSON schema in <pre><code> blocks
    const codeBlocks = element.querySelectorAll('pre code, code pre, pre');
    for (const block of codeBlocks) {
      const code = block.textContent?.trim();
      if (!code) continue;

      // Try to parse as JSON
      try {
        const parsed = JSON.parse(code);
        // Check if it looks like a schema (has properties or fields)
        if (parsed && typeof parsed === 'object') {
          return { type: 'json', data: parsed };
        }
      } catch (e) {
        // Not JSON, continue
      }
    }

    // Strategy 2: Look for field tables
    const tables = element.querySelectorAll('table');
    for (const table of tables) {
      const headers = Array.from(table.querySelectorAll('thead th, tr:first-child th, tr:first-child td'))
        .map(th => th.textContent?.trim().toLowerCase());

      // Check if this looks like a field/parameter table
      if (headers.includes('field') || headers.includes('name') || headers.includes('parameter')) {
        const rows = Array.from(table.querySelectorAll('tbody tr, tr')).slice(headers.length > 0 ? 1 : 0);

        const fields = rows.map(row => {
          const cells = Array.from(row.querySelectorAll('td, th'));
          const field = {};

          headers.forEach((header, index) => {
            if (cells[index]) {
              const value = cells[index].textContent?.trim();

              // Map common header names
              switch (header) {
                case 'field':
                case 'name':
                case 'parameter':
                  field.name = value;
                  break;
                case 'type':
                case 'data type':
                  field.type = value;
                  break;
                case 'description':
                case 'desc':
                  field.description = value;
                  break;
                case 'required':
                case 'req':
                  field.required = value?.toLowerCase() === 'yes' || value?.toLowerCase() === 'true';
                  break;
                case 'default':
                case 'default value':
                  field.default = value;
                  break;
                case 'example':
                case 'sample':
                  field.example = value;
                  break;
                default:
                  field[header] = value;
              }
            }
          });

          return field;
        }).filter(f => f.name); // Only include rows with a name

        if (fields.length > 0) {
          return { type: 'table', data: fields };
        }
      }
    }

    // Strategy 3: Look for definition lists (<dl>)
    const definitionLists = element.querySelectorAll('dl');
    for (const dl of definitionLists) {
      const fields = [];
      const dts = Array.from(dl.querySelectorAll('dt'));
      const dds = Array.from(dl.querySelectorAll('dd'));

      dts.forEach((dt, index) => {
        const name = dt.textContent?.trim();
        const description = dds[index]?.textContent?.trim();

        if (name) {
          // Try to extract type from description (e.g., "string - Description")
          const typeMatch = description?.match(/^(\w+)\s*[-:]\s*(.+)$/);

          fields.push({
            name,
            type: typeMatch ? typeMatch[1] : 'unknown',
            description: typeMatch ? typeMatch[2] : description
          });
        }
      });

      if (fields.length > 0) {
        return { type: 'definition_list', data: fields };
      }
    }

    // Strategy 4: Look for property lists (common in API docs)
    const propertyDivs = element.querySelectorAll('[class*="property"], [class*="field"], [class*="param"]');
    if (propertyDivs.length > 0) {
      const fields = Array.from(propertyDivs).map(div => {
        const nameEl = div.querySelector('[class*="name"], code, strong, b');
        const typeEl = div.querySelector('[class*="type"], .type, em, i');
        const descEl = div.querySelector('[class*="desc"], [class*="description"], p');

        const name = nameEl?.textContent?.trim();
        if (!name) return null;

        return {
          name,
          type: typeEl?.textContent?.trim() || 'unknown',
          description: descEl?.textContent?.trim() || ''
        };
      }).filter(Boolean);

      if (fields.length > 0) {
        return { type: 'property_list', data: fields };
      }
    }

    // No schema found
    return null;
  }, container);
}

/**
 * Extract parameters from documentation section
 * @param {Page} page - Puppeteer page instance
 * @param {string} sectionSelector - Selector for parameter section
 * @returns {Promise<Array>} Array of parameter objects
 */
export async function extractParameters(page, sectionSelector) {
  return await page.evaluate((selector) => {
    const section = document.querySelector(selector);
    if (!section) return [];

    // Look for table
    const table = section.querySelector('table');
    if (table) {
      const headers = Array.from(table.querySelectorAll('thead th, tr:first-child th'))
        .map(th => th.textContent?.trim().toLowerCase());

      const rows = Array.from(table.querySelectorAll('tbody tr, tr')).slice(headers.length > 0 ? 1 : 0);

      return rows.map(row => {
        const cells = Array.from(row.querySelectorAll('td, th'));
        const param = {};

        headers.forEach((header, index) => {
          if (cells[index]) {
            const value = cells[index].textContent?.trim();

            switch (header) {
              case 'parameter':
              case 'name':
                param.name = value;
                break;
              case 'type':
                param.type = value;
                break;
              case 'required':
                param.required = value?.toLowerCase() === 'yes' || value?.toLowerCase() === 'true';
                break;
              case 'description':
              case 'desc':
                param.description = value;
                break;
              case 'default':
                param.default = value;
                break;
            }
          }
        });

        return param;
      }).filter(p => p.name);
    }

    // Look for list items
    const listItems = section.querySelectorAll('li, [class*="param"]');
    if (listItems.length > 0) {
      return Array.from(listItems).map(item => {
        const text = item.textContent?.trim();
        if (!text) return null;

        // Try to parse format like "name (type): description"
        const match = text.match(/^([^\s(]+)\s*\(([^)]+)\)\s*:?\s*(.*)$/);
        if (match) {
          return {
            name: match[1],
            type: match[2],
            description: match[3]
          };
        }

        // Try simpler format like "name: description"
        const simpleMatch = text.match(/^([^\s:]+)\s*:?\s*(.*)$/);
        if (simpleMatch) {
          return {
            name: simpleMatch[1],
            type: 'unknown',
            description: simpleMatch[2]
          };
        }

        return null;
      }).filter(Boolean);
    }

    return [];
  }, sectionSelector);
}

/**
 * Extract code examples from documentation
 * @param {Page} page - Puppeteer page instance
 * @param {string} sectionSelector - Selector for example section
 * @returns {Promise<Object>} {request, response} examples
 */
export async function extractExamples(page, sectionSelector) {
  return await page.evaluate((selector) => {
    const section = document.querySelector(selector);
    if (!section) return { request: null, response: null };

    const examples = { request: null, response: null };

    // Look for labeled code blocks
    const codeBlocks = section.querySelectorAll('pre code, pre');

    codeBlocks.forEach(block => {
      const code = block.textContent?.trim();
      if (!code) return;

      // Check surrounding text for labels
      let label = '';
      if (block.previousElementSibling) {
        label = block.previousElementSibling.textContent?.toLowerCase() || '';
      }
      if (!label && block.parentElement?.previousElementSibling) {
        label = block.parentElement.previousElementSibling.textContent?.toLowerCase() || '';
      }

      // Determine if it's request or response
      if (label.includes('request') || label.includes('payload') || label.includes('body')) {
        examples.request = code;
      } else if (label.includes('response') || label.includes('output') || label.includes('result')) {
        examples.response = code;
      } else if (!examples.request && (code.includes('"method"') || code.includes('POST') || code.includes('GET'))) {
        // Heuristic: looks like a request
        examples.request = code;
      } else if (!examples.response && (code.includes('"status"') || code.includes('"data"'))) {
        // Heuristic: looks like a response
        examples.response = code;
      }
    });

    // Try to parse JSON examples
    if (examples.request) {
      try {
        const parsed = JSON.parse(examples.request);
        examples.request = JSON.stringify(parsed, null, 2);
      } catch (e) {
        // Keep as string
      }
    }

    if (examples.response) {
      try {
        const parsed = JSON.parse(examples.response);
        examples.response = JSON.stringify(parsed, null, 2);
      } catch (e) {
        // Keep as string
      }
    }

    return examples;
  }, sectionSelector);
}
