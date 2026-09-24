"""Integrated local Playwright check against the real API and browser UI.

Run from the repository root after starting the isolated flood demo API and web.
Credentials are read from the ignored seed output; never print them.
"""
import argparse
import io
import json
import re
import uuid
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument("--web", default="http://127.0.0.1:5178")
parser.add_argument("--api", default="http://127.0.0.1:8012")
parser.add_argument("--credentials", default=".artifacts/flood-demo-access.json")
parser.add_argument("--offline-refresh", action="store_true", help="Use against a production preview with its service worker")
args = parser.parse_args()
credentials = json.loads(Path(args.credentials).read_text())
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 390, "height": 844})
    context.route("https://tile.openstreetmap.org/**", lambda route: route.abort())
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    assert context.request.get(args.api+"/health").status == 200
    assert context.request.get(args.api+"/docs").status == 200
    page.goto(args.web+"/flood/report")
    expect(page.get_by_role("heading", name="Report flooding. Make the location clear.")).to_be_visible()
    page.get_by_role("button", name="3. Location").click()
    locality = "Browser test " + uuid.uuid4().hex[:8]
    page.get_by_label("District / city", exact=True).fill("Demo City")
    page.get_by_label("Locality", exact=True).fill(locality)
    page.get_by_label("Street name", exact=True).fill("Synthetic Browser Street")
    page.get_by_label("Door / house number", exact=True).fill("12-4/7A")
    page.get_by_label("Directions from landmark / access notes", exact=True).fill("Fictional access notes")
    page.get_by_role("button", name="4. Situation").click()
    page.get_by_label("People count quality", exact=True).select_option("estimated")
    page.get_by_label("Reported people needing assistance", exact=True).fill("3")
    page.get_by_label("Water level — citizen estimate", exact=True).select_option("knee")
    page.get_by_role("button", name="2. Photographs").click()
    out = io.BytesIO()
    Image.new("RGB", (64, 64), "navy").save(out, format="JPEG")
    page.get_by_label("Choose from gallery").set_input_files({"name": "synthetic.jpg", "mimeType": "image/jpeg", "buffer": out.getvalue()})
    expect(page.get_by_role("img", name="Selected photo synthetic.jpg")).to_be_visible()
    page.get_by_role("button", name="5. Review & send").click()
    expect(page.get_by_role("status")).to_contain_text("Saved on this device")
    if args.offline_refresh:
        page.evaluate("navigator.serviceWorker.ready.then(() => true)")
        page.reload()
        page.get_by_role("button", name="5. Review & send").click()
    # Failure and retry use real offline network state, not mocked API responses.
    context.set_offline(True)
    page.get_by_role("button", name="Submit report", exact=True).click()
    expect(page.get_by_role("button", name="Retry submission", exact=True)).to_be_enabled(timeout=25000)
    if args.offline_refresh:
        page.reload()
    else:
        context.set_offline(False)
        page.reload()
    expect(page.get_by_role("alert")).to_contain_text("Recovered report")
    page.get_by_role("button", name="3. Location").click()
    expect(page.get_by_label("Door / house number", exact=True)).to_have_value("12-4/7A")
    context.set_offline(False)
    page.get_by_role("button", name="5. Review & send").click()
    page.get_by_role("button", name="Retry submission", exact=True).click()
    expect(page.get_by_role("heading", name="Received by the platform")).to_be_visible(timeout=25000)
    expect(page.get_by_text("Photos attached: 1 of 1. Photos remain private.")).to_be_visible(timeout=25000)
    text = page.locator("main").inner_text()
    incident_id = int(re.search(r"Incident #(\d+)", text).group(1))
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=".artifacts/flood-mobile.png", full_page=True)
    page.goto(args.web+"/flood")
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.get_by_label("Locality", exact=True).fill(locality)
    expect(page.locator(".flood-list-item")).to_have_count(1)
    page.locator(".flood-list-item").filter(has_text=locality).click()
    expect(page.get_by_role("heading", name=f"Incident #{incident_id}", exact=True)).to_be_visible()
    assert "12-4/7A" not in page.locator("main").inner_text()
    page.get_by_text("Coordinator / responder access", exact=True).click()
    page.get_by_label("Operational credential", exact=True).fill(credentials["coordinator"])
    page.get_by_role("button", name="Unlock operational view").click()
    expect(page.get_by_text("Synthetic coordinator · coordinator", exact=True)).to_be_visible()
    page.locator(".flood-list-item").filter(has_text=locality).click()
    page.get_by_label("Evidence and reason", exact=True).fill("Reviewed synthetic browser evidence; count estimated")
    page.get_by_role("button", name="Save reviewed situation").click()
    expect(page.get_by_text("Reported people: 3 (estimated)", exact=False)).to_be_visible()
    def transition(state):
        page.get_by_label("Next rescue state", exact=True).select_option(state)
        page.get_by_label("Progress / reason", exact=True).fill("Synthetic integrated browser progress")
        if state == "assigned":
            page.get_by_label("Assign team", exact=True).select_option("synthetic-water-team")
        if state == "resolved":
            page.get_by_label("Resolution outcome", exact=True).fill("Synthetic rescue complete")
            page.get_by_label("Number assisted, if known", exact=True).fill("3")
            page.get_by_label("Remaining needs (write none if none)", exact=True).fill("none")
        page.get_by_role("button", name="Record task transition").click()
        expect(page.get_by_role("heading", name="Rescue task: "+state.replace("_", " "), exact=True)).to_be_visible()
    transition("ready")
    transition("assigned")
    page.get_by_role("button", name="Lock operational view").click()
    page.get_by_text("Coordinator / responder access", exact=True).click()
    page.get_by_label("Operational credential", exact=True).fill(credentials["responder"])
    page.get_by_role("button", name="Unlock operational view").click()
    expect(page.get_by_text("Synthetic responder · responder", exact=True)).to_be_visible()
    page.get_by_label("Locality", exact=True).fill(locality)
    page.locator(".flood-list-item").filter(has_text=locality).click()
    transition("en_route")
    transition("on_scene")
    transition("resolved")
    expect(page.get_by_text("active flooding", exact=False)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=".artifacts/flood-desktop.png", full_page=True)
    assert not errors, errors
    browser.close()
print("PASS: mobile offline recovery/photo upload; public privacy; coordinator review/assignment; responder progress/resolution; flooding remains active; desktop/mobile layout; health/docs")
