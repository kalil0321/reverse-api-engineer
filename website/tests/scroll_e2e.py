"""Real-browser regression checks against a served production export.

Run: uv run --extra manual python website/tests/scroll_e2e.py URL EXPORT_DIR
Install browsers first: uv run --extra manual playwright install chromium firefox webkit
"""
import json
import sys
from contextlib import closing
from pathlib import Path

from playwright.sync_api import sync_playwright

base_url, export_dir = sys.argv[1:]
docs_dir = Path(export_dir, 'docs')
assert docs_dir.is_dir(), f'Missing docs export: {docs_dir}'
docs_routes = sorted('/' + str(p.parent.relative_to(export_dir)) + '/' for p in docs_dir.rglob('index.html'))
assert len(docs_routes) > 1, f'Expected docs index and content pages: {docs_routes}'
routes = ['/'] + docs_routes
results = []
with sync_playwright() as playwright:
    for engine in ['chromium', 'firefox', 'webkit']:
        with closing(getattr(playwright, engine).launch()) as browser:
            for width, height in [(1280, 800), (390, 844)]:
                with closing(browser.new_context(viewport={'width': width, 'height': height})) as context:
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    for route in routes:
                        print(engine, width, route, file=sys.stderr, flush=True)
                        response = page.goto(base_url + route, wait_until='domcontentloaded')
                        assert response.status == 200, (engine, route, response.status)
                        assert page.locator('h1').first.inner_text().strip(), route
                        header = page.locator('header').first
                        for delta in [3000, -1800, 8000, -9000]:
                            before = page.evaluate('scrollY')
                            maximum = page.evaluate('Math.max(0, document.documentElement.scrollHeight - innerHeight)')
                            can_move = (delta > 0 and before < maximum - 1) or (delta < 0 and before > 1)
                            page.mouse.wheel(0, delta)
                            # Sample frames during the scroll, not just after it settles.
                            positions = page.evaluate('''async () => {
                                const samples = [];
                                for (let i = 0; i < 12; i++) {
                                    await new Promise(requestAnimationFrame);
                                    const r = document.querySelector('header').getBoundingClientRect();
                                    samples.push({top:r.top, bottom:r.bottom, left:r.left, right:r.right, y:scrollY});
                                }
                                return samples;
                            }''')
                            if can_move:
                                assert any(abs(p['y'] - before) > 1 for p in positions), (engine, route, delta, 'wheel did not scroll', before, positions)
                            assert all(abs(p['top']) < 1 and p['bottom'] > 40 and p['left'] >= -1 and p['right'] <= width + 1 for p in positions), (engine, route, positions)
                        # End of document and immediate reversal must not push the nav away.
                        for y in [100000, 0]:
                            page.evaluate('(y) => scrollTo(0, y)', y)
                            assert abs(header.bounding_box()['y']) < 1, (engine, route, y)
                        assert not errors, (engine, route, errors)
                        results.append({'engine': engine, 'width': width, 'route': route, 'status': 'pass'})
                    # Exercise real mobile navigation and theme switching after scroll.
                    page.goto(base_url + '/docs/', wait_until='domcontentloaded')
                    if width < 1024:
                        page.locator('summary').click()
                        page.get_by_role('link', name='Installation', exact=True).click()
                        page.wait_for_url('**/docs/installation/')
                    theme = page.get_by_role('button', name='Switch to', exact=False)
                    previous = page.locator('html').get_attribute('class')
                    theme.click()
                    page.wait_for_function('(previous) => document.documentElement.className !== previous', arg=previous)
                    page.screenshot(path=f'/tmp/rae-header-{engine}-{width}.png')
                    assert not errors, (engine, errors)
print(json.dumps({'passed': len(results), 'results': results}, indent=2))
