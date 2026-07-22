"""
Apple Jobs API Client

This module provides a Python client for interacting with the Apple Jobs API.
It handles authentication, CSRF token management, and provides methods for
searching and retrieving job postings from jobs.apple.com.

Author: Generated from HAR file analysis
Date: 2025-12-22
"""

import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Location:
    """Represents a job location."""
    postLocationId: str
    city: str
    stateProvince: str
    countryName: str
    metro: str
    region: str
    name: str
    countryID: str
    level: int


@dataclass
class Team:
    """Represents a team/department."""
    teamName: str
    teamID: str
    teamCode: str


@dataclass
class Job:
    """Represents an Apple job posting."""
    id: str
    positionId: str
    postingTitle: str
    postingDate: str
    jobSummary: str
    locations: List[Location]
    team: Team
    reqId: str
    standardWeeklyHours: int
    homeOffice: bool
    isMultiLocation: bool
    transformedPostingTitle: str

    @property
    def url(self) -> str:
        """Generate the job URL."""
        return f"https://jobs.apple.com/en-us/details/{self.positionId}/{self.transformedPostingTitle}"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Job':
        """Create a Job instance from API response data."""
        locations = [Location(**loc) for loc in data.get('locations', [])]
        team = Team(**data.get('team', {}))

        return cls(
            id=data.get('id', ''),
            positionId=data.get('positionId', ''),
            postingTitle=data.get('postingTitle', ''),
            postingDate=data.get('postingDate', ''),
            jobSummary=data.get('jobSummary', ''),
            locations=locations,
            team=team,
            reqId=data.get('reqId', ''),
            standardWeeklyHours=data.get('standardWeeklyHours', 0),
            homeOffice=data.get('homeOffice', False),
            isMultiLocation=data.get('isMultiLocation', False),
            transformedPostingTitle=data.get('transformedPostingTitle', '')
        )


class AppleJobsAPI:
    """
    Client for interacting with the Apple Jobs API.

    This client handles:
    - CSRF token management
    - Session management with proper cookies
    - Job search with filters and pagination
    - Rate limiting and error handling

    Example usage:
        >>> client = AppleJobsAPI()
        >>> jobs = client.search_jobs(query="engineer", page=1)
        >>> for job in jobs:
        ...     print(f"{job.postingTitle} - {job.url}")
    """

    BASE_URL = "https://jobs.apple.com"
    API_BASE = f"{BASE_URL}/api/v1"

    def __init__(self, locale: str = "en-us"):
        """
        Initialize the Apple Jobs API client.

        Args:
            locale: The locale to use for job searches (e.g., "en-us", "fr-fr")
        """
        self.locale = locale
        self.session = requests.Session()
        self._csrf_token: Optional[str] = None

        # Set default headers that match browser behavior
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': self.BASE_URL,
            'Referer': f'{self.BASE_URL}/{locale}/search',
            'Content-Type': 'application/json',
            'browserlocale': locale,
            'locale': locale.replace('-', '_').upper() if locale else 'EN_US',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
        })

        logger.info(f"Initialized Apple Jobs API client with locale: {locale}")

    def _get_csrf_token(self) -> str:
        """
        Retrieve a CSRF token from the API.

        The CSRF token is required for all POST requests to the search endpoint.
        It's returned in the response headers as 'x-apple-csrf-token'.

        Returns:
            The CSRF token string

        Raises:
            requests.RequestException: If the token request fails
        """
        try:
            response = self.session.get(f"{self.API_BASE}/CSRFToken", timeout=15)
            response.raise_for_status()

            csrf_token = response.headers.get('x-apple-csrf-token')
            if not csrf_token:
                raise ValueError("No CSRF token found in response headers")

            logger.debug("Retrieved CSRF token")
            return csrf_token

        except requests.RequestException as e:
            logger.error(f"Failed to retrieve CSRF token: {e}")
            raise

    def _ensure_csrf_token(self) -> None:
        """Ensure we have a valid CSRF token, fetching a new one if needed."""
        if not self._csrf_token:
            self._csrf_token = self._get_csrf_token()
            self.session.headers.update({
                'x-apple-csrf-token': self._csrf_token
            })

    def search_jobs(
        self,
        query: str = "",
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        sort: str = "",
        locale: Optional[str] = None
    ) -> List[Job]:
        """
        Search for job postings on Apple's job site.

        Args:
            query: Search query string (searches in job title and description)
            filters: Dictionary of filters to apply. Common filters include:
                - postLocation: List of location IDs (e.g., ["postLocation-FRA"])
                - team: List of team IDs
                - role: List of role types
            page: Page number (1-indexed)
            sort: Sort order (empty string for default)
            locale: Override the default locale for this search

        Returns:
            List of Job objects matching the search criteria

        Raises:
            requests.RequestException: If the API request fails

        Example:
            >>> # Search for engineering jobs in France
            >>> jobs = client.search_jobs(
            ...     query="engineer",
            ...     filters={"postLocation": ["postLocation-FRA"]},
            ...     page=1
            ... )
        """
        self._ensure_csrf_token()

        search_locale = locale or self.locale

        # Build request payload matching the API specification
        payload = {
            "query": query,
            "filters": filters or {},
            "page": page,
            "locale": search_locale,
            "sort": sort,
            "format": {
                "longDate": "MMMM D, YYYY",
                "mediumDate": "MMM D, YYYY"
            }
        }

        try:
            logger.info(f"Searching jobs with query='{query}', page={page}, filters={filters}")

            response = self.session.post(
                f"{self.API_BASE}/search",
                json=payload
            )
            response.raise_for_status()

            data = response.json()

            # Extract job results
            search_results = data.get('res', {}).get('searchResults', [])
            total_records = data.get('res', {}).get('totalRecords', 0)

            logger.info(f"Found {len(search_results)} jobs on page {page} (total: {total_records})")

            # Convert to Job objects
            jobs = [Job.from_dict(job_data) for job_data in search_results]

            return jobs

        except requests.RequestException as e:
            logger.error(f"Job search failed: {e}")
            raise
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse job search response: {e}")
            raise

    def get_total_jobs(
        self,
        query: str = "",
        filters: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Get the total number of jobs matching the search criteria.

        Args:
            query: Search query string
            filters: Dictionary of filters to apply

        Returns:
            Total number of jobs matching the criteria

        Example:
            >>> total = client.get_total_jobs(query="engineer")
            >>> print(f"Found {total} engineering jobs")
        """
        self._ensure_csrf_token()

        payload = {
            "query": query,
            "filters": filters or {},
            "page": 1,
            "locale": self.locale,
            "sort": "",
            "format": {
                "longDate": "MMMM D, YYYY",
                "mediumDate": "MMM D, YYYY"
            }
        }

        try:
            response = self.session.post(
                f"{self.API_BASE}/search",
                json=payload
            )
            response.raise_for_status()

            data = response.json()
            total_records = data.get('res', {}).get('totalRecords', 0)

            logger.info(f"Total jobs matching criteria: {total_records}")
            return total_records

        except requests.RequestException as e:
            logger.error(f"Failed to get total jobs: {e}")
            raise

    def search_all_jobs(
        self,
        query: str = "",
        filters: Optional[Dict[str, Any]] = None,
        max_pages: Optional[int] = None
    ) -> List[Job]:
        """
        Search for all jobs matching criteria, handling pagination automatically.

        This method will iterate through all pages of results and return
        all jobs matching the search criteria.

        Args:
            query: Search query string
            filters: Dictionary of filters to apply
            max_pages: Maximum number of pages to fetch (None for all pages)

        Returns:
            List of all Job objects matching the search criteria

        Example:
            >>> # Get all engineering jobs in France
            >>> all_jobs = client.search_all_jobs(
            ...     query="engineer",
            ...     filters={"postLocation": ["postLocation-FRA"]},
            ...     max_pages=5  # Limit to first 5 pages
            ... )
        """
        all_jobs: List[Job] = []
        page = 1

        # Get total count to know when to stop
        total_jobs = self.get_total_jobs(query=query, filters=filters)

        if total_jobs == 0:
            logger.info("No jobs found matching criteria")
            return []

        # Estimate total pages (assuming ~20 results per page)
        estimated_pages = (total_jobs + 19) // 20

        if max_pages:
            estimated_pages = min(estimated_pages, max_pages)

        logger.info(f"Fetching up to {estimated_pages} pages of results...")

        while True:
            if max_pages and page > max_pages:
                logger.info(f"Reached max_pages limit: {max_pages}")
                break

            jobs = self.search_jobs(
                query=query,
                filters=filters,
                page=page
            )

            if not jobs:
                logger.info(f"No more jobs found after page {page}")
                break

            all_jobs.extend(jobs)
            logger.info(f"Fetched page {page}/{estimated_pages} ({len(all_jobs)}/{total_jobs} jobs)")

            page += 1

        logger.info(f"Total jobs fetched: {len(all_jobs)}")
        return all_jobs


def main():
    """Example usage of the Apple Jobs API client."""

    # Initialize the client
    client = AppleJobsAPI(locale="en-us")

    # Example 1: Search for all jobs (first page)
    print("\n=== Example 1: First page of all jobs ===")
    jobs = client.search_jobs(page=1)
    for job in jobs[:5]:  # Show first 5
        print(f"Title: {job.postingTitle}")
        print(f"Location: {job.locations[0].name if job.locations else 'N/A'}")
        print(f"URL: {job.url}")
        print(f"Description: {job.jobSummary[:100]}...")
        print("-" * 80)

    # Example 2: Search with a query
    print("\n=== Example 2: Search for 'engineer' jobs ===")
    engineer_jobs = client.search_jobs(query="engineer", page=1)
    print(f"Found {len(engineer_jobs)} engineer jobs on page 1")

    # Example 3: Get total count
    print("\n=== Example 3: Total jobs available ===")
    total = client.get_total_jobs()
    print(f"Total jobs available: {total}")

    # Example 4: Search with filters (if you know the filter format)
    print("\n=== Example 4: Search with location filter ===")
    # Note: You would need to know the exact location IDs from the API
    filtered_jobs = client.search_jobs(
        query="",
        filters={},  # Add filters here if known
        page=1
    )
    print(f"Found {len(filtered_jobs)} jobs")

    # Example 5: Get all jobs (limited to 3 pages for demo)
    print("\n=== Example 5: Get multiple pages of jobs ===")
    all_jobs = client.search_all_jobs(max_pages=3)
    print(f"Total jobs fetched: {len(all_jobs)}")


if __name__ == "__main__":
    main()
