from playwright.sync_api import sync_playwright, expect

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto("http://localhost:8000")

            # Wait for the first article card to be visible.
            # This is the key element that indicates the fix is working.
            # We'll wait for up to 10 seconds.
            first_article_card = page.locator(".article-card").first
            expect(first_article_card).to_be_visible(timeout=10000)

            # Take a screenshot to verify that the article cards are now loading.
            page.screenshot(path="jules-scratch/verification/verification.png")
            print("Screenshot taken. Verification successful.")

        except Exception as e:
            print(f"An error occurred: {e}")
            # In case of an error, take a screenshot anyway to help with debugging.
            page.screenshot(path="jules-scratch/verification/error.png")
        finally:
            browser.close()

if __name__ == "__main__":
    run()
