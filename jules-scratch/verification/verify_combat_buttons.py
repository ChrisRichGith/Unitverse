from playwright.sync_api import sync_playwright, expect
import requests
import re

def clear_app_state():
    requests.post("http://localhost:5000/clear")

def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # --- Test Case 1: Normal Combat ---
        clear_app_state()
        page.goto("http://localhost:5000")
        page.get_by_role("button", name="Spiel starten").click()
        page.wait_for_url("http://localhost:5000/") # Wait for redirect

        # Buy a unit
        page.locator('.side-panel:has-text("Shop") .unit-card').first.get_by_role("button", name="Kaufen").click()
        page.wait_for_url("http://localhost:5000/") # Wait for redirect

        # Start Normal Combat
        page.get_by_role("button", name="Kauf beenden & Kampf starten").click()
        page.wait_for_url(re.compile(r".*/combat_results"))

        # Verify that we are on the combat replay screen
        expect(page.locator("#player1-log-display")).to_be_visible()
        page.screenshot(path="jules-scratch/verification/combat_buttons_fix.png")

        # --- Test Case 2: Quick Combat ---
        clear_app_state()
        page.goto("http://localhost:5000")
        page.get_by_role("button", name="Spiel starten").click()
        page.wait_for_url("http://localhost:5000/") # Wait for redirect

        # Buy a unit
        page.locator('.side-panel:has-text("Shop") .unit-card').first.get_by_role("button", name="Kaufen").click()
        page.wait_for_url("http://localhost:5000/") # Wait for redirect

        # Start Quick Combat
        page.get_by_role("button", name="Schnellkampf").click()
        page.wait_for_url(re.compile(r".*/combat_results"))

        # Verify that we are on the combat results screen
        expect(page.get_by_role("heading", name="Kampf beendet!")).to_be_visible()

        browser.close()

if __name__ == "__main__":
    run_verification()