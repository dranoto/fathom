from playwright.sync_api import sync_playwright, expect

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    try:
        # Go to the application
        page.goto("http://localhost:8000")

        # Wait for the first article card to be visible.
        # This indicates that the initial feed has been fetched and rendered.
        # I'll give it a generous timeout since fetching and processing can take time.
        first_article_card = page.locator(".article-card").first
        expect(first_article_card).to_be_visible(timeout=60000)

        # Take a screenshot
        page.screenshot(path="jules-scratch/verification/verification.png")

        print("Screenshot taken successfully.")

    except Exception as e:
        print(f"An error occurred: {e}")
        # In case of an error, take a screenshot anyway to help with debugging.
        page.screenshot(path="jules-scratch/verification/error.png")

    finally:
        browser.close()

with sync_playwright() as playwright:
    run(playwright)
