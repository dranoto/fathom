import re
from playwright.sync_api import Page, expect

def test_mobile_button_functionality(page: Page):
    # Use a mobile viewport
    # In headless mode, we can't use device descriptors directly, so we set the viewport size.
    # The iPhone 11 viewport is 414x896, but we'll use a common mobile size.
    page.set_viewport_size({"width": 375, "height": 812})

    # 1. Go to the app
    page.goto("http://localhost:8000/")

    # 2. Go to setup to add a feed
    page.get_by_role("button", name="Setup").click()
    expect(page.get_by_role("heading", name="Setup & Preferences")).to_be_visible()

    # 3. Add an RSS feed
    page.get_by_label("New RSS Feed URL:").fill("https://www.technologyreview.com/feed/")
    page.get_by_role("button", name="Add Feed").click()

    # Wait for the feed to appear in the list
    expect(page.get_by_text("technologyreview.com")).to_be_visible(timeout=10000)

    # 4. Go back to the main feed
    page.get_by_role("button", name="Main Feed").click()
    expect(page.get_by_role("heading", name="Latest Summaries")).to_be_visible()

    # 5. Wait for an article to appear and find the first "Summarize with AI" button
    # This can take a while as the backend needs to fetch and process
    summarize_button = page.get_by_role("button", name="Summarize with AI").first
    expect(summarize_button).to_be_visible(timeout=60000) # Wait up to 60 seconds for the first article

    article_card = page.locator(".article-card", has=summarize_button)

    # 6. Click the summarize button and check for the loading text
    summarize_button.click()

    # We expect the article card to now contain the text "Regenerating summary..."
    expect(article_card).to_contain_text("Regenerating summary...", timeout=5000)

    # 7. Test the favorites button
    favorites_button = page.get_by_role("button", name="Favorites")
    favorites_button.click()

    # After clicking favorites, the loading text should show "Favorites"
    loading_text = page.locator("#loading-text")
    expect(loading_text).to_contain_text("Favorites", timeout=10000)

    # 8. Take a screenshot
    page.screenshot(path="jules-scratch/verification/mobile_verification.png")
