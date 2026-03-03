#!/usr/bin/env python3
"""
Horreum Exporter (stub)

Placeholder for exporting processed benchmark results to Horreum.
The post-processor currently focuses on OpenSearch; this module provides
stubs so that --horreum and config can remain in place for future use.

To implement: replace the stub methods with real HTTP calls to the Horreum API.
"""

import logging
from typing import Dict, List, Any, Optional

# Import schema for type hints
try:
    from ..schema import ZathrasDocument
except ImportError:
    ZathrasDocument = None


def _not_implemented(method: str = "Horreum export") -> None:
    raise NotImplementedError(
        f"{method} is not implemented. Focus is on OpenSearch; "
        "implement horreum_exporter.py to enable Horreum."
    )


class HorreumExporter:
    """Stub: export benchmark results to Horreum (not implemented)."""

    def __init__(
        self,
        url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        **kwargs: Any
    ) -> None:
        """
        Initialize Horreum exporter (stub).
        Args are stored for a future implementation.
        """
        self.url = url.rstrip("/") if url else ""
        self.username = username
        self.password = password
        self.logger = logging.getLogger(__name__)
        # Original implementation also used: test_name, auth_token, owner, access, timeout, etc.
        self._kwargs = kwargs

    def test_connection(self) -> bool:
        """Stub: test connection to Horreum."""
        _not_implemented("Horreum test_connection")

    def get_or_create_test(self) -> int:
        """Stub: get or create test in Horreum."""
        _not_implemented("Horreum get_or_create_test")

    def export_zathras_document(self, document: "ZathrasDocument") -> int:
        """
        Stub: export a ZathrasDocument to Horreum.
        Raises NotImplementedError; caller should catch and log that Horreum is not implemented.
        """
        _not_implemented("Horreum export_zathras_document")

    def export_run(
        self,
        document: Dict[str, Any],
        start_time: Optional[str] = None,
        stop_time: Optional[str] = None,
        schema_uri: Optional[str] = None,
    ) -> int:
        """Stub: export a benchmark run to Horreum."""
        _not_implemented("Horreum export_run")

    def export_bulk(self, documents: List[Dict[str, Any]]) -> List[int]:
        """Stub: export multiple runs to Horreum."""
        _not_implemented("Horreum export_bulk")

    def get_run(self, run_id: int) -> Dict[str, Any]:
        """Stub: retrieve a run from Horreum."""
        _not_implemented("Horreum get_run")

    def delete_run(self, run_id: int) -> bool:
        """Stub: delete a run from Horreum."""
        _not_implemented("Horreum delete_run")

    def list_runs(
        self,
        limit: int = 100,
        from_timestamp: Optional[str] = None,
        to_timestamp: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Stub: list runs for the configured test."""
        _not_implemented("Horreum list_runs")


# =============================================================================
# Original implementation (commented out; uncomment to restore full Horreum)
# Original docstring:
#   Handles exporting processed benchmark results to Horreum performance
#   test results repository. Supports run submission, schema validation,
#   and baseline management. Object-based schema with dynamic keys for
#   runs, NUMA nodes, storage devices; boolean object for CPU flags;
#   timestamp-keyed time series; named metrics objects.
# =============================================================================
#
# import json
# import time
# from datetime import datetime
# from urllib.parse import urljoin
# import urllib.request
# import urllib.error
#
# class HorreumExporter:
#     """Export benchmark results to Horreum."""
#
#     def __init__(
#         self,
#         url: str,
#         test_name: str,
#         auth_token: Optional[str] = None,
#         owner: Optional[str] = None,
#         access: str = "PUBLIC",
#         timeout: int = 30,
#         max_retries: int = 3,
#         retry_delay: int = 5
#     ):
#         self.url = url.rstrip('/')
#         self.test_name = test_name
#         self.auth_token = auth_token
#         self.owner = owner
#         self.access = access
#         self.timeout = timeout
#         self.max_retries = max_retries
#         self.retry_delay = retry_delay
#         self.logger = logging.getLogger(__name__)
#         self.test_id = None
#
#     def _build_headers(self) -> Dict[str, str]:
#         headers = {
#             'Content-Type': 'application/json',
#             'Accept': 'application/json'
#         }
#         if self.auth_token:
#             headers['Authorization'] = f'Bearer {self.auth_token}'
#         return headers
#
#     def _make_request(
#         self,
#         endpoint: str,
#         method: str = 'POST',
#         data: Optional[Dict] = None
#     ) -> Dict[str, Any]:
#         url = urljoin(self.url, endpoint)
#         headers = self._build_headers()
#         for attempt in range(self.max_retries):
#             try:
#                 request_data = json.dumps(data).encode('utf-8') if data else None
#                 req = urllib.request.Request(
#                     url,
#                     data=request_data,
#                     headers=headers,
#                     method=method
#                 )
#                 with urllib.request.urlopen(req, timeout=self.timeout) as response:
#                     response_body = response.read().decode('utf-8')
#                     if response_body:
#                         response_data = json.loads(response_body)
#                     else:
#                         response_data = {}
#                     self.logger.debug(f"Request to {endpoint} succeeded")
#                     return response_data
#             except urllib.error.HTTPError as e:
#                 error_body = e.read().decode('utf-8')
#                 self.logger.error(
#                     f"HTTP {e.code} error on attempt {attempt + 1}/{self.max_retries}: {error_body}"
#                 )
#                 if 400 <= e.code < 500:
#                     raise Exception(f"Client error {e.code}: {error_body}")
#                 if attempt < self.max_retries - 1:
#                     time.sleep(self.retry_delay)
#                 else:
#                     raise Exception(f"Request failed after {self.max_retries} attempts: {error_body}")
#             except urllib.error.URLError as e:
#                 self.logger.error(f"Connection error on attempt {attempt + 1}/{self.max_retries}: {e.reason}")
#                 if attempt < self.max_retries - 1:
#                     time.sleep(self.retry_delay)
#                 else:
#                     raise Exception(f"Connection failed after {self.max_retries} attempts: {e.reason}")
#             except Exception as e:
#                 self.logger.error(f"Unexpected error on attempt {attempt + 1}/{self.max_retries}: {str(e)}")
#                 if attempt < self.max_retries - 1:
#                     time.sleep(self.retry_delay)
#                 else:
#                     raise
#
#     def test_connection(self) -> bool:
#         try:
#             _ = self._make_request('/api/test', method='GET')
#             self.logger.info("Successfully connected to Horreum")
#             return True
#         except Exception as e:
#             self.logger.error(f"Connection test failed: {str(e)}")
#             return False
#
#     def get_or_create_test(self) -> int:
#         try:
#             tests = self._make_request('/api/test', method='GET')
#             for test in tests:
#                 if test.get('name') == self.test_name:
#                     self.test_id = test.get('id')
#                     self.logger.info(f"Found existing test '{self.test_name}' with ID: {self.test_id}")
#                     return self.test_id
#         except Exception as e:
#             self.logger.warning(f"Could not search for existing test: {str(e)}")
#         try:
#             test_definition = {
#                 "name": self.test_name,
#                 "description": f"Zathras benchmark results for {self.test_name}",
#                 "owner": self.owner or "zathras",
#                 "access": self.access
#             }
#             response = self._make_request('/api/test', method='POST', data=test_definition)
#             self.test_id = response.get('id')
#             self.logger.info(f"Created new test '{self.test_name}' with ID: {self.test_id}")
#             return self.test_id
#         except Exception as e:
#             self.logger.error(f"Failed to create test: {str(e)}")
#             raise
#
#     def export_zathras_document(self, document: 'ZathrasDocument') -> int:
#         if hasattr(document, 'to_dict'):
#             doc_dict = document.to_dict()
#         else:
#             doc_dict = document
#         start_time = None
#         stop_time = None
#         if 'runtime_info' in doc_dict:
#             start_time = doc_dict['runtime_info'].get('start_time')
#             stop_time = doc_dict['runtime_info'].get('end_time')
#         if not start_time and 'metadata' in doc_dict:
#             start_time = doc_dict['metadata'].get('collection_timestamp')
#         return self.export_run(doc_dict, start_time=start_time, stop_time=stop_time)
#
#     def export_run(
#         self,
#         document: Dict[str, Any],
#         start_time: Optional[str] = None,
#         stop_time: Optional[str] = None,
#         schema_uri: Optional[str] = None
#     ) -> int:
#         if ZathrasDocument and isinstance(document, ZathrasDocument):
#             return self.export_zathras_document(document)
#         if not self.test_id:
#             self.get_or_create_test()
#         run_data = {
#             "test": self.test_id,
#             "start": start_time or document.get('metadata', {}).get(
#                 'collection_timestamp',
#                 datetime.utcnow().isoformat() + 'Z'
#             ),
#             "stop": stop_time or datetime.utcnow().isoformat() + 'Z',
#             "owner": self.owner or "zathras",
#             "access": self.access,
#             "data": document
#         }
#         if schema_uri:
#             run_data["schema"] = schema_uri
#         run_data["data"]["_horreum_metadata"] = {
#             "exported_at": datetime.utcnow().isoformat() + 'Z',
#             "exporter": "zathras-horreum-exporter",
#             "exporter_version": "0.1.0",
#             "test_name": self.test_name
#         }
#         try:
#             response = self._make_request('/api/run', method='POST', data=run_data)
#             run_id = response.get('id')
#             self.logger.info(f"Exported run with ID: {run_id}")
#             return run_id
#         except Exception as e:
#             self.logger.error(f"Failed to export run: {str(e)}")
#             raise
#
#     def export_bulk(
#         self,
#         documents: List[Dict[str, Any]]
#     ) -> List[int]:
#         if not documents:
#             self.logger.warning("No documents to export")
#             return []
#         run_ids = []
#         errors = []
#         for i, doc in enumerate(documents):
#             try:
#                 run_id = self.export_run(doc)
#                 run_ids.append(run_id)
#             except Exception as e:
#                 self.logger.error(f"Failed to export document {i}: {str(e)}")
#                 errors.append((i, str(e)))
#         if errors:
#             self.logger.warning(
#                 f"Bulk export completed with {len(errors)} errors out of {len(documents)} documents"
#             )
#         else:
#             self.logger.info(f"Successfully exported {len(documents)} runs")
#         return run_ids
#
#     def get_run(self, run_id: int) -> Dict[str, Any]:
#         try:
#             return self._make_request(f'/api/run/{run_id}', method='GET')
#         except Exception as e:
#             self.logger.error(f"Failed to retrieve run {run_id}: {str(e)}")
#             raise
#
#     def delete_run(self, run_id: int) -> bool:
#         try:
#             self._make_request(f'/api/run/{run_id}', method='DELETE')
#             self.logger.info(f"Deleted run: {run_id}")
#             return True
#         except Exception as e:
#             self.logger.error(f"Failed to delete run {run_id}: {str(e)}")
#             return False
#
#     def list_runs(
#         self,
#         limit: int = 100,
#         from_timestamp: Optional[str] = None,
#         to_timestamp: Optional[str] = None
#     ) -> List[Dict[str, Any]]:
#         if not self.test_id:
#             self.get_or_create_test()
#         try:
#             query_params = [f"limit={limit}"]
#             if from_timestamp:
#                 query_params.append(f"from={from_timestamp}")
#             if to_timestamp:
#                 query_params.append(f"to={to_timestamp}")
#             query_string = "&".join(query_params)
#             endpoint = f'/api/run/list/{self.test_id}?{query_string}'
#             return self._make_request(endpoint, method='GET')
#         except Exception as e:
#             self.logger.error(f"Failed to list runs: {str(e)}")
#             raise
