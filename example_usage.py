"""
Example script showing how to use confluence_manager module.

This demonstrates:
1. Fetching a Confluence page as JSON
2. Modifying the JSON data
3. Updating the Confluence page with the modified data
"""

from confluence_manager import fetch_confluence_page_json, update_confluence_page
import json


def add_event_to_release(json_data, release_name, event_data):
    """
    Add a new event to the "Last 5 Events" table for a specific release.

    Args:
        json_data (dict): The Confluence page JSON data
        release_name (str): Name of the release (e.g., "Ares/Artemis 4.10.33.x")
        event_data (dict): Event data with keys: Date, Time, Event, Person / Source, Link

    Returns:
        dict: Modified JSON data
    """
    content = json_data.get("content", {})
    sections = content.get("sections", [])

    for section in sections:
        if "subsections" in section and release_name in section.get("title", ""):
            for subsection in section.get("subsections", []):
                if "Last 5 Events" in subsection.get("title", ""):
                    for item in subsection.get("content", []):
                        if item.get("type") == "table":
                            # Add new event row to the beginning
                            item["value"].insert(0, event_data)
                            print(f"✓ Added event to '{release_name}' - Last 5 Events")
                            return json_data

    print(f"⚠️  Could not find 'Last 5 Events' for '{release_name}'")
    return json_data


def add_note_to_release(json_data, release_name, note_text):
    """
    Add a new note to the "Other notes" list for a specific release.

    Args:
        json_data (dict): The Confluence page JSON data
        release_name (str): Name of the release (e.g., "Vulcan 4.10.32.x")
        note_text (str): The note text to add

    Returns:
        dict: Modified JSON data
    """
    content = json_data.get("content", {})
    sections = content.get("sections", [])

    for section in sections:
        if "subsections" in section and release_name in section.get("title", ""):
            for subsection in section.get("subsections", []):
                if "Other notes" in subsection.get("title", ""):
                    for item in subsection.get("content", []):
                        if item.get("type") == "list":
                            item["value"].append(note_text)
                            print(f"✓ Added note to '{release_name}' - Other notes")
                            return json_data

    print(f"⚠️  Could not find 'Other notes' for '{release_name}'")
    return json_data


def main():
    print("=" * 80)
    print("Confluence Page Update Example")
    print("=" * 80)
    print()

    # Step 1: Fetch the current page as JSON
    print("Step 1: Fetching Confluence page...")
    try:
        json_data = fetch_confluence_page_json()
        print(f"✓ Fetched page: {json_data['metadata']['title']}")
        print(f"  Version: {json_data['metadata']['version']}")
        print()
    except Exception as e:
        print(f"❌ Error fetching page: {e}")
        return

    # Step 2: Modify the JSON data
    print("Step 2: Modifying JSON data...")

    # Add a new event to Ares/Artemis
    new_event = {
        "Date": "<p><time datetime=\"2026-06-09\"></time></p>",
        "Time": "<p>3:45 PM</p>",
        "Event": "<p>Successful integration test on staging environment</p>",
        "Person / Source": "<p>QA Automation</p>",
        "Link": "<p><a href=\"https://generac.slack.com/archives/C01ABC123/p1717960000123462\">Slack link</a></p>"
    }
    json_data = add_event_to_release(json_data, "Ares/Artemis 4.10.33.x", new_event)

    # Add a note to Vulcan
    json_data = add_note_to_release(
        json_data,
        "Vulcan 4.10.32.x",
        "Performance testing completed - 15% improvement in response time"
    )

    print()

    # Optional: Save modified JSON to file for inspection
    with open("confluence_page_modified.json", 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print("✓ Modified JSON saved to: confluence_page_modified.json")
    print()

    # Step 3: Update the Confluence page
    print("Step 3: Updating Confluence page...")
    try:
        success = update_confluence_page(json_data)
        if success:
            print()
            print("=" * 80)
            print("✓ Update completed successfully!")
            print("=" * 80)
        else:
            print("❌ Update failed")
    except Exception as e:
        print(f"❌ Error updating page: {e}")


if __name__ == "__main__":
    main()
