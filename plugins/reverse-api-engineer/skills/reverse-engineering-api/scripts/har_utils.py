#!/usr/bin/env python3
"""
Shared utilities for HAR analysis scripts.

This module provides common functions used across har_filter.py,
har_analyze.py, and har_validate.py.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse, parse_qs


def load_har(har_path: Path) -> Dict[str, Any]:
    """
    Load and parse a HAR file.

    Args:
        har_path: Path to the HAR file

    Returns:
        Parsed HAR data as dictionary

    Raises:
        FileNotFoundError: If HAR file doesn't exist
        json.JSONDecodeError: If HAR file is invalid JSON
        ValueError: If HAR structure is invalid
    """
    if not har_path.exists():
        raise FileNotFoundError(f"HAR file not found: {har_path}")

    with open(har_path, 'r', encoding='utf-8') as f:
        har_data = json.load(f)

    if not validate_har(har_data):
        raise ValueError("Invalid HAR structure")

    return har_data


def validate_har(har: Dict[str, Any]) -> bool:
    """
    Validate HAR structure.

    Args:
        har: HAR data dictionary

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(har, dict):
        return False

    if 'log' not in har:
        return False

    log = har['log']
    if not isinstance(log, dict):
        return False

    if 'entries' not in log:
        return False

    return isinstance(log['entries'], list)


def get_content_type(entry: Dict[str, Any]) -> Optional[str]:
    """
    Extract content-type from HAR entry.

    Args:
        entry: HAR entry dictionary

    Returns:
        Content-type string or None if not found
    """
    response = entry.get('response', {})
    headers = response.get('headers', [])

    for header in headers:
        if isinstance(header, dict):
            name = header.get('name', '').lower()
            if name == 'content-type':
                return header.get('value', '')

    return None


def parse_json_safe(text: str) -> Optional[Dict[str, Any]]:
    """
    Safely parse JSON text.

    Args:
        text: JSON string to parse

    Returns:
        Parsed dictionary or None if parsing fails
    """
    if not text or not isinstance(text, str):
        return None

    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def is_uuid(s: str) -> bool:
    """
    Check if a string is a UUID.

    Args:
        s: String to check

    Returns:
        True if string matches UUID pattern
    """
    uuid_pattern = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    return bool(uuid_pattern.match(s))


def is_numeric_id(s: str) -> bool:
    """
    Check if a string is a numeric ID.

    Args:
        s: String to check

    Returns:
        True if string is all digits
    """
    return s.isdigit()


def is_path_parameter(s: str) -> bool:
    """
    Check if a URL path segment is likely a parameter.

    Args:
        s: Path segment to check

    Returns:
        True if likely a parameter (UUID, numeric ID, etc.)
    """
    if not s or s.startswith('.'):
        return False

    # UUID
    if is_uuid(s):
        return True

    # Numeric ID (but not too short, could be version number)
    if is_numeric_id(s) and len(s) >= 3:
        return True

    # Long alphanumeric strings (likely IDs)
    if len(s) > 16 and s.isalnum():
        return True

    # Base64-like strings
    if len(s) > 20 and re.match(r'^[A-Za-z0-9_-]+$', s):
        return True

    return False


def sanitize_method_name(endpoint: str, method: str = 'GET') -> str:
    """
    Convert an endpoint pattern to a Python method name.

    Examples:
        "/api/users/{id}" -> "get_user"
        "/api/v1/products/{id}/reviews" -> "get_product_reviews"
        "/graphql" -> "post_graphql"

    Args:
        endpoint: URL path pattern (e.g., "/api/users/{id}")
        method: HTTP method (e.g., "GET", "POST")

    Returns:
        Python method name (snake_case)
    """
    # Remove leading/trailing slashes
    path = endpoint.strip('/')

    # Remove common prefixes
    for prefix in ['api/', 'v1/', 'v2/', 'v3/', 'api/v1/', 'api/v2/', 'api/v3/']:
        if path.startswith(prefix):
            path = path[len(prefix):]

    # Split by slashes and filter out parameter placeholders
    parts = []
    for segment in path.split('/'):
        # Skip parameter placeholders like {id}, {uuid}
        if segment.startswith('{') and segment.endswith('}'):
            continue
        # Skip numeric segments (version numbers)
        if segment.isdigit():
            continue
        # Add the segment
        if segment:
            parts.append(segment)

    # Join parts with underscores
    if not parts:
        # Fallback for paths like /api/{id}
        parts = ['item']

    base_name = '_'.join(parts)

    # Singularize if method suggests single item
    if method in ['GET', 'PUT', 'PATCH', 'DELETE']:
        # Check if path has parameter (suggesting single item)
        if '{id}' in endpoint or '{uuid}' in endpoint:
            # Simple singularization (remove trailing 's')
            if base_name.endswith('ies'):
                base_name = base_name[:-3] + 'y'
            elif base_name.endswith('s') and not base_name.endswith('ss'):
                base_name = base_name[:-1]

    # Add method prefix
    method_prefix = method.lower()
    if method_prefix == 'delete':
        method_prefix = 'remove'

    method_name = f"{method_prefix}_{base_name}"

    # Clean up any double underscores
    method_name = re.sub(r'_+', '_', method_name)

    # Ensure it's a valid Python identifier
    method_name = re.sub(r'[^a-z0-9_]', '_', method_name)

    return method_name


def extract_url_parts(url: str) -> Dict[str, Any]:
    """
    Extract components from a URL.

    Args:
        url: Full URL string

    Returns:
        Dictionary with scheme, netloc, path, query_params
    """
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    return {
        'scheme': parsed.scheme,
        'netloc': parsed.netloc,
        'hostname': parsed.hostname,
        'port': parsed.port,
        'path': parsed.path,
        'query': parsed.query,
        'query_params': query_params,
        'fragment': parsed.fragment,
    }


def get_base_url(url: str) -> str:
    """
    Extract base URL (scheme + netloc) from full URL.

    Args:
        url: Full URL string

    Returns:
        Base URL (e.g., "https://api.example.com")
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def normalize_path(path: str) -> str:
    """
    Normalize a URL path by removing trailing slashes.

    Args:
        path: URL path

    Returns:
        Normalized path
    """
    path = path.strip()
    # Remove trailing slash unless it's the root path
    if len(path) > 1 and path.endswith('/'):
        path = path[:-1]
    return path


def get_request_body(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract and parse request body from HAR entry.

    Args:
        entry: HAR entry dictionary

    Returns:
        Parsed request body as dict, or None if not JSON
    """
    request = entry.get('request', {})
    post_data = request.get('postData', {})

    mime_type = post_data.get('mimeType', '')
    text = post_data.get('text', '')

    if 'json' in mime_type.lower():
        return parse_json_safe(text)

    return None


def get_response_body(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Extract and parse response body from HAR entry.

    Args:
        entry: HAR entry dictionary

    Returns:
        Parsed response body as dict, or None if not JSON
    """
    response = entry.get('response', {})
    content = response.get('content', {})

    mime_type = content.get('mimeType', '')
    text = content.get('text', '')

    if 'json' in mime_type.lower():
        return parse_json_safe(text)

    return None


def get_request_headers(entry: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract request headers as a dictionary.

    Args:
        entry: HAR entry dictionary

    Returns:
        Dictionary of header name -> value
    """
    request = entry.get('request', {})
    headers = request.get('headers', [])

    result = {}
    for header in headers:
        if isinstance(header, dict):
            name = header.get('name', '')
            value = header.get('value', '')
            if name:
                result[name] = value

    return result


def get_response_headers(entry: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract response headers as a dictionary.

    Args:
        entry: HAR entry dictionary

    Returns:
        Dictionary of header name -> value
    """
    response = entry.get('response', {})
    headers = response.get('headers', [])

    result = {}
    for header in headers:
        if isinstance(header, dict):
            name = header.get('name', '')
            value = header.get('value', '')
            if name:
                result[name] = value

    return result


def save_json(data: Dict[str, Any], output_path: Path, pretty: bool = True) -> None:
    """
    Save data as JSON file.

    Args:
        data: Data to save
        output_path: Output file path
        pretty: Whether to pretty-print the JSON
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        if pretty:
            json.dump(data, f, indent=2, ensure_ascii=False)
        else:
            json.dump(data, f, ensure_ascii=False)
