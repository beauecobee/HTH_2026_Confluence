"""
Confluence Page Manager Module

This module provides functions to:
- Fetch Confluence pages and convert them to JSON
- Update Confluence pages from JSON data

Public API:
- fetch_confluence_page_json(page_id=None) -> dict
- update_confluence_page(json_data, page_id=None) -> bool

Can be used as a standalone script or imported as a module.
"""

import os
import requests
import json
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# Load environment variables from .env file
load_dotenv()


def _get_confluence_credentials(page_id=None):
    """Get Confluence credentials from environment variables."""
    return {
        'base_url': os.getenv('CONFLUENCE_BASE_URL'),
        'email': os.getenv('CONFLUENCE_EMAIL'),
        'api_token': os.getenv('CONFLUENCE_API_TOKEN'),
        'page_id': page_id or os.getenv('CONFLUENCE_PAGE_ID')
    }


def _validate_credentials(creds):
    """Validate that all required credentials are present."""
    missing = [k for k, v in creds.items() if not v]
    if missing:
        raise ValueError(f"Missing required credentials: {', '.join(missing)}")


def _clean_cell_html(cell):
    """
    Clean HTML from table cell while preserving important semantic elements.

    Strips wrapper <p> tags and local-id attributes, but preserves:
    - <time> tags (without local-id)
    - <a> tags (links)
    - Plain text
    """
    from bs4 import BeautifulSoup

    # Parse the cell content
    soup = BeautifulSoup(str(cell), 'html.parser')

    # Remove local-id attributes from all elements
    for tag in soup.find_all(True):
        if tag.has_attr('local-id'):
            del tag['local-id']

    # Check if the cell only contains a <p> wrapper with plain text
    p_tag = soup.find('p')
    if p_tag and not p_tag.find(['time', 'a', 'strong', 'em', 'span']):
        # Just return the text if it's a simple paragraph
        return p_tag.get_text(strip=True)

    # If there's a <p> wrapper, unwrap it but keep inner content
    if p_tag:
        inner_html = ''.join(str(content) for content in p_tag.contents)
        soup = BeautifulSoup(inner_html, 'html.parser')

    # Convert back to string, removing empty tags
    result = str(soup).strip()

    # Clean up if it's just a wrapper tag with nothing inside
    if result.startswith('<html><body>') and result.endswith('</body></html>'):
        result = result[12:-14].strip()

    # If empty after cleaning, return the plain text
    if not result or result == '<p></p>':
        return cell.get_text(strip=True)

    return result if result else cell.get_text(strip=True)


def _parse_table(table):
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
                if first_row.find('th'):
                    headers = [th.get_text(strip=True) for th in first_row.find_all(['th', 'td'])]
                    skip_first_tbody_row = True
                else:
                    cells = first_row.find_all(['th', 'td'])
                    headers = [cell.get_text(strip=True) for cell in cells]
                    skip_first_tbody_row = True

    # Get data rows
    tbody = table.find('tbody')
    if tbody:
        for idx, row in enumerate(tbody.find_all('tr')):
            if skip_first_tbody_row and idx == 0:
                continue

            cells = row.find_all(['td', 'th'])
            if cells:
                if headers and len(headers) == len(cells):
                    row_dict = {}
                    for i, cell in enumerate(cells):
                        # Clean the cell HTML
                        row_dict[headers[i]] = _clean_cell_html(cell)
                    rows.append(row_dict)
                else:
                    rows.append([_clean_cell_html(cell) for cell in cells])

    return rows


def _parse_list(ul_or_ol):
    """Parse an HTML list (ul or ol) into a list of strings."""
    items = []
    for li in ul_or_ol.find_all('li', recursive=False):
        items.append(li.get_text(strip=True))
    return items


def _parse_html_to_json(html_content):
    """Parse Confluence HTML storage format into hierarchical JSON."""
    soup = BeautifulSoup(html_content, 'html.parser')

    result = {
        "sections": []
    }

    current_h1 = None
    current_h2 = None

    def is_nested_in_container(elem):
        """Check if element is nested inside a table or list."""
        for parent in elem.parents:
            if parent.name in ['table', 'ul', 'ol']:
                return True
        return False

    for element in soup.find_all(['h1', 'h2', 'h3', 'table', 'ul', 'ol', 'p', 'hr']):
        if element.name == 'p' and is_nested_in_container(element):
            continue

        if element.name == 'h1':
            current_h1 = {
                "title": element.get_text(strip=True),
                "subsections": []
            }
            result["sections"].append(current_h1)
            current_h2 = None

        elif element.name == 'h2':
            if current_h1 is not None:
                current_h2 = {
                    "title": element.get_text(strip=True),
                    "content": []
                }
                current_h1["subsections"].append(current_h2)
            else:
                current_h2 = {
                    "title": element.get_text(strip=True),
                    "content": []
                }
                result["sections"].append(current_h2)

        elif element.name == 'h3':
            if current_h2 is not None:
                current_h2["content"].append({
                    "type": "heading3",
                    "value": element.get_text(strip=True)
                })

        elif element.name == 'table':
            table_data = _parse_table(element)
            if current_h2 is not None:
                current_h2["content"].append({
                    "type": "table",
                    "value": table_data
                })
            elif current_h1 is not None:
                if "content" not in current_h1:
                    current_h1["content"] = []
                current_h1["content"].append({
                    "type": "table",
                    "value": table_data
                })

        elif element.name in ['ul', 'ol']:
            list_data = _parse_list(element)
            if current_h2 is not None:
                current_h2["content"].append({
                    "type": "list",
                    "list_type": element.name,
                    "value": list_data
                })
            elif current_h1 is not None:
                if "content" not in current_h1:
                    current_h1["content"] = []
                current_h1["content"].append({
                    "type": "list",
                    "list_type": element.name,
                    "value": list_data
                })

        elif element.name == 'p':
            text = element.get_text(strip=True)
            if text:
                if current_h2 is not None:
                    current_h2["content"].append({
                        "type": "paragraph",
                        "value": text
                    })
                elif current_h1 is not None:
                    if "content" not in current_h1:
                        current_h1["content"] = []
                    current_h1["content"].append({
                        "type": "paragraph",
                        "value": text
                    })

        elif element.name == 'hr':
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
                result["sections"].append({
                    "type": "horizontal_rule",
                    "attributes": hr_attrs
                })

    return result


def _content_item_to_html(item):
    """Convert a single content item to HTML."""
    item_type = item.get("type")

    if item_type == "paragraph":
        return f"<p>{item['value']}</p>"

    elif item_type == "heading3":
        return f"<h3>{item['value']}</h3>"

    elif item_type == "table":
        return _table_to_html(item["value"])

    elif item_type == "list":
        list_type = item.get("list_type", "ul")
        list_items = "\n".join([f"  <li>{li}</li>" for li in item["value"]])
        return f"<{list_type}>\n{list_items}\n</{list_type}>"

    elif item_type == "horizontal_rule":
        attrs = item.get("attributes", {})
        attr_str = " ".join([f'{k}="{v}"' for k, v in attrs.items()])
        if attr_str:
            return f"<hr {attr_str} />"
        else:
            return "<hr />"

    return ""


def _wrap_cell_content(content):
    """
    Wrap cell content appropriately for Confluence.

    If content contains HTML tags (like <time> or <a>), wrap in <p>.
    If it's plain text, wrap in <p>.
    If it's already wrapped, return as-is.
    """
    if not content:
        return "<p></p>"

    content_str = str(content).strip()

    # If it already starts with a tag, assume it's properly formatted
    if content_str.startswith('<') and not content_str.startswith('<time>'):
        return content_str

    # Check if content contains HTML tags
    if '<' in content_str and '>' in content_str:
        # It has HTML tags, wrap in <p>
        return f"<p>{content_str}</p>"
    else:
        # Plain text, wrap in <p>
        return f"<p>{content_str}</p>"


def _table_to_html(table_data):
    """Convert table data to HTML table format."""
    if not table_data:
        return "<table></table>"

    html_parts = ["<table>"]

    if isinstance(table_data[0], dict):
        headers = list(table_data[0].keys())

        html_parts.append("  <thead>")
        html_parts.append("    <tr>")
        for header in headers:
            html_parts.append(f"      <th>{header}</th>")
        html_parts.append("    </tr>")
        html_parts.append("  </thead>")

        html_parts.append("  <tbody>")
        for row in table_data:
            html_parts.append("    <tr>")
            for header in headers:
                cell_content = row.get(header, '')
                wrapped_content = _wrap_cell_content(cell_content)
                html_parts.append(f"      <td>{wrapped_content}</td>")
            html_parts.append("    </tr>")
        html_parts.append("  </tbody>")

    else:
        html_parts.append("  <tbody>")
        for row in table_data:
            html_parts.append("    <tr>")
            for cell in row:
                wrapped_content = _wrap_cell_content(cell)
                html_parts.append(f"      <td>{wrapped_content}</td>")
            html_parts.append("    </tr>")
        html_parts.append("  </tbody>")

    html_parts.append("</table>")

    return "\n".join(html_parts)


def _json_to_html(json_data):
    """Convert JSON structure back to Confluence HTML storage format."""
    html_parts = []

    content = json_data.get("content", {})
    sections = content.get("sections", [])

    for section in sections:
        if section.get("type") == "horizontal_rule":
            attrs = section.get("attributes", {})
            attr_str = " ".join([f'{k}="{v}"' for k, v in attrs.items()])
            if attr_str:
                html_parts.append(f"<hr {attr_str} />")
            else:
                html_parts.append("<hr />")
            continue

        if "subsections" in section:
            html_parts.append(f"<h1>{section['title']}</h1>")

            if "content" in section:
                for item in section["content"]:
                    html_parts.append(_content_item_to_html(item))

            for subsection in section.get("subsections", []):
                html_parts.append(f"<h2>{subsection['title']}</h2>")

                for item in subsection.get("content", []):
                    html_parts.append(_content_item_to_html(item))

        else:
            html_parts.append(f"<h2>{section['title']}</h2>")

            for item in section.get("content", []):
                html_parts.append(_content_item_to_html(item))

    return "\n".join(html_parts)


# ============================================================================
# PUBLIC API
# ============================================================================

def fetch_confluence_page_json(page_id=None):
    """
    Fetch a Confluence page and return it as JSON.

    Args:
        page_id (str, optional): The Confluence page ID. If not provided,
                                 uses CONFLUENCE_PAGE_ID from environment.

    Returns:
        dict: JSON representation of the page with structure:
            {
                "metadata": {
                    "title": str,
                    "page_id": str,
                    "version": int,
                    "page_url": str
                },
                "content": {
                    "sections": [...]
                }
            }

    Raises:
        ValueError: If required credentials are missing
        requests.HTTPError: If the API request fails
    """
    creds = _get_confluence_credentials(page_id)
    _validate_credentials(creds)

    get_url = f"{creds['base_url']}/wiki/rest/api/content/{creds['page_id']}"
    response = requests.get(
        get_url,
        auth=(creds['email'], creds['api_token']),
        params={'expand': 'body.storage,version'}
    )

    if response.status_code != 200:
        raise requests.HTTPError(f"Failed to fetch page: {response.status_code} - {response.text}")

    page_data = response.json()

    title = page_data['title']
    storage_content = page_data['body']['storage']['value']
    version = page_data['version']['number']

    parsed_json = _parse_html_to_json(storage_content)

    output_data = {
        "metadata": {
            "title": title,
            "page_id": creds['page_id'],
            "version": version,
            "page_url": f"{creds['base_url']}/wiki/spaces/x/pages/{creds['page_id']}"
        },
        "content": parsed_json
    }

    return output_data


def update_confluence_page(json_data, page_id=None):
    """
    Update a Confluence page with data from JSON.

    This function converts the JSON back to HTML and replaces the entire
    page content on Confluence.

    Args:
        json_data (dict): JSON data with the structure returned by
                         fetch_confluence_page_json()
        page_id (str, optional): The Confluence page ID. If not provided,
                                 uses CONFLUENCE_PAGE_ID from environment.

    Returns:
        bool: True if update was successful, False otherwise

    Raises:
        ValueError: If required credentials are missing
    """
    creds = _get_confluence_credentials(page_id)
    _validate_credentials(creds)

    # Convert JSON to HTML
    html_content = _json_to_html(json_data)

    # Get current page version (required for updates)
    get_url = f"{creds['base_url']}/wiki/rest/api/content/{creds['page_id']}"
    response = requests.get(
        get_url,
        auth=(creds['email'], creds['api_token']),
        params={'expand': 'version,body.storage'}
    )

    if response.status_code != 200:
        print(f"❌ Error getting page: {response.status_code}")
        print(response.text)
        return False

    page_data = response.json()
    current_version = page_data['version']['number']

    # Update the page
    update_url = f"{creds['base_url']}/wiki/rest/api/content/{creds['page_id']}"
    update_data = {
        "version": {
            "number": current_version + 1
        },
        "title": page_data['title'],
        "type": "page",
        "body": {
            "storage": {
                "value": html_content,
                "representation": "storage"
            }
        }
    }

    response = requests.put(
        update_url,
        auth=(creds['email'], creds['api_token']),
        headers={"Content-Type": "application/json"},
        json=update_data
    )

    if response.status_code == 200:
        print(f"✓ Successfully updated Confluence page!")
        print(f"  Page URL: {creds['base_url']}/wiki/spaces/x/pages/{creds['page_id']}")
        return True
    else:
        print(f"❌ Error updating page: {response.status_code}")
        print(response.text)
        return False


# ============================================================================
# CLI USAGE
# ============================================================================

if __name__ == "__main__":
    import sys

    print("Confluence Page Manager")
    print("=" * 80)

    if len(sys.argv) > 1 and sys.argv[1] == "fetch":
        # Fetch mode
        print("Fetching Confluence page...")
        try:
            json_data = fetch_confluence_page_json()

            # Save to file
            output_file = "confluence_page.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)

            print(f"✓ Page fetched successfully!")
            print(f"  Title: {json_data['metadata']['title']}")
            print(f"  Version: {json_data['metadata']['version']}")
            print(f"  Saved to: {output_file}")

        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)

    elif len(sys.argv) > 1 and sys.argv[1] == "update":
        # Update mode
        input_file = sys.argv[2] if len(sys.argv) > 2 else "confluence_page.json"

        print(f"Updating Confluence page from {input_file}...")
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            success = update_confluence_page(json_data)

            if success:
                print("✓ Update completed successfully!")
            else:
                print("❌ Update failed")
                sys.exit(1)

        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)

    else:
        # Help text
        print("\nUsage:")
        print("  python confluence_manager.py fetch")
        print("      Fetch page and save to confluence_page.json")
        print()
        print("  python confluence_manager.py update [file.json]")
        print("      Update page from JSON file (default: confluence_page.json)")
        print()
        print("Or import as a module:")
        print("  from confluence_manager import fetch_confluence_page_json, update_confluence_page")
