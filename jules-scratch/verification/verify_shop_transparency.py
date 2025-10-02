from playwright.sync_api import sync_playwright, expect

def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # Navigate to the application's main page
            page.goto("http://127.0.0.1:5000/")

            # Start a new game to get to the shop screen
            new_game_button = page.get_by_role("button", name="Neues Spiel")
            if new_game_button.is_visible(timeout=5000):
                new_game_button.click()
            else:
                page.get_by_role("button", name="Spiel starten").click()

            page.wait_for_load_state("networkidle")

            # Wait for the shop page containers to be visible
            expect(page.locator(".prep-container")).to_be_visible(timeout=5000)

            # Take a screenshot of the shop screen
            page.screenshot(path="jules-scratch/verification/shop_transparency.png")
            print("Screenshot 'jules-scratch/verification/shop_transparency.png' created successfully.")

        except Exception as e:
            print(f"An error occurred: {e}")
            page.screenshot(path="jules-scratch/verification/error.png")

        finally:
            browser.close()

if __name__ == "__main__":
    run_verification()