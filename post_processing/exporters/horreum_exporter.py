#!/usr/bin/env python3
"""
Horreum Exporter

Handles exporting processed benchmark results to Horreum performance
test results repository. Supports run submission, schema validation,
and baseline management.

Updated for object-based schema with:
- Dynamic keys for runs, NUMA nodes, storage devices
- Boolean object for CPU flags
- Timestamp-keyed time series
- Named metrics objects
"""

import json
import logging
import time
from typing import Dict, List, Any, Optional
from datetime import datetime
from urllib.parse import urljoin
import urllib.request
import urllib.error

# Import schema for type hints
try:
    from ..schema import ZathrasDocument
except ImportError:
    ZathrasDocument = None


class HorreumExporter:
    """Export benchmark results to Horreum."""

    def __init__(
        self,
        url: str,
        test_name: str,
        auth_token: Optional[str] = None,
        owner: Optional[str] = None,
        access: str = "PUBLIC",
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: int = 5
    ):
        """
        Initialize Horreum exporter.

        Args:
            url: Horreum endpoint URL (e.g., https://horreum.example.com)
            test_name: Name of the test in Horreum
            auth_token: Optional authentication token
            owner: Test owner/team name
            access: Access level (PUBLIC, PROTECTED, PRIVATE)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
        """
        self.url = url.rstrip('/')
        self.test_name = test_name
        self.auth_token = auth_token
        self.owner = owner
        self.access = access
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logging.getLogger(__name__)
        self.test_id = None

    def _build_headers(self) -> Dict[str, str]:
        """Build HTTP headers for requests."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        if self.auth_token:
            headers['Authorization'] = f'Bearer {self.auth_token}'

        return headers

    def _make_request(
        self,
        endpoint: str,
        method: str = 'POST',
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Horreum with retry logic.

        Args:
            endpoint: API endpoint path
            method: HTTP method
            data: Request payload

        Returns:
            Response data as dictionary

        Raises:
            Exception: If request fails after retries
        """
        url = urljoin(self.url, endpoint)
        headers = self._build_headers()

        for attempt in range(self.max_retries):
            try:
                # Prepare request
                request_data = json.dumps(data).encode('utf-8') if data else None
                req = urllib.request.Request(
                    url,
                    data=request_data,
                    headers=headers,
                    method=method
                )

                # Make request
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    response_body = response.read().decode('utf-8')
                    if response_body:
                        response_data = json.loads(response_body)
                    else:
                        response_data = {}
                    self.logger.debug(f"Request to {endpoint} succeeded")
                    return response_data

            except urllib.error.HTTPError as e:
                error_body = e.read().decode('utf-8')
                self.logger.error(
                    f"HTTP {e.code} error on attempt {attempt + 1}/{self.max_retries}: {error_body}"
                )

                # Don't retry on client errors (4xx)
                if 400 <= e.code < 500:
                    raise Exception(f"Client error {e.code}: {error_body}")

                # Retry on server errors (5xx)
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise Exception(f"Request failed after {self.max_retries} attempts: {error_body}")

            except urllib.error.URLError as e:
                self.logger.error(f"Connection error on attempt {attempt + 1}/{self.max_retries}: {e.reason}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise Exception(f"Connection failed after {self.max_retries} attempts: {e.reason}")

            except Exception as e:
                self.logger.error(f"Unexpected error on attempt {attempt + 1}/{self.max_retries}: {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                else:
                    raise

    def test_connection(self) -> bool:
        """
        Test connection to Horreum.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try to get API version or test list
            _ = self._make_request('/api/test', method='GET')
            self.logger.info("Successfully connected to Horreum")
            return True
        except Exception as e:
            self.logger.error(f"Connection test failed: {str(e)}")
            return False

    def get_or_create_test(self) -> int:
        """
        Get existing test ID or create a new test in Horreum.

        Returns:
            Test ID

        Raises:
            Exception: If test cannot be retrieved or created
        """
        # Try to find existing test by name
        try:
            tests = self._make_request('/api/test', method='GET')
            for test in tests:
                if test.get('name') == self.test_name:
                    self.test_id = test.get('id')
                    self.logger.info(f"Found existing test '{self.test_name}' with ID: {self.test_id}")
                    return self.test_id
        except Exception as e:
            self.logger.warning(f"Could not search for existing test: {str(e)}")

        # Test doesn't exist, create it
        try:
            test_definition = {
                "name": self.test_name,
                "description": f"Zathras benchmark results for {self.test_name}",
                "owner": self.owner or "zathras",
                "access": self.access
            }

            response = self._make_request('/api/test', method='POST', data=test_definition)
            self.test_id = response.get('id')
            self.logger.info(f"Created new test '{self.test_name}' with ID: {self.test_id}")
            return self.test_id

        except Exception as e:
            self.logger.error(f"Failed to create test: {str(e)}")
            raise

    def export_zathras_document(self, document: 'ZathrasDocument') -> int:
        """
        Export a ZathrasDocument to Horreum.

        Args:
            document: ZathrasDocument object to export

        Returns:
            Run ID in Horreum

        Raises:
            Exception: If export fails
        """
        # Convert to dict
        if hasattr(document, 'to_dict'):
            doc_dict = document.to_dict()
        else:
            doc_dict = document

        # Extract start/stop times from runtime_info or results
        start_time = None
        stop_time = None

        if 'runtime_info' in doc_dict:
            start_time = doc_dict['runtime_info'].get('start_time')
            stop_time = doc_dict['runtime_info'].get('end_time')

        # Fallback to metadata timestamp
        if not start_time and 'metadata' in doc_dict:
            start_time = doc_dict['metadata'].get('collection_timestamp')

        return self.export_run(doc_dict, start_time=start_time, stop_time=stop_time)

    def export_run(
        self,
        document: Dict[str, Any],
        start_time: Optional[str] = None,
        stop_time: Optional[str] = None,
        schema_uri: Optional[str] = None
    ) -> int:
        """
        Export a benchmark run to Horreum.

        Args:
            document: Benchmark result document (dict or ZathrasDocument)
            start_time: Run start time (ISO format)
            stop_time: Run stop time (ISO format)
            schema_uri: URI of the JSON schema (if applicable)

        Returns:
            Run ID in Horreum

        Raises:
            Exception: If export fails
        """
        # Handle ZathrasDocument objects
        if ZathrasDocument and isinstance(document, ZathrasDocument):
            return self.export_zathras_document(document)

        # Ensure we have a test ID
        if not self.test_id:
            self.get_or_create_test()

        # Build run payload
        run_data = {
            "test": self.test_id,
            "start": start_time or document.get('metadata', {}).get(
                'collection_timestamp',
                datetime.utcnow().isoformat() + 'Z'
            ),
            "stop": stop_time or datetime.utcnow().isoformat() + 'Z',
            "owner": self.owner or "zathras",
            "access": self.access,
            "data": document
        }

        if schema_uri:
            run_data["schema"] = schema_uri

        # Add Horreum-specific metadata
        run_data["data"]["_horreum_metadata"] = {
            "exported_at": datetime.utcnow().isoformat() + 'Z',
            "exporter": "zathras-horreum-exporter",
            "exporter_version": "0.1.0",
            "test_name": self.test_name
        }

        # Submit run
        try:
            response = self._make_request('/api/run', method='POST', data=run_data)
            run_id = response.get('id')
            self.logger.info(f"Exported run with ID: {run_id}")
            return run_id
        except Exception as e:
            self.logger.error(f"Failed to export run: {str(e)}")
            raise

    def export_bulk(
        self,
        documents: List[Dict[str, Any]]
    ) -> List[int]:
        """
        Export multiple runs to Horreum.

        Args:
            documents: List of benchmark result documents

        Returns:
            List of run IDs

        Raises:
            Exception: If bulk export fails
        """
        if not documents:
            self.logger.warning("No documents to export")
            return []

        run_ids = []
        errors = []

        for i, doc in enumerate(documents):
            try:
                run_id = self.export_run(doc)
                run_ids.append(run_id)
            except Exception as e:
                self.logger.error(f"Failed to export document {i}: {str(e)}")
                errors.append((i, str(e)))

        if errors:
            self.logger.warning(
                f"Bulk export completed with {len(errors)} errors out of {len(documents)} documents"
            )
        else:
            self.logger.info(f"Successfully exported {len(documents)} runs")

        return run_ids

    def get_run(self, run_id: int) -> Dict[str, Any]:
        """
        Retrieve a run from Horreum.

        Args:
            run_id: Run ID to retrieve

        Returns:
            Run data
        """
        try:
            return self._make_request(f'/api/run/{run_id}', method='GET')
        except Exception as e:
            self.logger.error(f"Failed to retrieve run {run_id}: {str(e)}")
            raise

    def delete_run(self, run_id: int) -> bool:
        """
        Delete a run from Horreum.

        Args:
            run_id: Run ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            self._make_request(f'/api/run/{run_id}', method='DELETE')
            self.logger.info(f"Deleted run: {run_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete run {run_id}: {str(e)}")
            return False

    def list_runs(
        self,
        limit: int = 100,
        from_timestamp: Optional[str] = None,
        to_timestamp: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List runs for the configured test.

        Args:
            limit: Maximum number of runs to return
            from_timestamp: Start time filter (ISO format)
            to_timestamp: End time filter (ISO format)

        Returns:
            List of runs
        """
        if not self.test_id:
            self.get_or_create_test()

        try:
            # Build query parameters
            query_params = [f"limit={limit}"]
            if from_timestamp:
                query_params.append(f"from={from_timestamp}")
            if to_timestamp:
                query_params.append(f"to={to_timestamp}")

            query_string = "&".join(query_params)
            endpoint = f'/api/run/list/{self.test_id}?{query_string}'

            return self._make_request(endpoint, method='GET')
        except Exception as e:
            self.logger.error(f"Failed to list runs: {str(e)}")
            raise
