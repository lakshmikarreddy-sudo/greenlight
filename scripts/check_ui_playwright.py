"""
Headless UI verification using Playwright (Python).
Usage:
  pip install playwright
  playwright install chromium
  python scripts/check_ui_playwright.py

The script will:
 - open http://127.0.0.1:8889
 - take a screenshot of the home page (before analysis)
 - verify the sample dropdown is visible and contains target options
 - select 'brooklyn-drone-chase' and click Analyze
 - wait for the production brief (SSE brief) to appear and take a screenshot
 - print pass/fail diagnostics

Note: Run this locally where Chrome/Chromium can be installed. This repo environment does not include Playwright.
"""
import asyncio
from playwright.async_api import async_playwright

URL = 'http://127.0.0.1:8889'

async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width':1200,'height':900})
        page = await context.new_page()
        await page.goto(URL)
        await page.wait_for_load_state('networkidle')
        await page.screenshot(path='ui_before.png')
        # Check sample select
        sel = await page.query_selector('#sampleSelect')
        if not sel:
            print('FAIL: #sampleSelect not found')
            await browser.close(); return 1
        visible = await sel.is_visible()
        if not visible:
            print('FAIL: #sampleSelect not visible')
            await browser.close(); return 1
        options = await page.eval_on_selector_all('#sampleSelect option', 'els => els.map(e => ({v:e.value,t:e.text}))')
        print('Options:', options)
        required = ['brooklyn-drone-chase','svalbard-arctic','savannah-pyro']
        missing = [r for r in required if not any(o['v'] == r for o in options)]
        if missing:
            print('FAIL: Missing options', missing)
            await browser.close(); return 1
        # select brooklyn and click analyze
        await page.select_option('#sampleSelect', 'brooklyn-drone-chase')
        await page.click('#analyzeBtn')
        # wait for brief to appear (briefSummary change)
        try:
            await page.wait_for_selector('#briefSummary .status-pill, .production-decision .status-pill', timeout=20000)
        except Exception as e:
            print('FAIL: production brief did not appear', e)
            await page.screenshot(path='ui_error.png')
            await browser.close(); return 1
        await page.screenshot(path='ui_after.png')
        print('PASS: UI flow completed; screenshots ui_before.png and ui_after.png saved')
        await browser.close();
        return 0

if __name__=='__main__':
    asyncio.run(run())
