import subprocess
import time
import requests
from playwright.sync_api import sync_playwright, expect

def run_verification():
    server_process = None
    try:
        # Start the uvicorn server
        server_process = subprocess.Popen(
            ["uvicorn", "app.main_api:app", "--host", "0.0.0.0", "--port", "8000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Wait for the server to be ready
        for _ in range(30):  # Wait for up to 30 seconds
            try:
                response = requests.get("http://localhost:8000")
                if response.status_code == 200:
                    print("Server is ready.")
                    break
            except requests.ConnectionError:
                time.sleep(1)
        else:
            raise RuntimeError("Server did not start in time.")

        # Run the playwright script
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto("http://localhost:8000")
                # Wait for the first article card to be visible
                expect(page.locator(".article-card").first).to_be_visible(timeout=60000)
                page.screenshot(path="jules-scratch/verification/verification.png")
                print("Screenshot taken successfully.")
            except Exception as e:
                print(f"Playwright error: {e}")
                page.screenshot(path="jules-scratch/verification/error.png")
            finally:
                browser.close()

    finally:
        if server_process:
            server_process.terminate()
            stdout, stderr = server_process.communicate()
            print("Server stdout:")
            print(stdout)
            print("Server stderr:")
            print(stderr)

if __name__ == "__main__":
    run_verification()
