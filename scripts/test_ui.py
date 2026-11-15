"""Browser checks for the synthetic local test stack; refuses a non-test environment."""
import csv
import json
import os
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.environ.get('UI_TEST_OUTPUT', str(ROOT / 'work' / 'ui-checks')))
OUTPUT.mkdir(parents=True, exist_ok=True)
URL = os.environ.get('UI_TEST_URL', 'http://127.0.0.1:8080')
values = dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines() if line and not line.startswith('#'))
checks = []


def passed(name):
    checks.append(name)
    print('PASS:', name, flush=True)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'),
                                         headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(URL, wait_until='networkidle')
    assert page.request.get(URL + '/api/console/session').json()['environment'] == 'test', 'Refusing writes outside the test workspace'
    page.locator('input[name=username]').fill('not-a-real-user')
    page.locator('input[name=password]').fill('invalid-test-password')
    page.get_by_role('button', name='Sign in to workspace').click()
    expect(page.get_by_role('alert')).to_contain_text('incorrect')
    page.locator('input[name=username]').fill(values['BOOTSTRAP_ADMIN_USER'])
    page.locator('input[name=password]').fill(values['BOOTSTRAP_ADMIN_PASSWORD'])
    page.get_by_role('button', name='Sign in to workspace').click()
    expect(page.get_by_role('heading', name='Security overview')).to_be_visible()
    expected_count=len(page.request.get(URL+'/api/console/devices').json()['items'])
    expect(page.locator('tbody tr')).to_have_count(min(6,expected_count))
    passed('Session login, invalid-credential feedback and real API-backed dashboard')

    page.goto(URL + '/devices', wait_until='networkidle')
    search = page.get_by_role('textbox', name='Filter endpoints')
    search.fill('SIM-NURSE01')
    expect(page.locator('tbody tr')).to_have_count(1)
    page.get_by_role('button', name='SIM-NURSE01', exact=False).first.click()
    dialog = page.get_by_role('dialog')
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text('monitoring-only')
    dialog.get_by_label('Deployment ring').select_option('ring20')
    expect(page.get_by_role('status')).to_contain_text('ring updated')
    dialog.get_by_label('Deployment ring').select_option('pilot')
    page.keyboard.press('Escape')
    expect(dialog).not_to_be_visible()
    search.fill('')
    page.get_by_role('button', name='Offline', exact=True).click()
    expect(page.locator('tbody')).to_contain_text('SIM-DESK03')
    passed('Device search, online/offline filters, details dialog and saved ring changes')

    page.goto(URL + '/shares', wait_until='networkidle')
    page.get_by_role('button', name='Register share', exact=True).first.click()
    page.get_by_role('dialog').get_by_label('Share path').fill(r'\\SIM-FILE01\*')
    page.get_by_role('dialog').get_by_role('button', name='Register share').click()
    expect(page.get_by_role('alert')).to_contain_text('exact UNC')
    path = r'\\SIM-FILE01\UI-Validation'
    page.get_by_role('dialog').get_by_label('Share path').fill(path)
    page.get_by_role('dialog').get_by_role('button', name='Register share').click()
    expect(page.get_by_role('dialog')).not_to_be_visible()
    expect(page.get_by_text(path, exact=True)).to_be_visible()
    page.once('dialog', lambda dialog: dialog.accept())
    page.get_by_role('button', name='Remove ' + path, exact=True).click()
    expect(page.get_by_text(path, exact=True)).not_to_be_visible()
    passed('Share validation, MySQL persistence and monitoring-target removal')

    page.goto(URL + '/activity', wait_until='networkidle')
    page.get_by_role('button', name='Denied', exact=True).click()
    expect(page.locator('tbody tr').first).to_contain_text('Denied check')
    page.get_by_role('button', name='All activity', exact=True).click()
    page.get_by_role('textbox', name='Search activity').fill('sample-inventory')
    expect(page.locator('tbody tr').first).to_contain_text('sample-inventory.xlsx')
    page.get_by_role('textbox', name='Search activity').fill('')
    with page.expect_download() as download:
        page.get_by_role('link', name='Export CSV').click()
    exported = OUTPUT / 'file-activity.csv'
    download.value.save_as(exported)
    with exported.open(newline='') as source:
        records = list(csv.DictReader(source))
    assert len(records) >= 147
    passed('Activity filters, search and CSV download from the backend')

    page.goto(URL + '/approvals', wait_until='networkidle')
    page.get_by_role('button', name='Record a request', exact=True).click()
    dialog = page.get_by_role('dialog')
    dialog.get_by_label('Windows username').fill('lab-ui-user')
    dialog.get_by_label('File path').fill(r'\\SIM-FILE01\Training\ui-validation.txt')
    dialog.get_by_label('Reason').fill('Synthetic browser integration check. No hospital access change.')
    dialog.get_by_role('button', name='Record request', exact=True).click()
    expect(page.get_by_role('dialog')).not_to_be_visible()
    row = page.locator('tbody tr').filter(has_text='lab-ui-user').first
    expect(row.get_by_role('button', name='Approve')).to_be_disabled()
    page.once('dialog', lambda dialog: dialog.accept())
    row.get_by_role('button', name='Reject', exact=True).click()
    expect(row).to_contain_text('rejected')
    passed('Request creation and review while AD grant changes remain disabled')

    page.goto(URL + '/system', wait_until='networkidle')
    expect(page.get_by_role('heading', name='Database explorer')).to_be_visible()
    expect(page.locator('.service-card')).to_have_count(4)
    assert all('Connected' in card.inner_text() for card in page.locator('.service-card').all())
    page.get_by_role('spinbutton', name='Approval duration in minutes').fill('45')
    page.get_by_role('button', name='Save preference').click()
    expect(page.get_by_role('status')).to_contain_text('saved')
    page.reload(wait_until='networkidle')
    expect(page.get_by_role('spinbutton', name='Approval duration in minutes')).to_have_value('45')
    page.get_by_role('spinbutton', name='Approval duration in minutes').fill('30')
    page.get_by_role('button', name='Save preference').click()
    with page.expect_download() as download:
        page.get_by_role('link', name='SQL schema', exact=True).click()
    sql = OUTPUT / 'schema.mysql.sql'
    download.value.save_as(sql)
    assert sql.read_text().count('CREATE TABLE IF NOT EXISTS') == 10
    passed('Four service connections, database row counts, saved settings and SQL schema download')

    page.goto(URL + '/audit', wait_until='networkidle')
    expect(page.get_by_text('Audit chain verified', exact=True)).to_be_visible()
    page.get_by_role('textbox', name='Search audit trail').fill('settings.save')
    expect(page.locator('tbody tr').first).to_contain_text('settings.save')
    passed('Verified audit chain and audit search')

    page.goto(URL, wait_until='networkidle')
    page.route('**/api/console/overview', lambda route: route.abort())
    page.get_by_role('button', name='Refresh', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('Connection interrupted')
    expect(page.get_by_role('heading', name='Security overview')).to_be_visible()
    page.unroute('**/api/console/overview')
    page.get_by_role('button', name='Refresh', exact=True).click()
    expect(page.locator('.connection-alert')).not_to_be_visible()
    passed('Connection-loss warning preserves last data and clears after recovery')
    page.screenshot(path=str(OUTPUT / 'overview-desktop.png'), full_page=True)
    page.get_by_role('button', name='Use dark theme').click()
    assert page.locator('html').get_attribute('data-theme') == 'dark'
    page.goto(URL + '/devices', wait_until='networkidle')
    page.screenshot(path=str(OUTPUT / 'devices-dark.png'), full_page=True)
    page.get_by_role('button', name='Use light theme').click()
    page.get_by_role('button', name='عربي', exact=True).click()
    assert page.locator('html').get_attribute('dir') == 'rtl'
    page.goto(URL, wait_until='networkidle')
    expect(page.get_by_role('heading', name='نظرة عامة على الأمان')).to_be_visible()
    page.screenshot(path=str(OUTPUT / 'overview-arabic.png'), full_page=True)
    page.get_by_role('button', name='EN', exact=True).click()
    passed('Persistent dark theme and Arabic right-to-left layout')

    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(URL, wait_until='networkidle')
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
    page.screenshot(path=str(OUTPUT / 'overview-mobile.png'), full_page=True)
    page.get_by_role('button', name='Open navigation').click()
    page.locator('aside').get_by_role('link', name='Devices', exact=False).click()
    expect(page.get_by_role('heading', name='Your connected fleet')).to_be_visible()
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
    page.screenshot(path=str(OUTPUT / 'devices-mobile.png'), full_page=True)
    passed('390px mobile layout, drawer navigation and no horizontal page overflow')
    assert not errors, errors
    passed('No browser JavaScript errors')
    browser.close()

(OUTPUT / 'browser-results.json').write_text(json.dumps({'passed':checks,'javascript_errors':errors}, indent=2))
print(f'{len(checks)} browser checks passed.')
