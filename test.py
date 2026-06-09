"""
Test script for Confluence Manager

This script demonstrates the full workflow:
1. Fetch the current Confluence page
2. Save it to a JSON file
3. Read from that JSON file
4. Update the Confluence page with the data from the file
"""

from confluence_manager import fetch_confluence_page_json, update_confluence_page
import json


def main():
    print("=" * 80)
    print("Confluence Manager Test Script")
    print("=" * 80)
    print()

    # Step 1: Fetch the current page
    print("Step 1: Fetching current Confluence page...")
    print("-" * 80)

    try:
        current_page_data = fetch_confluence_page_json()

        print(f"✓ Successfully fetched page!")
        print(f"  Title: {current_page_data['metadata']['title']}")
        print(f"  Page ID: {current_page_data['metadata']['page_id']}")
        print(f"  Version: {current_page_data['metadata']['version']}")
        print(f"  URL: {current_page_data['metadata']['page_url']}")
        print()

    except Exception as e:
        print(f"❌ Error fetching page: {e}")
        return

    # Step 2: Save current page to file
    print("Step 2: Saving page to JSON file...")
    print("-" * 80)

    output_file = "current_confluence_page.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(current_page_data, f, indent=2, ensure_ascii=False)

        print(f"✓ Page saved to: {output_file}")

        # Show file size
        import os
        file_size = os.path.getsize(output_file)
        print(f"  File size: {file_size:,} bytes")
        print()

    except Exception as e:
        print(f"❌ Error saving file: {e}")
        return

    # Step 3: Read from the JSON file
    print("Step 3: Reading from JSON file...")
    print("-" * 80)

    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            page_data_from_file = json.load(f)

        print(f"✓ Successfully loaded data from: {output_file}")

        # Display some info
        print(f"  Title: {page_data_from_file['metadata'].get('title', 'N/A')}")
        sections_count = len(page_data_from_file.get("content", {}).get("sections", []))
        print(f"  Sections: {sections_count}")
        print()

    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON file: {e}")
        return
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return

    # Step 4: Update the Confluence page using the data from file
    print("Step 4: Updating Confluence page with data from file...")
    print("-" * 80)

    try:
        success = update_confluence_page(page_data_from_file)

        if success:
            print()
            print("=" * 80)
            print("✓ Round-trip test completed successfully!")
            print("=" * 80)
            print()
            print("Summary:")
            print(f"  1. Fetched current page from Confluence")
            print(f"  2. Saved to: {output_file}")
            print(f"  3. Read back from: {output_file}")
            print(f"  4. Updated Confluence page successfully")
            print()
            print("This confirms the fetch -> save -> read -> update cycle works!")
            print()
        else:
            print()
            print("❌ Update failed!")
            print("   Check the error messages above for details.")
            print()

    except Exception as e:
        print(f"❌ Error updating page: {e}")
        return


if __name__ == "__main__":
    main()
