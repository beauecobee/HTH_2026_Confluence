"""
Confluence Page Manager Module

This module provides functions to:
- Fetch Confluence pages and convert them to JSON
- Update Confluence pages from JSON data

Can be used as a standalone script or imported as a module.
"""

import os
import requests
import json
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# Load environment variables from .env file
load_dotenv()

# Get Confluence credentials from environment
CONFLUENCE_BASE_URL = os.getenv('CONFLUENCE_BASE_URL')
CONFLUENCE_EMAIL = os.getenv('CONFLUENCE_EMAIL')
CONFLUENCE_API_TOKEN = os.getenv('CONFLUENCE_API_TOKEN')
CONFLUENCE_PAGE_ID = os.getenv('CONFLUENCE_PAGE_ID')


def _validate_env_vars():
    """Validate that all required environment variables are set."""
    required_vars = {
        'CONFLUENCE_BASE_URL': CONFLUENCE_BASE_URL,
        'CONFLUENCE_EMAIL': CONFLUENCE_EMAIL,
        'CONFLUENCE_API_TOKEN': CONFLUENCE_API_TOKEN,
        'CONFLUENCE_PAGE_ID': CONFLUENCE_PAGE_ID
    }

    missing_vars = [name for name, value in required_vars.items() if not value]

    if missing_vars:
        print("❌ Error: Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nMake sure you have:")
        print("  1. Renamed 'env.example' to '.env'")
        print("  2. Filled in all the Confluence values in the .env file")
        return False
    return True

def parse_table(table):
    """Parse an HTML table into a list of dictionaries."""
    rows = []
    headers = []
    skip_first_tbody_row = False

    # Get headers from thead or first row
    thead = table.find('thead')
    if thead:
        header_row = thead.find('tr')
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]

    # If no thead, try to get headers from first row in tbody
    if not headers:
        tbody = table.find('tbody')
        if tbody:
            first_row = tbody.find('tr')
            if first_row:
                # Check if first row contains th elements (likely headers)
                if first_row.find('th'):
                    headers = [th.get_text(strip=True) for th in first_row.find_all(['th', 'td'])]
                    skip_first_tbody_row = True
                else:
                    # Check if all cells look like headers (you might need to adjust this logic)
                    cells = first_row.find_all(['th', 'td'])
                    headers = [cell.get_text(strip=True) for cell in cells]
                    skip_first_tbody_row = True

    # Get data rows
    tbody = table.find('tbody')
    if tbody:
        for idx, row in enumerate(tbody.find_all('tr')):
            # Skip first row if we used it as headers
            if skip_first_tbody_row and idx == 0:
                continue

            cells = row.find_all(['td', 'th'])
            if cells:
                # If we have headers, create a dictionary
                if headers and len(headers) == len(cells):
                    row_dict = {}
                    for i, cell in enumerate(cells):
                        # Preserve inner HTML for cells (for <time>, <a>, etc.)
                        cell_html = ''.join(str(content) for content in cell.contents)
                        row_dict[headers[i]] = cell_html.strip() if cell_html.strip() else cell.get_text(strip=True)
                    rows.append(row_dict)
                else:
                    # Otherwise, just use a list of cell values with HTML preserved
                    rows.append([''.join(str(content) for content in cell.contents).strip() or cell.get_text(strip=True) for cell in cells])

    return rows


def parse_list(ul_or_ol):
    """Parse an HTML list (ul or ol) into a list of strings."""
    items = []
    for li in ul_or_ol.find_all('li', recursive=False):
        items.append(li.get_text(strip=True))
    return items


def parse_html_to_json(html_content):
    """Parse Confluence HTML storage format into hierarchical JSON."""
    soup = BeautifulSoup(html_content, 'html.parser')

    result = {
        "sections": []
    }

    current_h1 = None
    current_h2 = None

    # Helper function to check if element is inside a table, list, or other container
    def is_nested_in_container(elem):
        """Check if element is nested inside a table or list."""
        for parent in elem.parents:
            if parent.name in ['table', 'ul', 'ol']:
                return True
        return False

    # Iterate through all elements
    for element in soup.find_all(['h1', 'h2', 'h3', 'table', 'ul', 'ol', 'p', 'hr']):

        # Skip paragraphs that are inside tables or lists
        if element.name == 'p' and is_nested_in_container(element):
            continue

        if element.name == 'h1':
            # New h1 section
            current_h1 = {
                "title": element.get_text(strip=True),
                "subsections": []
            }
            result["sections"].append(current_h1)
            current_h2 = None

        elif element.name == 'h2':
            # New h2 subsection under current h1
            if current_h1 is not None:
                current_h2 = {
                    "title": element.get_text(strip=True),
                    "content": []
                }
                current_h1["subsections"].append(current_h2)
            else:
                # H2 without H1, create a new top-level section
                current_h2 = {
                    "title": element.get_text(strip=True),
                    "content": []
                }
                result["sections"].append(current_h2)

        elif element.name == 'h3':
            # H3 under current h2
            if current_h2 is not None:
                current_h2["content"].append({
                    "type": "heading3",
                    "value": element.get_text(strip=True)
                })

        elif element.name == 'table':
            # Table under current h2
            table_data = parse_table(element)
            if current_h2 is not None:
                current_h2["content"].append({
                    "type": "table",
                    "value": table_data
                })
            elif current_h1 is not None:
                # Table directly under h1 without h2
                if "content" not in current_h1:
                    current_h1["content"] = []
                current_h1["content"].append({
                    "type": "table",
                    "value": table_data
                })

        elif element.name in ['ul', 'ol']:
            # List under current h2
            list_data = parse_list(element)
            if current_h2 is not None:
                current_h2["content"].append({
                    "type": "list",
                    "list_type": element.name,
                    "value": list_data
                })
            elif current_h1 is not None:
                # List directly under h1 without h2
                if "content" not in current_h1:
                    current_h1["content"] = []
                current_h1["content"].append({
                    "type": "list",
                    "list_type": element.name,
                    "value": list_data
                })

        elif element.name == 'p':
            # Paragraph under current h2
            text = element.get_text(strip=True)
            if text:  # Only add non-empty paragraphs
                if current_h2 is not None:
                    current_h2["content"].append({
                        "type": "paragraph",
                        "value": text
                    })
                elif current_h1 is not None:
                    # Paragraph directly under h1 without h2
                    if "content" not in current_h1:
                        current_h1["content"] = []
                    current_h1["content"].append({
                        "type": "paragraph",
                        "value": text
                    })

        elif element.name == 'hr':
            # Horizontal rule - preserve attributes like local-id
            hr_attrs = dict(element.attrs)
            if current_h2 is not None:
                current_h2["content"].append({
                    "type": "horizontal_rule",
                    "attributes": hr_attrs
                })
            elif current_h1 is not None:
                if "content" not in current_h1:
                    current_h1["content"] = []
                current_h1["content"].append({
                    "type": "horizontal_rule",
                    "attributes": hr_attrs
                })
            else:
                # HR at top level (before any headings)
                result["sections"].append({
                    "type": "horizontal_rule",
                    "attributes": hr_attrs
                })

    return result


def json_to_html(json_data):
    """Convert JSON structure back to Confluence HTML storage format."""
    html_parts = []

    content = json_data.get("content", {})
    sections = content.get("sections", [])

    for section in sections:
        # Check if this is a horizontal rule at top level
        if section.get("type") == "horizontal_rule":
            attrs = section.get("attributes", {})
            attr_str = " ".join([f'{k}="{v}"' for k, v in attrs.items()])
            if attr_str:
                html_parts.append(f"<hr {attr_str} />")
            else:
                html_parts.append("<hr />")
            continue

        # Check if this is an h1 section with subsections or an h2 section at top level
        if "subsections" in section:
            # This is an h1 section
            html_parts.append(f"<h1>{section['title']}</h1>")

            # Add any direct content under h1 (if exists)
            if "content" in section:
                for item in section["content"]:
                    html_parts.append(content_item_to_html(item))

            # Process h2 subsections
            for subsection in section.get("subsections", []):
                html_parts.append(f"<h2>{subsection['title']}</h2>")

                # Process content under h2
                for item in subsection.get("content", []):
                    html_parts.append(content_item_to_html(item))

        else:
            # This is a top-level h2 section (no h1 parent)
            html_parts.append(f"<h2>{section['title']}</h2>")

            # Process content under h2
            for item in section.get("content", []):
                html_parts.append(content_item_to_html(item))

    return "\n".join(html_parts)


def content_item_to_html(item):
    """Convert a single content item to HTML."""
    item_type = item.get("type")

    if item_type == "paragraph":
        return f"<p>{item['value']}</p>"

    elif item_type == "heading3":
        return f"<h3>{item['value']}</h3>"

    elif item_type == "table":
        return table_to_html(item["value"])

    elif item_type == "list":
        list_type = item.get("list_type", "ul")
        list_items = "\n".join([f"  <li>{li}</li>" for li in item["value"]])
        return f"<{list_type}>\n{list_items}\n</{list_type}>"

    elif item_type == "horizontal_rule":
        # Reconstruct <hr> with its attributes
        attrs = item.get("attributes", {})
        attr_str = " ".join([f'{k}="{v}"' for k, v in attrs.items()])
        if attr_str:
            return f"<hr {attr_str} />"
        else:
            return "<hr />"

    return ""


def table_to_html(table_data):
    """Convert table data to HTML table format."""
    if not table_data:
        return "<table></table>"

    html_parts = ["<table>"]

    # If table_data is a list of dictionaries, extract headers
    if isinstance(table_data[0], dict):
        headers = list(table_data[0].keys())

        # Add header row
        html_parts.append("  <thead>")
        html_parts.append("    <tr>")
        for header in headers:
            html_parts.append(f"      <th>{header}</th>")
        html_parts.append("    </tr>")
        html_parts.append("  </thead>")

        # Add data rows (cells may contain HTML like <time>, <a>, etc.)
        html_parts.append("  <tbody>")
        for row in table_data:
            html_parts.append("    <tr>")
            for header in headers:
                cell_content = row.get(header, '')
                # Don't escape the cell content - it may contain valid HTML
                html_parts.append(f"      <td>{cell_content}</td>")
            html_parts.append("    </tr>")
        html_parts.append("  </tbody>")

    else:
        # Table data is a list of lists
        html_parts.append("  <tbody>")
        for row in table_data:
            html_parts.append("    <tr>")
            for cell in row:
                # Don't escape the cell content - it may contain valid HTML
                html_parts.append(f"      <td>{cell}</td>")
            html_parts.append("    </tr>")
        html_parts.append("  </tbody>")

    html_parts.append("</table>")

    return "\n".join(html_parts)


def read_confluence_page():
    """Read content from a Confluence page and convert to JSON."""

    # Get page content
    get_url = f"{CONFLUENCE_BASE_URL}/wiki/rest/api/content/{CONFLUENCE_PAGE_ID}"
    response = requests.get(
        get_url,
        auth=(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN),
        params={'expand': 'body.storage,version'}
    )

    if response.status_code != 200:
        print(f"❌ Error getting page: {response.status_code}")
        print(response.text)
        return False

    page_data = response.json()

    # Get the content
    title = page_data['title']
    storage_content = page_data['body']['storage']['value']
    version = page_data['version']['number']

    # Parse HTML to JSON
    parsed_json = parse_html_to_json(storage_content)

    # Add metadata
    output_data = {
        "metadata": {
            "title": title,
            "page_id": CONFLUENCE_PAGE_ID,
            "version": version,
            "page_url": f"{CONFLUENCE_BASE_URL}/wiki/spaces/x/pages/{CONFLUENCE_PAGE_ID}"
        },
        "content": parsed_json
    }

    # Save to JSON file
    json_filename = "confluence_page_content.json"
    with open(json_filename, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    # Save original HTML
    original_html_filename = "confluence_original_html.txt"
    with open(original_html_filename, 'w', encoding='utf-8') as f:
        f.write(storage_content)

    # Convert JSON back to HTML and save
    regenerated_html = json_to_html(output_data)
    regenerated_html_filename = "confluence_regenerated_html.txt"
    with open(regenerated_html_filename, 'w', encoding='utf-8') as f:
        f.write(regenerated_html)

    print(f"✓ Successfully read Confluence page!")
    print(f"  Title: {title}")
    print(f"  Version: {version}")
    print(f"  JSON saved to: {json_filename}")
    print(f"  Original HTML saved to: {original_html_filename}")
    print(f"  Regenerated HTML saved to: {regenerated_html_filename}")
    print(f"  Page URL: {CONFLUENCE_BASE_URL}/wiki/spaces/x/pages/{CONFLUENCE_PAGE_ID}")

    return regenerated_html


def update_confluence_page(content):
    """Update a Confluence page with new content."""

    # Get current page version (required for updates)
    get_url = f"{CONFLUENCE_BASE_URL}/wiki/rest/api/content/{CONFLUENCE_PAGE_ID}"
    response = requests.get(
        get_url,
        auth=(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN),
        params={'expand': 'version,body.storage'}
    )

    if response.status_code != 200:
        print(f"Error getting page: {response.status_code}")
        print(response.text)
        return False

    page_data = response.json()
    current_version = page_data['version']['number']

    # Update the page
    update_url = f"{CONFLUENCE_BASE_URL}/wiki/rest/api/content/{CONFLUENCE_PAGE_ID}"
    update_data = {
        "version": {
            "number": current_version + 1
        },
        "title": page_data['title'],  # Keep existing title
        "type": "page",
        "body": {
            "storage": {
                "value": content,
                "representation": "storage"
            }
        }
    }

    response = requests.put(
        update_url,
        auth=(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN),
        headers={"Content-Type": "application/json"},
        json=update_data
    )

    if response.status_code == 200:
        print("✓ Successfully updated Confluence page!")
        print(f"Page URL: {CONFLUENCE_BASE_URL}/wiki/spaces/x/pages/{CONFLUENCE_PAGE_ID}")
        return True
    else:
        print(f"Error updating page: {response.status_code}")
        print(response.text)
        return False

def modify_json_data(json_data):
    """Modify JSON data to add new events and notes."""

    content = json_data.get("content", {})
    sections = content.get("sections", [])

    # Find and modify Ares/Artemis 4.10.33.x section
    for section in sections:
        if "subsections" in section and "Ares/Artemis 4.10.33.x" in section.get("title", ""):
            # Look for "Last 5 Events" subsection
            for subsection in section.get("subsections", []):
                if "Last 5 Events" in subsection.get("title", ""):
                    # Find the table content
                    for item in subsection.get("content", []):
                        if item.get("type") == "table":
                            # Add a new event row to the beginning of the table
                            new_event_row = {
                                "Date": "<p><time datetime=\"2026-06-09\"></time></p>",
                                "Time": "<p>11:30 AM</p>",
                                "Event": "<p>New test build deployed for regression testing</p>",
                                "Person / Source": "<p>CI/CD Bot</p>",
                                "Link": "<p><a href=\"https://generac.slack.com/archives/C01ABC123/p1717950000123461\">Slack link</a></p>"
                            }
                            item["value"].insert(0, new_event_row)
                            print("✓ Added new event to 'Last 5 Events' table in Ares/Artemis 4.10.33.x")
                            break

        # Find and modify Vulcan 4.10.32.x section
        if "subsections" in section and "Vulcan 4.10.32.x" in section.get("title", ""):
            # Look for "Other notes" subsection
            for subsection in section.get("subsections", []):
                if "Other notes" in subsection.get("title", ""):
                    # Find the list content
                    for item in subsection.get("content", []):
                        if item.get("type") == "list":
                            # Add a new note
                            new_note = "Security audit scheduled for next sprint - preliminary review shows no critical vulnerabilities"
                            item["value"].append(new_note)
                            print("✓ Added new note to 'Other notes' in Vulcan 4.10.32.x")
                            break

    return json_data


if __name__ == "__main__":
    # Read the Confluence page, parse to JSON, and regenerate HTML
    regenerated_html = read_confluence_page()

    if regenerated_html:
        # Load the JSON file that was just created
        json_filename = "confluence_page_content.json"
        with open(json_filename, 'r', encoding='utf-8') as f:
            json_data = json.load(f)

        print("\n" + "=" * 80)
        print("Modifying JSON data...")
        print("=" * 80 + "\n")

        # Modify the JSON data
        modified_json = modify_json_data(json_data)

        # Save the modified JSON
        modified_json_filename = "confluence_page_content_modified.json"
        with open(modified_json_filename, 'w', encoding='utf-8') as f:
            json.dump(modified_json, f, indent=2, ensure_ascii=False)
        print(f"✓ Modified JSON saved to: {modified_json_filename}")

        # Convert modified JSON back to HTML
        modified_html = json_to_html(modified_json)
        modified_html_filename = "confluence_modified_html.txt"
        with open(modified_html_filename, 'w', encoding='utf-8') as f:
            f.write(modified_html)
        print(f"✓ Modified HTML saved to: {modified_html_filename}")

        print("\n" + "=" * 80)
        print("Writing modified HTML back to Confluence page...")
        print("=" * 80 + "\n")

        # Write the modified HTML back to Confluence
        success = update_confluence_page(modified_html)

        if success:
            print("\n✓ Full cycle completed successfully!")
            print("  1. Read original HTML from Confluence")
            print("  2. Converted to JSON")
            print("  3. Modified JSON (added event and note)")
            print("  4. Regenerated HTML from modified JSON")
            print("  5. Wrote modified HTML back to Confluence")
        else:
            print("\n❌ Failed to write back to Confluence")

    # To write custom content instead, replace the above with:
    # content = "<p>hello world</p>"
    # update_confluence_page(content)
