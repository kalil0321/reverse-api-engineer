#!/usr/bin/env python3
"""
HAR Filter - Filter HAR files to API-relevant entries only.

This script removes static assets, analytics, tracking, and CDN resources
from HAR files, keeping only API-relevant requests.

Usage:
    python har_filter.py <input.har> --output <filtered.har> [--stats]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any
from urllib.parse import urlparse

from har_utils import load_har, save_json, get_content_type, extract_url_parts


# File extensions to skip (static assets)
SKIP_EXTENSIONS = {
    # JavaScript/CSS
    '.js', '.jsx', '.ts', '.tsx', '.css', '.scss', '.sass', '.less',
    # Images
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.bmp', '.tiff',
    # Fonts
    '.woff', '.woff2', '.ttf', '.otf', '.eot',
    # Media
    '.mp4', '.webm', '.ogg', '.mp3', '.wav', '.flac',
    # Documents (usually not API responses)
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.tar', '.gz',
    # Other static files
    '.xml', '.txt', '.csv', '.html', '.htm',
    # Source maps and manifests
    '.map', '.manifest',
}

# Domain patterns to skip (analytics, tracking, CDN)
SKIP_DOMAIN_PATTERNS = [
    # Analytics
    'google-analytics.com',
    'analytics.google.com',
    'googletagmanager.com',
    'doubleclick.net',
    'facebook.net',
    'connect.facebook.net',
    'mixpanel.com',
    'segment.com',
    'segment.io',
    'amplitude.com',
    'hotjar.com',
    'fullstory.com',
    'heap.io',
    'clarity.ms',
    # Ads
    'googlesyndication.com',
    'adservice.google.com',
    'advertising.com',
    # CDN patterns
    'cloudfront.net',
    'fastly.net',
    'akamai.net',
    'akamaihd.net',
    'cdn.jsdelivr.net',
    'unpkg.com',
    'cdnjs.cloudflare.com',
    # Other tracking
    'bugsnag.com',
    'sentry.io',
    'newrelic.com',
]

# URL patterns to skip (includes path components for tracking endpoints)
SKIP_URL_PATTERNS = [
    # Social media tracking pixels
    'facebook.com/tr',
    'twitter.com/i/',
    'linkedin.com/px/',
    'snapchat.com/tr',
]

# URL path patterns that indicate API endpoints
API_PATH_PATTERNS = [
    '/api/',
    '/v1/',
    '/v2/',
    '/v3/',
    '/v4/',
    '/rest/',
    '/graphql',
    '/query',
    '/mutation',
    '/rpc/',
    '/_api/',
]


def get_skip_extensions() -> set:
    """Get set of file extensions to skip."""
    return SKIP_EXTENSIONS


def get_skip_domain_patterns() -> list:
    """Get list of domain patterns to skip."""
    return SKIP_DOMAIN_PATTERNS


def should_skip_domain(hostname: str) -> bool:
    """
    Check if a domain should be skipped.

    Args:
        hostname: Hostname from URL

    Returns:
        True if domain should be skipped
    """
    if not hostname:
        return False

    hostname_lower = hostname.lower()

    for pattern in SKIP_DOMAIN_PATTERNS:
        if pattern in hostname_lower:
            return True

    # Skip common CDN patterns like cdn.*, static.*, assets.*
    if hostname_lower.startswith(('cdn.', 'static.', 'assets.', 'media.')):
        return True

    return False


def should_skip_url(url: str) -> bool:
    """
    Check if a full URL should be skipped based on URL patterns.

    Args:
        url: Full URL string

    Returns:
        True if URL should be skipped
    """
    if not url:
        return False

    url_lower = url.lower()

    for pattern in SKIP_URL_PATTERNS:
        if pattern in url_lower:
            return True

    return False


def should_skip_extension(path: str) -> bool:
    """
    Check if file extension should be skipped.

    Args:
        path: URL path

    Returns:
        True if extension should be skipped
    """
    path_lower = path.lower()

    for ext in SKIP_EXTENSIONS:
        if path_lower.endswith(ext):
            return True

    return False


def has_api_pattern(path: str) -> bool:
    """
    Check if path contains API patterns.

    Args:
        path: URL path

    Returns:
        True if path looks like an API endpoint
    """
    path_lower = path.lower()

    for pattern in API_PATH_PATTERNS:
        if pattern in path_lower:
            return True

    return False


def is_xhr_fetch(entry: Dict[str, Any]) -> bool:
    """
    Check if request is XHR/Fetch (likely an API call).

    Args:
        entry: HAR entry

    Returns:
        True if request appears to be XHR/Fetch
    """
    request = entry.get('request', {})
    headers = request.get('headers', [])

    # Check for XHR/Fetch indicators in headers
    for header in headers:
        if not isinstance(header, dict):
            continue

        name = header.get('name', '').lower()
        value = header.get('value', '').lower()

        # X-Requested-With: XMLHttpRequest
        if name == 'x-requested-with' and 'xmlhttprequest' in value:
            return True

        # Fetch API usually sets specific Accept headers
        if name == 'accept' and ('application/json' in value or 'application/*' in value):
            return True

    return False


def is_json_response(entry: Dict[str, Any]) -> bool:
    """
    Check if response is JSON.

    Args:
        entry: HAR entry

    Returns:
        True if response content-type is JSON
    """
    content_type = get_content_type(entry)
    if content_type:
        return 'json' in content_type.lower()
    return False


def categorize_entry(entry: Dict[str, Any]) -> str:
    """
    Categorize a HAR entry.

    Args:
        entry: HAR entry

    Returns:
        Category: "api", "static", "analytics", "cdn", or "other"
    """
    request = entry.get('request', {})
    url = request.get('url', '')

    parts = extract_url_parts(url)
    hostname = parts.get('hostname', '')
    path = parts.get('path', '')

    # Check URL patterns first (includes path components)
    if should_skip_url(url):
        return 'analytics'

    # Check domain-based skips
    if should_skip_domain(hostname):
        # Categorize analytics vs CDN
        hostname_lower = hostname.lower()
        if any(term in hostname_lower for term in ['analytics', 'tracking', 'ads', 'doubleclick']):
            return 'analytics'
        return 'cdn'

    # Check file extension
    if should_skip_extension(path):
        return 'static'

    # Check for API patterns
    if has_api_pattern(path):
        return 'api'

    # Check if XHR/Fetch
    if is_xhr_fetch(entry):
        return 'api'

    # Check if JSON response
    if is_json_response(entry):
        return 'api'

    return 'other'


def is_api_endpoint(entry: Dict[str, Any]) -> bool:
    """
    Determine if a HAR entry is an API endpoint.

    Args:
        entry: HAR entry

    Returns:
        True if entry should be kept as API endpoint
    """
    category = categorize_entry(entry)
    return category == 'api'


def filter_har(har_path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Filter HAR file to API-relevant entries only.

    Args:
        har_path: Path to input HAR file

    Returns:
        Tuple of (filtered_har, statistics)
    """
    har_data = load_har(har_path)

    entries = har_data['log']['entries']
    total_entries = len(entries)

    # Categorize all entries
    categorized = {
        'api': [],
        'static': [],
        'analytics': [],
        'cdn': [],
        'other': [],
    }

    for entry in entries:
        category = categorize_entry(entry)
        categorized[category].append(entry)

    # Build filtered HAR with only API entries
    filtered_har = {
        'log': {
            'version': har_data['log'].get('version', '1.2'),
            'creator': har_data['log'].get('creator', {}),
            'pages': har_data['log'].get('pages', []),
            'entries': categorized['api'],
        }
    }

    # Collect API patterns found
    api_patterns = set()
    for entry in categorized['api']:
        request = entry.get('request', {})
        url = request.get('url', '')
        parts = extract_url_parts(url)
        path = parts.get('path', '')

        for pattern in API_PATH_PATTERNS:
            if pattern in path.lower():
                api_patterns.add(pattern)

    # Build statistics
    stats = {
        'total_entries': total_entries,
        'filtered_entries': len(categorized['api']),
        'removed_static': len(categorized['static']),
        'removed_analytics': len(categorized['analytics']),
        'removed_cdn': len(categorized['cdn']),
        'removed_other': len(categorized['other']),
        'api_patterns_found': sorted(list(api_patterns)),
        'filter_ratio': round(len(categorized['api']) / total_entries * 100, 1) if total_entries > 0 else 0,
    }

    return filtered_har, stats


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description='Filter HAR files to API-relevant entries only',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Filter HAR and save to new file
  python har_filter.py recording.har --output filtered.har

  # Filter and display stats
  python har_filter.py recording.har --output filtered.har --stats

  # Stats only (no output file)
  python har_filter.py recording.har --stats
        """
    )

    parser.add_argument(
        'input',
        type=str,
        help='Input HAR file path'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Output filtered HAR file path'
    )

    parser.add_argument(
        '--stats',
        action='store_true',
        help='Print filtering statistics'
    )

    args = parser.parse_args()

    # Validate input file
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        # Filter HAR
        filtered_har, stats = filter_har(input_path)

        # Save filtered HAR if output specified
        if args.output:
            output_path = Path(args.output).expanduser().resolve()
            save_json(filtered_har, output_path, pretty=True)
            stats['filtered_har_path'] = str(output_path)

        # Print stats if requested
        if args.stats:
            print(json.dumps(stats, indent=2))
        elif not args.output:
            # If neither output nor stats requested, print stats by default
            print(json.dumps(stats, indent=2))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
