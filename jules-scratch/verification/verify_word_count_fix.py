from playwright.sync_api import sync_playwright, expect

def run_verification(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    try:
        # 1. Navigate to the application
        page.goto("http://localhost:8000")

        # 2. Go to the "Setup" tab
        page.get_by_role("button", name="Setup").click()
        expect(page.get_by_role("heading", name="Content Preferences")).to_be_visible()

        # 3. Change the "Minimum Word Count" to a high value and save
        min_word_count_input = page.locator("#minimum-word-count-setup")
        expect(min_word_count_input).to_be_visible()
        min_word_count_input.fill("800")

        # Click the save button for the content preferences form
        page.get_by_role("form", target="#content-prefs-form").get_by_role("button", name="Save").click()

        # Handle the alert
        page.once("dialog", lambda dialog: dialog.accept())


        # 4. Wait for the article feed to reload by switching back to the main tab
        page.get_by_role("button", name="Main").click()

        # Wait for the loading indicator to disappear
        expect(page.locator("#loading-indicator")).not_to_be_visible(timeout=20000)

        # Assert that a known short article is NOT visible
        # (We are assuming an article with "Microsoft" in the title is short)
        # This is a bit brittle, but good enough for verification
        expect(page.locator(".article-card", has_text="Microsoft")).not_to_be_visible()

        page.screenshot(path="jules-scratch/verification/verification_high_word_count.png")
        print("Screenshot taken with high word count.")

        # 6. Change the "Minimum Word Count" back to a low value
        page.get_by_role("button", name="Setup").click()
        expect(page.get_by_role("heading", name="Content Preferences")).to_be_visible()

        min_word_count_input.fill("10")
        page.get_by_role("form", target="#content-prefs-form").get_by_role("button", name="Save").click()

        # Handle the alert
        page.once("dialog", lambda dialog: dialog.accept())

        # 7. Wait for the article feed to reload
        page.get_by_role("button", name="Main").click()
        expect(page.locator("#loading-indicator")).not_to_be_visible(timeout=20000)

        # 8. Take a final screenshot
        expect(page.locator(".article-card", has_text="Microsoft")).to_be_visible()
        page.screenshot(path="jules-scratch/verification/verification_low_word_count.png")
        print("Screenshot taken with low word count.")

    except Exception as e:
        print(f"An error occurred: {e}")
        page.screenshot(path="jules-scratch/verification/error.png")

    finally:
        browser.close()

with sync_playwright() as p:
    run_verification(p)
