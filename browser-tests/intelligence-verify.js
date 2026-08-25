/**
 * intelligence-verify.js
 * Headless Chromium verification of the Spotify Intelligence page.
 *
 * Opens http://127.0.0.1:5000/Intelligence.dc.html in headless Chromium,
 * waits for the page's own JS (loadIntelligence via refreshAll on DOMContentLoaded)
 * to populate the DOM from /api/analytics, then asserts the rendered values
 * match the live API response.
 *
 * Why localhost instead of ngrok: the dashboard is local and the in-page JS
 * references relative /api/* paths that resolve to 127.0.0.1:5000 — no bot-
 * detection or interstitial risk. The ngrok tunnel is a separate public-facing
 * concern; this script verifies the dashboard itself.
 *
 * Usage:  node intelligence-verify.js
 * Exit:   0 = all checks pass, 1 = any check fails
 */

const { chromium } = require('./node_modules/playwright');
const fs = require('fs');

const DASHBOARD_URL = 'http://127.0.0.1:5000/Intelligence.dc.html';
const API_URL       = 'http://127.0.0.1:5000/api/analytics';
const TIMEOUT_MS    = 30_000;
const ARCHETYPE_WAIT_MS = 10_000; // generous: page JS + API round-trip

const RESULTS = { ok: true, checks: [] };

function record(name, ok, detail) {
  RESULTS.checks.push({ name, ok, detail });
  if (!ok) RESULTS.ok = false;
  console.log(ok ? '✅' : '❌', name, detail || '');
}

const EXECUTABLE_PATH = 'C:\\Users\\ismai\\AppData\\Local\\ms-playwright\\chromium-1234\\chrome-win64\\chrome.exe';

(async () => {
  // --- Pre-flight: verify dashboard is alive ---
  let apiData;
  try {
    const res = await fetch(API_URL);
    if (!res.ok) throw new Error(`HTTP ${res.status()}`);
    apiData = await res.json();
  } catch (err) {
    record('Pre-flight API', false, `dashboard not reachable: ${err.message}`);
    process.exit(1);
  }
  const arch = apiData.listener_archetype || {};
  record('Pre-flight API', true,
    `archetype=${arch.archetype || 'null'} discovery_rate=${arch.discovery_rate || 'null'}% genres=${arch.genre_diversity?.genre_count || 'null'}`);

  // --- Launch headless Chromium ---
  let browser;
  try {
    browser = await chromium.launch({
      headless: true,
      executablePath: EXECUTABLE_PATH,
      args: [
        '--no-sandbox',
        '--disable-gpu',
        '--disable-dev-shm-usage',
        '--disable-extensions',
        '--disable-background-networking',
      ],
    });
  } catch (err) {
    record('Browser launch', false, err.message);
    process.exit(1);
  }

  const page = await browser.newPage();
  const consoleMsgs = [];
  page.on('console', msg => consoleMsgs.push({ type: msg.type(), text: msg.text() }));
  page.on('pageerror', err => consoleMsgs.push({ type: 'pageerror', text: err.message }));

  // --- Navigate to the Intelligence page ---
  let navOk = false;
  try {
    const response = await page.goto(DASHBOARD_URL, {
      waitUntil: 'domcontentloaded',
      timeout: TIMEOUT_MS,
    });
    navOk = response.ok();
  } catch (err) {
    record('Page navigation', false, `goto failed: ${err.message}`);
  }
  record('Page navigation', navOk, navOk ? `title="${await page.title()}"` : 'FAILED');

  if (!navOk) {
    await browser.close();
    process.exit(1);
  }

  // --- Wait for the page's JS to populate the archetype.
  // The template ships with <h2 class="archetype-name">—</h2> (placeholder).
  // loadIntelligence() fetches /api/analytics and calls renderArchetype()
  // which sets archetype-name.textContent = analytics.listener_archetype?.archetype.
  // We wait for the text to change from "—" to something substantive.
  let archetypePopulated = false;
  try {
    await page.waitForFunction(
      () => {
        const el = document.querySelector('.archetype-name');
        if (!el) return false;
        const t = (el.textContent || '').trim();
        return t.length > 1 && t !== '—';
      },
      { timeout: ARCHETYPE_WAIT_MS }
    );
    archetypePopulated = true;
  } catch (err) {
    // Timeout — capture what we have for diagnostics
    const el = await page.$eval('.archetype-name', e => e.textContent.trim()).catch(() => '(not found)');
    record('Archetype renders (non-placeholder)', false,
      `waitForFunction timed out after ${ARCHETYPE_WAIT_MS}ms; current text="${el}"`);
  }

  // --- Read all DOM values ---
  const archetypeName = await page.$eval('.archetype-name', e => (e.textContent||'').trim())
    .catch(() => '(not found)');
  const archetypeDesc = await page.$eval('.archetype-description', e => (e.textContent||'').trim())
    .catch(() => '(not found)');

  record('Archetype name rendered', archetypeName !== '—' && archetypeName.length > 1,
    `text="${archetypeName}" (populated=${archetypePopulated})`);
  record('Archetype description renders', archetypeDesc !== '—' && archetypeDesc.length > 1,
    `text="${archetypeDesc}"`);

  // Insight cards
  const insightTexts = await page.$$eval('.insight-card', els =>
    els.map(el => (el.textContent || '').trim()).filter(t => t.length > 0 && t !== '—')
  ).catch(() => []);
  record('Insight cards populated', insightTexts.length >= 1,
    `${insightTexts.length} insight card(s): ${insightTexts.slice(0,3).map(t => t.slice(0,60)).join(' | ')}`);

  // Recommendation cards
  const recNames = await page.$$eval('.recommendation-card .recommendation-name, .recommendation-card h3',
    els => els.map(el => (el.textContent || '').trim()).filter(n => n.length > 0 && n !== '—')
  ).catch(() => []);
  record('Recommendation cards populated', recNames.length >= 1,
    `${recNames.length} recommendation card(s): ${recNames.slice(0,3).join(', ')}`);

  // Anomaly cards — 0 findings is valid (API may return empty)
  const anomalyTitles = await page.$$eval('.anomaly-card .anomaly-title',
    els => els.map(el => (el.textContent || '').trim()).filter(t => t.length > 0 && t !== '—')
  ).catch(() => []);
  const anomalyApiCount = apiData.anomalies?.total_findings || 0;
  record('Anomaly cards match API', anomalyTitles.length === anomalyApiCount,
    `${anomalyTitles.length} anomaly card(s) rendered vs API total_findings=${anomalyApiCount}`);

  // --- Cross-check rendered archetype name vs API ---
  const apiArchetype = arch.archetype || '(no archetype)';
  const nameMatch = archetypeName.toLowerCase().includes(apiArchetype.toLowerCase()) ||
                    apiArchetype.toLowerCase().includes(archetypeName.toLowerCase());
  record('Archetype name matches API', nameMatch,
    `rendered="${archetypeName}" vs API="${apiArchetype}"`);

  // --- Cross-check discovery rate appears in page text ---
  const pageText = await page.$eval('body', e => (e.innerText || '').trim()).catch(() => '');
  const discoveryPct = arch.discovery_rate;
  if (discoveryPct != null) {
    const present = pageText.includes(String(discoveryPct));
    record('Discovery rate visible in page text', present,
      `${discoveryPct}% ${present ? 'found' : 'NOT found'} in page body text`);
  }

  // --- Cross-check genre count appears in page text ---
  const genreCount = arch.genre_diversity?.genre_count;
  if (genreCount != null) {
    const present = pageText.includes(String(genreCount));
    record('Genre count visible in page text', present,
      `${genreCount} genres ${present ? 'found' : 'NOT found'} in page body text`);
  }

  // --- Console errors ---
  const errors = consoleMsgs.filter(m => m.type === 'pageerror');
  if (errors.length > 0) {
    record('No JS page errors', false, errors.map(e => e.text).join('; '));
  } else {
    record('No JS page errors', true, '');
  }

  // --- Screenshot ---
  const screenshotPath = 'intelligence-verify.png';
  await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => {});
  record('Screenshot saved', fs.existsSync(screenshotPath), screenshotPath);

  await browser.close();

  // --- Summary ---
  console.log('\n--- RESULT ---');
  console.log(JSON.stringify(RESULTS, null, 2));
  process.exit(RESULTS.ok ? 0 : 1);
})().catch(err => {
  console.error('Fatal:', err);
  if (browser) browser.close();
  process.exit(1);
});
