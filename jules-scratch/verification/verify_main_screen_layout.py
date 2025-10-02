from playwright.sync_api import sync_playwright, expect

def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # Navigate to the application's main page
            page.goto("http://127.0.0.1:5000/")

            # Wait for the page to load and the bottom menu to be visible
            expect(page.locator(".bottom-menu")).to_be_visible(timeout=5000)

            # Take a screenshot of the main screen
            page.screenshot(path="jules-scratch/verification/main_screen_layout.png")
            print("Screenshot 'jules-scratch/verification/main_screen_layout.png' created successfully.")

        except Exception as e:
            print(f"An error occurred: {e}")
            page.screenshot(path="jules-scratch/verification/error.png")

        finally:
            browser.close()

if __name__ == "__main__":
    run_verification()