from playwright.sync_api import sync_playwright
import os, urllib.parse as u

URL = "https://www.bershka.com/ww/en/men/clothes/view-all-c1010834564.html"
proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
proxy_kw = {}
if proxy:
    pu = u.urlparse(proxy)
    proxy_kw = {"server": f"{pu.scheme}://{pu.hostname}:{pu.port}"}
    if pu.username: proxy_kw["username"] = pu.username
    if pu.password: proxy_kw["password"] = pu.password

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, proxy=(proxy_kw or None))
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        ignore_https_errors=True,
    )
    page = context.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    for _ in range(6):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(900)
    open("bershka_view_all.html", "w", encoding="utf-8").write(page.content())
    context.close(); browser.close()
print("Saved bershka_view_all.html")