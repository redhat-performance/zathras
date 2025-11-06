#!/usr/bin/env python3
"""
OpenSearch Exporter

Handles exporting processed benchmark results to OpenSearch/Elasticsearch.
Supports bulk operations, retry logic, and connection management.

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
from pathlib import Path
import urllib.request
import urllib.error

# Import schema for type hints
try:
    from ..schema import ZathrasDocument
except ImportError:
    ZathrasDocument = None


class OpenSearchExporter:
    """Export benchmark results to OpenSearch."""

    def __init__(
        self,
        url: str,
        index: str,
        auth_token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        verify_ssl: bool = True,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: int = 5
    ):
        """
        Initialize OpenSearch exporter.

        Args:
            url: OpenSearch endpoint URL (e.g., https://opensearch.example.com)
            index: Index name to write documents to
            auth_token: Optional bearer token for authentication
            username: Optional username for basic auth
            password: Optional password for basic auth
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
        """
        self.url = url.rstrip('/')
        self.index = index
        self.auth_token = auth_token
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logging.getLogger(__name__)

    def _build_headers(self) -> Dict[str, str]:
        """Build HTTP headers for requests."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        if self.auth_token:
            headers['Authorization'] = f'Bearer {self.auth_token}'
        elif self.username and self.password:
            # Basic auth
            import base64
            credentials = f"{self.username}:{self.password}"
            encoded = base64.b64encode(credentials.encode('utf-8')).decode('ascii')
            headers['Authorization'] = f'Basic {encoded}'

        return headers

    def _make_request(
        self,
        endpoint: str,
        method: str = 'POST',
        data: Optional[Dict] = None,
        is_bulk: bool = False
    ) -> Dict[str, Any]:
        """
        Make HTTP request to OpenSearch with retry logic.

        Args:
            endpoint: API endpoint path
            method: HTTP method
            data: Request payload (Dict for regular requests, str for bulk)
            is_bulk: Whether this is a bulk request (uses different content-type)

        Returns:
            Response data as dictionary

        Raises:
            Exception: If request fails after retries
        """
        url = urljoin(self.url, endpoint)
        headers = self._build_headers()

        # For bulk requests, use different content-type
        if is_bulk:
            headers['Content-Type'] = 'application/x-ndjson'

        for attempt in range(self.max_retries):
            try:
                # Prepare request
                if is_bulk:
                    # Bulk data is already a string
                    request_data = data.encode('utf-8') if data else None
                else:
                    # Regular JSON data
                    request_data = json.dumps(data).encode('utf-8') if data else None

                req = urllib.request.Request(
                    url,
                    data=request_data,
                    headers=headers,
                    method=method
                )

                # Create SSL context if needed
                import ssl
                context = None
                if not self.verify_ssl and url.startswith('https'):
                    context = ssl._create_unverified_context()

                # Make request
                with urllib.request.urlopen(req, timeout=self.timeout, context=context) as response:
                    response_data = json.loads(response.read().decode('utf-8'))
                    self.logger.debug(f"Request to {endpoint} succeeded")
                    return response_data

            except urllib.error.HTTPError as e:
                error_body = e.read().decode('utf-8')

                # HTTP 409 is expected for duplicates - log as warning
                if e.code == 409:
                    self.logger.warning(
                        f"HTTP {e.code} conflict on attempt {attempt + 1}/{self.max_retries}: {error_body}"
                    )
                else:
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
        Test connection to OpenSearch.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self._make_request('/', method='GET')
            self.logger.info(f"Connected to OpenSearch cluster: {response.get('cluster_name', 'unknown')}")
            return True
        except Exception as e:
            self.logger.error(f"Connection test failed: {str(e)}")
            return False

    def apply_index_template(self, template_file: Optional[str] = None) -> bool:
        """
        Apply OpenSearch index template for object-based schema.

        Args:
            template_file: Path to template JSON file. If None, uses default template.

        Returns:
            True if template applied successfully
        """
        try:
            if template_file:
                with open(template_file, 'r') as f:
                    template = json.load(f)
            else:
                # Use default template from config
                config_dir = Path(__file__).parent.parent / 'config'
                template_path = config_dir / 'opensearch_index_template.json'

                if template_path.exists():
                    with open(template_path, 'r') as f:
                        template = json.load(f)
                else:
                    self.logger.warning("No index template found, skipping template application")
                    return False

            # Apply template
            template_name = "zathras-results-template"
            endpoint = f"/_index_template/{template_name}"

            self._make_request(endpoint, method='PUT', data=template)
            self.logger.info(f"Applied index template: {template_name}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to apply index template: {str(e)}")
            return False

    def ensure_index_exists(self, apply_template: bool = True) -> bool:
        """
        Ensure the target index exists, create if it doesn't.

        Args:
            apply_template: If True, apply index template before creating index

        Returns:
            True if index exists or was created successfully
        """
        try:
            # Check if index exists
            self._make_request(f'/{self.index}', method='HEAD')
            self.logger.info(f"Index '{self.index}' already exists")
            return True
        except Exception:
            # Apply template first if requested
            if apply_template:
                self.apply_index_template()

            # Index doesn't exist, create it
            # If template was applied, this will use the template settings
            try:
                # Simple index creation - template will handle mappings
                index_settings = {
                    "settings": {
                        "number_of_shards": 3,
                        "number_of_replicas": 1,
                        "index": {
                            "mapping": {
                                "total_fields": {
                                    "limit": 5000  # Higher limit for dynamic fields
                                }
                            }
                        }
                    }
                }

                self._make_request(f'/{self.index}', method='PUT', data=index_settings)
                self.logger.info(f"Created index '{self.index}'")
                return True
            except Exception as e:
                error_msg = str(e)
                # Index already exists is actually success
                if 'resource_already_exists_exception' in error_msg or 'index_already_exists' in error_msg:
                    self.logger.info(f"Index '{self.index}' already exists")
                    return True
                self.logger.error(f"Failed to create index: {error_msg}")
                return False

    def export_zathras_document(self, document: 'ZathrasDocument') -> str:
        """
        Export a ZathrasDocument to OpenSearch.

        Args:
            document: ZathrasDocument object to export

        Returns:
            Document ID of the indexed document

        Raises:
            Exception: If export fails
        """
        # Convert to dict
        if hasattr(document, 'to_dict'):
            doc_dict = document.to_dict()
        else:
            doc_dict = document

        # Use document_id from metadata as OpenSearch document ID
        doc_id = doc_dict.get('metadata', {}).get('document_id')

        return self.export_document(doc_dict, doc_id=doc_id)

    def export_document(self, document: Dict[str, Any], doc_id: Optional[str] = None) -> Dict[str, str]:
        """
        Export a single document to OpenSearch.

        Args:
            document: Document to export (dict or ZathrasDocument)
            doc_id: Optional document ID (auto-generated if not provided)

        Returns:
            Dict with 'id' (document ID) and 'result' ('created' or 'updated')

        Raises:
            Exception: If export fails
        """
        # Handle ZathrasDocument objects
        if ZathrasDocument and isinstance(document, ZathrasDocument):
            return self.export_zathras_document(document)

        # Add export metadata
        document['_export_metadata'] = {
            'exported_at': datetime.utcnow().isoformat() + 'Z',
            'exporter': 'zathras-opensearch-exporter',
            'exporter_version': '1.0.0'
        }

        # Determine endpoint
        if doc_id:
            endpoint = f'/{self.index}/_doc/{doc_id}'
        else:
            endpoint = f'/{self.index}/_doc'

        # Index document
        try:
            response = self._make_request(endpoint, method='POST', data=document)
            doc_id = response.get('_id')
            result = response.get('result', 'unknown')  # 'created' or 'updated'
            self.logger.info(f"Exported document with ID: {doc_id} (result: {result})")
            return {'id': doc_id, 'result': result}
        except Exception as e:
            self.logger.error(f"Failed to export document: {str(e)}")
            raise

    def export_bulk(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Export multiple documents using bulk API.

        Args:
            documents: List of documents to export

        Returns:
            Bulk operation results

        Raises:
            Exception: If bulk export fails
        """
        if not documents:
            self.logger.warning("No documents to export")
            return {"items": [], "errors": False}

        # Build bulk request body
        bulk_body = []
        for doc in documents:
            # Add export metadata
            doc['_export_metadata'] = {
                'exported_at': datetime.utcnow().isoformat() + 'Z',
                'exporter': 'zathras-opensearch-exporter',
                'exporter_version': '0.1.0'
            }

            # Index action
            bulk_body.append(json.dumps({"index": {"_index": self.index}}))
            bulk_body.append(json.dumps(doc))

        bulk_data = '\n'.join(bulk_body) + '\n'

        # Make bulk request
        try:
            url = urljoin(self.url, '/_bulk')
            headers = self._build_headers()
            headers['Content-Type'] = 'application/x-ndjson'

            req = urllib.request.Request(
                url,
                data=bulk_data.encode('utf-8'),
                headers=headers,
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode('utf-8'))

            # Check for errors
            if result.get('errors'):
                error_count = sum(
                    1 for item in result.get('items', [])
                    if 'error' in item.get('index', {})
                )
                self.logger.warning(f"Bulk export completed with {error_count} errors")
            else:
                self.logger.info(f"Successfully exported {len(documents)} documents")

            return result

        except Exception as e:
            self.logger.error(f"Bulk export failed: {str(e)}")
            raise

    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document from OpenSearch.

        Args:
            doc_id: Document ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            self._make_request(f'/{self.index}/_doc/{doc_id}', method='DELETE')
            self.logger.info(f"Deleted document: {doc_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete document {doc_id}: {str(e)}")
            return False

    def delete_by_query(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Delete documents matching a query.

        Args:
            query: OpenSearch query DSL

        Returns:
            Deletion response with 'deleted' count
        """
        try:
            return self._make_request(f'/{self.index}/_delete_by_query', method='POST', data=query)
        except Exception as e:
            self.logger.error(f"Delete by query failed: {str(e)}")
            raise

    def create_document(self, document: Dict[str, Any], doc_id: str) -> Dict[str, str]:
        """
        Create a new document in OpenSearch. Fails if document already exists.

        Args:
            document: Document to create
            doc_id: Document ID

        Returns:
            Dict with 'id' (document ID) and 'result' ('created' or 'duplicate')

        Raises:
            Exception: If creation fails for reasons other than duplicate
        """
        # Add export metadata
        document['_export_metadata'] = {
            'exported_at': datetime.utcnow().isoformat() + 'Z',
            'exporter': 'zathras-opensearch-exporter',
            'exporter_version': '1.0.0'
        }

        # Use _create endpoint which fails on duplicates
        endpoint = f'/{self.index}/_create/{doc_id}'

        try:
            response = self._make_request(endpoint, method='PUT', data=document)
            result = response.get('result', 'created')
            self.logger.info(f"Created document with ID: {doc_id}")
            return {'id': doc_id, 'result': result}
        except Exception as e:
            error_str = str(e)
            # Check if this is a duplicate (version conflict)
            if 'version_conflict_engine_exception' in error_str or '409' in error_str:
                self.logger.info(f"Document already exists: {doc_id} (duplicate)")
                return {'id': doc_id, 'result': 'duplicate'}
            else:
                # Other error - re-raise
                self.logger.error(f"Failed to create document {doc_id}: {error_str}")
                raise

    def search(self, query: Dict[str, Any], size: int = 100) -> Dict[str, Any]:
        """
        Execute a search query.

        Args:
            query: OpenSearch query DSL
            size: Maximum number of results to return (default: 100)

        Returns:
            Search results
        """
        try:
            # Add size to query if not already present
            if 'size' not in query:
                query['size'] = size

            return self._make_request(f'/{self.index}/_search', method='POST', data=query)
        except Exception as e:
            self.logger.error(f"Search failed: {str(e)}")
            raise

    def bulk_export(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Export multiple documents using the Bulk API.

        Args:
            documents: List of dicts with 'id' and 'document' keys
                      [{'id': 'doc1', 'document': {...}}, ...]

        Returns:
            Dict with stats: {'total': int, 'successful': int, 'failed': int, 'errors': List[str]}
        """
        if not documents:
            return {'total': 0, 'successful': 0, 'failed': 0, 'errors': []}

        # Build bulk request body
        # Format: {"index": {"_id": "id"}}\n{document}\n
        bulk_body_lines = []
        for doc in documents:
            doc_id = doc.get('id')
            document = doc.get('document')

            if not doc_id or not document:
                continue

            # Action line
            action = {"index": {"_id": doc_id}}
            bulk_body_lines.append(json.dumps(action))

            # Document line
            bulk_body_lines.append(json.dumps(document))

        # Join with newlines and add trailing newline
        bulk_body = '\n'.join(bulk_body_lines) + '\n'

        try:
            # Make bulk request
            response = self._make_request(
                f'/{self.index}/_bulk',
                method='POST',
                data=bulk_body,
                is_bulk=True  # Special flag for bulk requests
            )

            # Parse response
            items = response.get('items', [])
            successful = 0
            failed = 0
            errors = []

            for item in items:
                index_result = item.get('index', {})
                if index_result.get('status') in [200, 201]:
                    successful += 1
                else:
                    failed += 1
                    error_msg = index_result.get('error', {}).get('reason', 'Unknown error')
                    errors.append(f"Doc {index_result.get('_id')}: {error_msg}")

            return {
                'total': len(documents),
                'successful': successful,
                'failed': failed,
                'errors': errors[:10]  # Limit error messages
            }

        except Exception as e:
            self.logger.error(f"Bulk export failed: {str(e)}")
            return {
                'total': len(documents),
                'successful': 0,
                'failed': len(documents),
                'errors': [str(e)]
            }
