#!/usr/bin/env python3
"""
HAR Validator - Validate generated API client against HAR analysis.

This script validates that a generated API client properly implements
all endpoints found in the HAR analysis.

Usage:
    python har_validate.py <api_client.py> <analysis.json>
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple


def load_analysis(analysis_path: Path) -> Dict[str, Any]:
    """Load analysis JSON file."""
    if not analysis_path.exists():
        raise FileNotFoundError(f"Analysis file not found: {analysis_path}")

    with open(analysis_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_client_code(client_path: Path) -> str:
    """Load API client Python code."""
    if not client_path.exists():
        raise FileNotFoundError(f"Client file not found: {client_path}")

    with open(client_path, 'r', encoding='utf-8') as f:
        return f.read()


def parse_client_methods(client_code: str) -> Set[str]:
    """
    Extract method names from API client code.

    Args:
        client_code: Python source code

    Returns:
        Set of method names (excluding private methods and __init__)
    """
    methods = set()

    try:
        tree = ast.parse(client_code)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        method_name = item.name
                        # Skip private methods and __init__
                        if not method_name.startswith('_'):
                            methods.add(method_name)

    except SyntaxError:
        # If AST parsing fails, fall back to regex
        pattern = r'def\s+([a-z_][a-z0-9_]*)\s*\('
        matches = re.findall(pattern, client_code, re.MULTILINE)
        methods = set(m for m in matches if not m.startswith('_'))

    return methods


def endpoint_to_method_names(pattern: str, methods: List[str]) -> List[str]:
    """
    Generate expected method names from endpoint pattern.

    Args:
        pattern: Endpoint pattern (e.g., "/api/users/{id}")
        methods: HTTP methods (e.g., ["GET", "POST"])

    Returns:
        List of expected Python method names
    """
    # Remove leading/trailing slashes
    path = pattern.strip('/')

    # Remove common prefixes
    for prefix in ['api/', 'v1/', 'v2/', 'v3/', 'api/v1/', 'api/v2/', 'api/v3/']:
        if path.startswith(prefix):
            path = path[len(prefix):]

    # Split and filter
    parts = []
    for segment in path.split('/'):
        # Skip parameter placeholders
        if segment.startswith('{') and segment.endswith('}'):
            continue
        # Skip numeric segments
        if segment.isdigit():
            continue
        if segment:
            parts.append(segment)

    if not parts:
        parts = ['item']

    base_name = '_'.join(parts)

    # Singularize if needed (simple approach)
    method_names = []
    for method in methods:
        name = base_name
        if method in ['GET', 'PUT', 'PATCH', 'DELETE']:
            # Check if pattern has parameter (suggests single item)
            if '{id}' in pattern or '{uuid}' in pattern:
                # Singularize
                if name.endswith('ies'):
                    name = name[:-3] + 'y'
                elif name.endswith('s') and not name.endswith('ss'):
                    name = name[:-1]

        # Add method prefix
        prefix = method.lower()
        if prefix == 'delete':
            prefix = 'remove'

        method_name = f"{prefix}_{name}"
        method_name = re.sub(r'_+', '_', method_name)
        method_name = re.sub(r'[^a-z0-9_]', '_', method_name)

        method_names.append(method_name)

    return method_names


def check_endpoint_coverage(
    client_code: str,
    client_methods: Set[str],
    endpoints: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Check if all endpoints from analysis are implemented.

    Args:
        client_code: Python source code
        client_methods: Set of implemented method names
        endpoints: List of endpoint dictionaries from analysis

    Returns:
        Tuple of (issues, coverage_stats)
    """
    issues = []
    endpoints_covered = 0
    endpoints_total = 0

    for endpoint in endpoints:
        pattern = endpoint['pattern']
        methods = endpoint['methods']

        # Generate expected method names
        expected_names = endpoint_to_method_names(pattern, methods)

        # Check if any expected name is implemented
        found = any(name in client_methods for name in expected_names)

        if found:
            endpoints_covered += 1
        else:
            # Not implemented
            for method in methods:
                issues.append({
                    'severity': 'error',
                    'category': 'missing_endpoint',
                    'message': f"Endpoint {method} {pattern} not implemented (expected method: {expected_names[0]})",
                    'line': None,
                })

        endpoints_total += 1

    coverage = {
        'endpoints_covered': endpoints_covered,
        'endpoints_total': endpoints_total,
        'percentage': round(endpoints_covered / endpoints_total * 100, 1) if endpoints_total > 0 else 0,
    }

    return issues, coverage


def check_auth_implementation(
    client_code: str,
    auth: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Check if authentication is properly implemented.

    Args:
        client_code: Python source code
        auth: Authentication dict from analysis

    Returns:
        List of issues
    """
    issues = []
    auth_type = auth.get('type', 'none')

    if auth_type == 'none':
        # No auth required
        return issues

    # Check for auth implementation
    auth_indicators = {
        'bearer_token': ['Authorization', 'Bearer', 'token'],
        'api_key_header': ['X-API-Key', 'api_key', 'apikey'],
        'api_key_query': ['api_key', 'apikey', 'params'],
        'session_cookie': ['cookie', 'session'],
        'basic_auth': ['Authorization', 'Basic', 'credentials'],
    }

    expected_indicators = auth_indicators.get(auth_type, [])
    found_any = any(indicator.lower() in client_code.lower() for indicator in expected_indicators)

    if not found_any:
        issues.append({
            'severity': 'warning',
            'category': 'missing_auth',
            'message': f"Authentication type '{auth_type}' not implemented (expected {auth['header_name'] or 'session handling'})",
            'line': None,
        })

    return issues


def check_error_handling(client_code: str) -> List[Dict[str, Any]]:
    """
    Check if proper error handling is implemented.

    Args:
        client_code: Python source code

    Returns:
        List of issues
    """
    issues = []

    # Check for try-except blocks
    has_try_except = 'try:' in client_code and 'except' in client_code

    # Check for custom exceptions
    has_custom_exceptions = 'class' in client_code and 'Error' in client_code and 'Exception' in client_code

    # Check for response validation
    has_response_check = 'raise_for_status' in client_code or 'status_code' in client_code

    if not has_try_except:
        issues.append({
            'severity': 'warning',
            'category': 'missing_error_handling',
            'message': 'No try-except blocks found for error handling',
            'line': None,
        })

    if not has_custom_exceptions:
        issues.append({
            'severity': 'info',
            'category': 'missing_custom_exceptions',
            'message': 'No custom exception classes defined',
            'line': None,
        })

    if not has_response_check:
        issues.append({
            'severity': 'warning',
            'category': 'missing_response_validation',
            'message': 'No response status validation found',
            'line': None,
        })

    return issues


def check_type_hints(client_code: str) -> List[Dict[str, Any]]:
    """
    Check if type hints are used.

    Args:
        client_code: Python source code

    Returns:
        List of issues
    """
    issues = []

    # Check for typing imports
    has_typing_import = 'from typing import' in client_code or 'import typing' in client_code

    # Check for type hints in code (look for -> or :)
    has_type_hints = ' -> ' in client_code or ': Dict' in client_code or ': List' in client_code

    if not has_typing_import or not has_type_hints:
        issues.append({
            'severity': 'info',
            'category': 'missing_type_hints',
            'message': 'Type hints not fully implemented',
            'line': None,
        })

    return issues


def validate_client(
    client_path: Path,
    analysis: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate API client against HAR analysis.

    Args:
        client_path: Path to API client Python file
        analysis: HAR analysis dictionary

    Returns:
        Validation report with score, issues, coverage
    """
    client_code = load_client_code(client_path)
    client_methods = parse_client_methods(client_code)

    all_issues = []

    # Check endpoint coverage
    endpoints = analysis.get('endpoints', [])
    endpoint_issues, coverage = check_endpoint_coverage(client_code, client_methods, endpoints)
    all_issues.extend(endpoint_issues)

    # Check authentication
    auth = analysis.get('authentication', {})
    auth_issues = check_auth_implementation(client_code, auth)
    all_issues.extend(auth_issues)

    # Check error handling
    error_issues = check_error_handling(client_code)
    all_issues.extend(error_issues)

    # Check type hints
    type_issues = check_type_hints(client_code)
    all_issues.extend(type_issues)

    # Calculate score
    # Base score starts at 100
    score = 100

    # Deduct points for errors
    error_count = len([i for i in all_issues if i['severity'] == 'error'])
    warning_count = len([i for i in all_issues if i['severity'] == 'warning'])
    info_count = len([i for i in all_issues if i['severity'] == 'info'])

    score -= error_count * 15  # -15 points per error
    score -= warning_count * 5   # -5 points per warning
    score -= info_count * 2      # -2 points per info

    # Bonus points for high coverage
    if coverage['percentage'] == 100:
        score += 10

    # Ensure score is between 0 and 100
    score = max(0, min(100, score))

    report = {
        'score': score,
        'issues': all_issues,
        'coverage': coverage,
        'summary': {
            'errors': error_count,
            'warnings': warning_count,
            'info': info_count,
            'total_issues': len(all_issues),
        },
    }

    return report


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description='Validate generated API client against HAR analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate API client
  python har_validate.py api_client.py analysis.json

  # Save validation report to file
  python har_validate.py api_client.py analysis.json --output report.json
        """
    )

    parser.add_argument(
        'client',
        type=str,
        help='API client Python file path'
    )

    parser.add_argument(
        'analysis',
        type=str,
        help='HAR analysis JSON file path'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Output validation report JSON file path'
    )

    args = parser.parse_args()

    # Validate input files
    client_path = Path(args.client).expanduser().resolve()
    analysis_path = Path(args.analysis).expanduser().resolve()

    if not client_path.exists():
        print(f"Error: Client file not found: {client_path}", file=sys.stderr)
        sys.exit(1)

    if not analysis_path.exists():
        print(f"Error: Analysis file not found: {analysis_path}", file=sys.stderr)
        sys.exit(1)

    try:
        # Load analysis
        analysis = load_analysis(analysis_path)

        # Validate client
        report = validate_client(client_path, analysis)

        # Save or print report
        if args.output:
            output_path = Path(args.output).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2)
            print(f"Validation report saved to: {output_path}")
        else:
            print(json.dumps(report, indent=2))

        # Exit with error code if score < 90
        if report['score'] < 90:
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
