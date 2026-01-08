#!/usr/bin/env python3
"""
HAR Analyzer - Extract structured endpoint information from HAR files.

This script analyzes filtered HAR files to extract:
- API endpoints with path parameters
- Authentication patterns
- Request/response schemas
- Pagination patterns
- Query parameters

Usage:
    python har_analyze.py <filtered.har> --output <analysis.json>
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from urllib.parse import urlparse, parse_qs

from har_utils import (
    load_har,
    save_json,
    extract_url_parts,
    get_base_url,
    is_path_parameter,
    get_request_body,
    get_response_body,
    get_request_headers,
    get_response_headers,
)


def detect_auth(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Detect authentication patterns from HAR entries.

    Args:
        entries: List of HAR entries

    Returns:
        Dictionary describing authentication mechanism
    """
    auth_headers = defaultdict(int)
    auth_cookies = defaultdict(int)
    auth_query_params = defaultdict(int)

    for entry in entries:
        request_headers = get_request_headers(entry)
        request = entry.get('request', {})
        url = request.get('url', '')
        parts = extract_url_parts(url)
        query_params = parts.get('query_params', {})

        # Check for Authorization header
        for header_name, header_value in request_headers.items():
            header_lower = header_name.lower()

            if header_lower == 'authorization':
                # Determine auth type from value
                value_lower = header_value.lower()
                if value_lower.startswith('bearer '):
                    auth_headers['bearer_token'] += 1
                elif value_lower.startswith('basic '):
                    auth_headers['basic_auth'] += 1
                elif 'oauth' in value_lower:
                    auth_headers['oauth'] += 1
                else:
                    auth_headers['unknown_token'] += 1

            # Check for X-API-Key or similar
            elif 'api' in header_lower and 'key' in header_lower:
                auth_headers['api_key_header'] += 1

            # Check for CSRF tokens
            elif 'csrf' in header_lower or 'xsrf' in header_lower:
                auth_headers['csrf_token'] += 1

            # Check for session tokens
            elif 'token' in header_lower:
                auth_headers['custom_token'] += 1

            # Check for cookies
            elif header_lower == 'cookie':
                if 'session' in header_value.lower():
                    auth_cookies['session_cookie'] += 1
                elif 'token' in header_value.lower():
                    auth_cookies['token_cookie'] += 1
                else:
                    auth_cookies['generic_cookie'] += 1

        # Check for API keys in query parameters
        for param_name in query_params.keys():
            param_lower = param_name.lower()
            if 'api' in param_lower and 'key' in param_lower:
                auth_query_params['api_key_query'] += 1
            elif 'token' in param_lower or 'auth' in param_lower:
                auth_query_params['token_query'] += 1

    # Determine primary auth method
    all_auth_methods = {}
    all_auth_methods.update(auth_headers)
    all_auth_methods.update(auth_cookies)
    all_auth_methods.update(auth_query_params)

    if not all_auth_methods:
        return {
            'type': 'none',
            'location': None,
            'header_name': None,
            'pattern': None,
            'description': 'No authentication detected (public API)',
        }

    # Find most common auth method
    primary_method = max(all_auth_methods.items(), key=lambda x: x[1])[0]

    # Map to structured auth info
    auth_info = {
        'type': primary_method,
        'detected_methods': list(all_auth_methods.keys()),
    }

    # Add details based on type
    if primary_method == 'bearer_token':
        auth_info.update({
            'location': 'header',
            'header_name': 'Authorization',
            'pattern': 'Bearer {token}',
            'description': 'JWT or Bearer token authentication',
        })
    elif primary_method == 'api_key_header':
        auth_info.update({
            'location': 'header',
            'header_name': 'X-API-Key',  # Common convention
            'pattern': '{api_key}',
            'description': 'API key in header',
        })
    elif primary_method == 'api_key_query':
        auth_info.update({
            'location': 'query',
            'header_name': None,
            'pattern': '?api_key={key}',
            'description': 'API key in query parameter',
        })
    elif 'session_cookie' in primary_method or 'cookie' in primary_method:
        auth_info.update({
            'location': 'cookie',
            'header_name': 'Cookie',
            'pattern': 'session={session_id}',
            'description': 'Session-based authentication with cookies',
        })
    elif primary_method == 'basic_auth':
        auth_info.update({
            'location': 'header',
            'header_name': 'Authorization',
            'pattern': 'Basic {base64_credentials}',
            'description': 'HTTP Basic Authentication',
        })
    else:
        auth_info.update({
            'location': 'header',
            'header_name': 'Authorization',
            'pattern': '{token}',
            'description': f'Custom authentication: {primary_method}',
        })

    return auth_info


def infer_path_params(paths: List[str]) -> str:
    """
    Infer path parameter pattern from multiple paths.

    Example:
        ["/api/users/123", "/api/users/456"] -> "/api/users/{id}"

    Args:
        paths: List of URL paths

    Returns:
        Path pattern with {param} placeholders
    """
    if not paths:
        return ''

    # Split all paths into segments
    all_segments = [path.strip('/').split('/') for path in paths]

    # Find common length
    min_length = min(len(segments) for segments in all_segments)

    # Build pattern
    pattern_segments = []
    for i in range(min_length):
        segment_values = [segments[i] for segments in all_segments]

        # Check if all values are the same (static segment)
        if len(set(segment_values)) == 1:
            pattern_segments.append(segment_values[0])
        else:
            # Values differ - likely a parameter
            # Check what type of parameter
            if all(is_path_parameter(val) for val in segment_values):
                # Determine parameter name
                if all(val.isdigit() for val in segment_values):
                    param_name = 'id'
                else:
                    param_name = 'uuid'  # or 'id' for UUIDs
                pattern_segments.append(f'{{{param_name}}}')
            else:
                # Mixed values - keep first as example
                pattern_segments.append(segment_values[0])

    pattern = '/' + '/'.join(pattern_segments)
    return pattern


def group_endpoints(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Group HAR entries by endpoint pattern.

    Args:
        entries: List of HAR entries

    Returns:
        List of endpoint dictionaries with patterns and metadata
    """
    # Group by method + base pattern
    groups = defaultdict(lambda: {
        'urls': [],
        'entries': [],
        'query_params': defaultdict(int),
        'request_bodies': [],
        'response_bodies': [],
    })

    for entry in entries:
        request = entry.get('request', {})
        method = request.get('method', 'GET')
        url = request.get('url', '')

        parts = extract_url_parts(url)
        path = parts.get('path', '')
        query_params = parts.get('query_params', {})

        # Create a preliminary grouping key
        # We'll refine this later to detect path parameters
        key = (method, path)
        groups[key]['urls'].append(url)
        groups[key]['entries'].append(entry)

        # Track query parameters
        for param_name in query_params.keys():
            groups[key]['query_params'][param_name] += 1

        # Collect request/response bodies
        req_body = get_request_body(entry)
        if req_body:
            groups[key]['request_bodies'].append(req_body)

        resp_body = get_response_body(entry)
        if resp_body:
            groups[key]['response_bodies'].append(resp_body)

    # Now refine groups to detect path parameters
    refined_endpoints = []

    for (method, path), group_data in groups.items():
        # If multiple URLs with same method+path structure, infer pattern
        unique_paths = list(set(parts.get('path', '') for parts in
                                [extract_url_parts(url) for url in group_data['urls']]))

        if len(unique_paths) > 1:
            # Multiple different paths - infer pattern
            pattern = infer_path_params(unique_paths)
        else:
            pattern = path

        # Determine required vs optional query params
        total_calls = len(group_data['entries'])
        required_params = []
        optional_params = []

        for param_name, count in group_data['query_params'].items():
            if count == total_calls:
                required_params.append(param_name)
            else:
                optional_params.append(param_name)

        # Merge request/response bodies to infer schema
        request_schema = merge_schemas(group_data['request_bodies'])
        response_schema = merge_schemas(group_data['response_bodies'])

        # Check if auth required (heuristic: has auth headers)
        has_auth = any(
            'authorization' in get_request_headers(entry).keys() or
            'cookie' in (h.lower() for h in get_request_headers(entry).keys())
            for entry in group_data['entries']
        )

        endpoint_info = {
            'pattern': pattern,
            'methods': [method],
            'calls_observed': total_calls,
            'query_params': {
                'required': sorted(required_params),
                'optional': sorted(optional_params),
            },
            'request_body_schema': request_schema,
            'response_schema': response_schema,
            'requires_auth': has_auth,
        }

        refined_endpoints.append(endpoint_info)

    # Merge endpoints with same pattern but different methods
    pattern_groups = defaultdict(list)
    for endpoint in refined_endpoints:
        pattern_groups[endpoint['pattern']].append(endpoint)

    final_endpoints = []
    for pattern, endpoints in pattern_groups.items():
        if len(endpoints) == 1:
            final_endpoints.append(endpoints[0])
        else:
            # Merge multiple methods for same pattern
            merged = {
                'pattern': pattern,
                'methods': sorted(set(method for ep in endpoints for method in ep['methods'])),
                'calls_observed': sum(ep['calls_observed'] for ep in endpoints),
                'query_params': endpoints[0]['query_params'],  # Use first as representative
                'request_body_schema': merge_schemas([ep['request_body_schema'] for ep in endpoints if ep['request_body_schema']]),
                'response_schema': merge_schemas([ep['response_schema'] for ep in endpoints if ep['response_schema']]),
                'requires_auth': any(ep['requires_auth'] for ep in endpoints),
            }
            final_endpoints.append(merged)

    # Sort by pattern for consistency
    final_endpoints.sort(key=lambda x: x['pattern'])

    return final_endpoints


def merge_schemas(bodies: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Merge multiple JSON bodies to infer a common schema.

    Args:
        bodies: List of JSON bodies

    Returns:
        Inferred schema or None
    """
    if not bodies:
        return None

    # Simple schema inference: collect all keys and their types
    schema = {}

    for body in bodies:
        if not isinstance(body, dict):
            continue

        for key, value in body.items():
            if key not in schema:
                schema[key] = type(value).__name__

    return schema if schema else None


def detect_pagination(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Detect pagination patterns from HAR entries.

    Args:
        entries: List of HAR entries

    Returns:
        Dictionary describing pagination pattern
    """
    pagination_params = defaultdict(int)

    for entry in entries:
        request = entry.get('request', {})
        url = request.get('url', '')
        parts = extract_url_parts(url)
        query_params = parts.get('query_params', {})

        # Check for common pagination parameters
        for param_name in query_params.keys():
            param_lower = param_name.lower()

            if param_lower in ['page', 'p']:
                pagination_params['page'] += 1
            elif param_lower in ['limit', 'per_page', 'page_size', 'size']:
                pagination_params['limit'] += 1
            elif param_lower in ['offset', 'skip']:
                pagination_params['offset'] += 1
            elif param_lower in ['cursor', 'next', 'continuation']:
                pagination_params['cursor'] += 1

    if not pagination_params:
        return {
            'detected': False,
            'type': None,
            'params': [],
        }

    # Determine pagination type
    if 'page' in pagination_params:
        return {
            'detected': True,
            'type': 'page',
            'params': ['page', 'limit'] if 'limit' in pagination_params else ['page'],
            'description': 'Page-based pagination',
        }
    elif 'offset' in pagination_params:
        return {
            'detected': True,
            'type': 'offset',
            'params': ['offset', 'limit'] if 'limit' in pagination_params else ['offset'],
            'description': 'Offset-based pagination',
        }
    elif 'cursor' in pagination_params:
        return {
            'detected': True,
            'type': 'cursor',
            'params': ['cursor', 'limit'] if 'limit' in pagination_params else ['cursor'],
            'description': 'Cursor-based pagination',
        }
    else:
        return {
            'detected': True,
            'type': 'unknown',
            'params': list(pagination_params.keys()),
            'description': 'Custom pagination pattern',
        }


def analyze_har(har: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze HAR file and extract structured information.

    Args:
        har: Parsed HAR data

    Returns:
        Analysis dictionary with endpoints, auth, pagination, etc.
    """
    entries = har['log']['entries']

    if not entries:
        return {
            'error': 'No entries found in HAR file',
            'base_url': None,
            'authentication': None,
            'endpoints': [],
            'pagination': None,
        }

    # Determine base URL (most common)
    base_urls = defaultdict(int)
    for entry in entries:
        request = entry.get('request', {})
        url = request.get('url', '')
        base = get_base_url(url)
        if base:
            base_urls[base] += 1

    base_url = max(base_urls.items(), key=lambda x: x[1])[0] if base_urls else None

    # Detect authentication
    authentication = detect_auth(entries)

    # Group and analyze endpoints
    endpoints = group_endpoints(entries)

    # Detect pagination
    pagination = detect_pagination(entries)

    # Build analysis result
    analysis = {
        'base_url': base_url,
        'authentication': authentication,
        'endpoints': endpoints,
        'pagination': pagination,
        'total_entries_analyzed': len(entries),
        'unique_endpoints': len(endpoints),
    }

    return analysis


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description='Analyze HAR files to extract endpoint information',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze HAR and save to JSON
  python har_analyze.py filtered.har --output analysis.json

  # Print analysis to stdout
  python har_analyze.py filtered.har
        """
    )

    parser.add_argument(
        'input',
        type=str,
        help='Input HAR file path (filtered recommended)'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Output analysis JSON file path'
    )

    args = parser.parse_args()

    # Validate input file
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        # Load and analyze HAR
        har_data = load_har(input_path)
        analysis = analyze_har(har_data)

        # Save or print analysis
        if args.output:
            output_path = Path(args.output).expanduser().resolve()
            save_json(analysis, output_path, pretty=True)
            print(f"Analysis saved to: {output_path}")
        else:
            print(json.dumps(analysis, indent=2))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
