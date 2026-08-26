#!/usr/bin/env node
/**
 * Debug script to inspect UniFi login page structure
 * Run this to see what selectors are actually available
 */

import puppeteer from 'puppeteer';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import { delay } from '../utils/delay.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function debugLoginPage() {
  console.log('🔍 Inspecting UniFi login page structure...\n');

  const browser = await puppeteer.launch({
    headless: false,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });

  try {
    // Navigate to API docs (will redirect to login)
    console.log('Navigating to UniFi portal...');
    await page.goto('https://unifi.ui.com/settings/api-docs', {
      waitUntil: 'networkidle2',
      timeout: 30000
    });

    // Wait for page to settle
    await delay(3000);

    console.log(`Current URL: ${page.url()}\n`);

    // Take screenshot
    const screenshotPath = path.join(__dirname, '../../screenshots/login-page.png');
    await fs.mkdir(path.dirname(screenshotPath), { recursive: true });
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`✓ Screenshot saved: ${screenshotPath}\n`);

    // Inspect all input fields
    const inputs = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('input')).map((input, index) => ({
        index,
        type: input.type,
        name: input.name,
        id: input.id,
        placeholder: input.placeholder,
        className: input.className,
        value: input.value,
        ariaLabel: input.getAttribute('aria-label'),
        autocomplete: input.autocomplete,
        visible: input.offsetParent !== null
      }));
    });

    console.log('📝 Input Fields Found:\n');
    inputs.forEach(input => {
      console.log(`[${input.index}] ${input.type}${input.visible ? '' : ' (HIDDEN)'}`);
      if (input.id) console.log(`    id="${input.id}"`);
      if (input.name) console.log(`    name="${input.name}"`);
      if (input.placeholder) console.log(`    placeholder="${input.placeholder}"`);
      if (input.className) console.log(`    class="${input.className}"`);
      if (input.ariaLabel) console.log(`    aria-label="${input.ariaLabel}"`);
      if (input.autocomplete) console.log(`    autocomplete="${input.autocomplete}"`);
      console.log();
    });

    // Inspect all buttons
    const buttons = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('button, input[type="submit"]')).map((btn, index) => ({
        index,
        tag: btn.tagName.toLowerCase(),
        type: btn.type,
        text: btn.textContent?.trim().substring(0, 50),
        id: btn.id,
        className: btn.className,
        ariaLabel: btn.getAttribute('aria-label'),
        visible: btn.offsetParent !== null
      }));
    });

    console.log('🔘 Buttons Found:\n');
    buttons.forEach(btn => {
      console.log(`[${btn.index}] <${btn.tag}>${btn.visible ? '' : ' (HIDDEN)'}`);
      if (btn.text) console.log(`    text="${btn.text}"`);
      if (btn.type) console.log(`    type="${btn.type}"`);
      if (btn.id) console.log(`    id="${btn.id}"`);
      if (btn.className) console.log(`    class="${btn.className}"`);
      if (btn.ariaLabel) console.log(`    aria-label="${btn.ariaLabel}"`);
      console.log();
    });

    // Save full HTML
    const html = await page.content();
    const htmlPath = path.join(__dirname, '../../screenshots/login-page.html');
    await fs.writeFile(htmlPath, html);
    console.log(`✓ HTML saved: ${htmlPath}\n`);

    // Look for forms
    const forms = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('form')).map((form, index) => ({
        index,
        action: form.action,
        method: form.method,
        id: form.id,
        className: form.className,
        inputCount: form.querySelectorAll('input').length
      }));
    });

    console.log('📋 Forms Found:\n');
    forms.forEach(form => {
      console.log(`[${form.index}] <form>`);
      if (form.action) console.log(`    action="${form.action}"`);
      if (form.method) console.log(`    method="${form.method}"`);
      if (form.id) console.log(`    id="${form.id}"`);
      if (form.className) console.log(`    class="${form.className}"`);
      console.log(`    inputs: ${form.inputCount}`);
      console.log();
    });

    console.log('\n✅ Inspection complete!');
    console.log('\nNext steps:');
    console.log('1. Review the output above to find the correct selectors');
    console.log('2. Check the screenshot: screenshots/login-page.png');
    console.log('3. Check the HTML: screenshots/login-page.html');
    console.log('\nPress Ctrl+C when done inspecting the browser window...\n');

    // Keep browser open for manual inspection
    await new Promise(() => {}); // Wait forever

  } catch (error) {
    console.error('Error:', error.message);
    console.error(error.stack);
  }
}

debugLoginPage();
