"""
Playwright UI review script — requires the Flask app to be running on port 5000.
Run: python tests/ui_review.py
"""

import sys
from playwright.sync_api import sync_playwright


def check(condition: bool, msg: str):
    status = "✅" if condition else "❌"
    print(f"{status} {msg}")
    return condition


all_ok = True
BASE = "http://127.0.0.1:5000"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()

    # ── Home page ──
    page.goto(BASE, wait_until="domcontentloaded")
    page.wait_for_selector("#drop-zone", timeout=10000)
    print("\n=== Home Page ===")
    all_ok &= check("N26 Tax Calculator" in page.title(), "Page title correct")
    all_ok &= check(page.locator("#drop-zone").is_visible(), "Drop zone visible")
    all_ok &= check(page.locator("text=Drag and drop PDF files here").is_visible(),
                    "Drop zone text present")
    all_ok &= check(page.locator("#cleanup-btn").is_visible(), "Cleanup button visible")
    all_ok &= check(not page.locator("#file-list").is_visible(), "File list hidden initially")
    all_ok &= check(not page.locator("#progress-container").is_visible(), "Progress hidden initially")
    all_ok &= check(page.locator("text=Quick Instructions").is_visible(), "Quick instructions visible")
    all_ok &= check(page.locator("nav").is_visible(), "Navigation bar visible")
    all_ok &= check(page.locator("nav >> text=Home").is_visible(), "Home link in nav")
    all_ok &= check(page.locator("nav >> text=History").is_visible(), "History link in nav")
    all_ok &= check(page.locator("nav >> text=Help").is_visible(), "Help link in nav")

    # ── File selection interaction ──
    print("\n=== File Selection ===")
    page.evaluate("""
        document.getElementById('file-input').files = 
            new DataTransfer().files;
        const input = document.getElementById('file-input');
        const dt = new DataTransfer();
        dt.items.add(new File(['dummy'], 'buy_order_test.pdf', {type:'application/pdf'}));
        input.files = dt.files;
        input.dispatchEvent(new Event('change', {bubbles: true}));
    """)
    page.wait_for_timeout(500)
    all_ok &= check(page.locator("#file-list").is_visible(), "File list appears after selection")
    file_count = page.locator("#file-count").text_content()
    all_ok &= check(file_count.strip() == "1", f"File count shows 1 (got '{file_count}')")

    page.locator("button[data-bs-target='#collapseFiles']").click()
    page.wait_for_timeout(500)
    page.locator("button:has-text('Remove')").click()
    page.wait_for_timeout(300)
    all_ok &= check(not page.locator("#file-list").is_visible(), "File list hides after removal")

    # ── Help page ──
    print("\n=== Help Page ===")
    page.goto(f"{BASE}/help", wait_until="domcontentloaded")
    page.wait_for_selector("h2", timeout=10000)
    all_ok &= check(page.locator("text=Getting Started").is_visible(), "Getting Started section")
    all_ok &= check(page.locator("text=Understanding the Report").is_visible(), "Understanding Report section")
    all_ok &= check(page.locator("text=Troubleshooting").is_visible(), "Troubleshooting section")
    all_ok &= check(page.locator("text=Before Filing").is_visible(), "Before Filing section")
    all_ok &= check(page.locator("a:has-text('Start Analysis')").is_visible(), "Start Analysis button")

    # ── History page ──
    print("\n=== History Page ===")
    page.goto(f"{BASE}/history", wait_until="domcontentloaded")
    page.wait_for_selector("h2", timeout=10000)
    if page.locator("text=No previous results found").is_visible():
        all_ok &= check(True, "Empty state shows 'no results' message")
        all_ok &= check(page.locator("a:has-text('Start a new analysis')").is_visible(), "Link to start analysis")

    # ── Error state: invalid session ──
    print("\n=== Error States ===")
    page.goto(f"{BASE}/results/invalid-session", wait_until="domcontentloaded")
    page.wait_for_selector("#drop-zone", timeout=10000)
    all_ok &= check(BASE in page.url, f"Invalid session redirects to index (current: {page.url})")

    # ── API session init ──
    print("\n=== API ===")
    resp = page.request.post(f"{BASE}/api/session/init")
    data = resp.json()
    all_ok &= check(data["status"] == "success", f"API init returns session_id")

    # ── Responsive check ──
    print("\n=== Responsive ===")
    context2 = browser.new_context(viewport={"width": 375, "height": 812})
    page2 = context2.new_page()
    page2.goto(BASE, wait_until="domcontentloaded")
    page2.wait_for_selector("#drop-zone", timeout=10000)
    all_ok &= check(page2.locator("#drop-zone").is_visible(), "Mobile: drop zone visible")
    body_width = page2.evaluate("document.body.scrollWidth")
    viewport_width = page2.evaluate("window.innerWidth")
    all_ok &= check(body_width <= viewport_width + 5,
                    f"Mobile: no horizontal scroll ({body_width}px <= {viewport_width}px)")
    page2.close()
    context2.close()

    browser.close()

print(f"\n{'='*40}")
print(f"{'All checks passed!' if all_ok else 'Some checks FAILED!'}")
sys.exit(0 if all_ok else 1)
