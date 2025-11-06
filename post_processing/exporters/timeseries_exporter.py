"""
Time Series Exporter for OpenSearch

Exports individual time series points to a separate zathras-timeseries index.
Each time series point is a fully denormalized document.
"""

import logging
from typing import List, Dict, Any, Optional

from .opensearch_exporter import OpenSearchExporter
from ..schema import TimeSeriesDocument, ZathrasDocument

logger = logging.getLogger(__name__)


class TimeSeriesExporter:
    """
    Exporter for time series data points to OpenSearch.

    Uses a separate index (zathras-timeseries) optimized for time series queries.
    Each data point is a separate document with full denormalized context.
    """

    def __init__(
        self,
        url: str,
        index: str = "zathras-timeseries",
        username: Optional[str] = None,
        password: Optional[str] = None,
        verify_ssl: bool = True,
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize time series exporter.

        Args:
            url: OpenSearch URL
            index: Index name (default: zathras-timeseries)
            username: Basic auth username
            password: Basic auth password
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.url = url
        self.index = index
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.max_retries = max_retries

        # Use OpenSearchExporter for the actual HTTP operations
        self.exporter = OpenSearchExporter(
            url=url,
            index=index,
            username=username,
            password=password,
            verify_ssl=verify_ssl,
            timeout=timeout,
            max_retries=max_retries
        )

        logger.info(f"TimeSeriesExporter initialized for index: {index}")

    def ensure_index_exists(self, apply_template: bool = False) -> bool:
        """
        Ensure the time series index exists.

        Args:
            apply_template: Whether to apply index template

        Returns:
            True if index exists or was created successfully
        """
        return self.exporter.ensure_index_exists(apply_template=apply_template)

    def export_timeseries_document(
        self,
        ts_doc: TimeSeriesDocument,
        doc_id: Optional[str] = None
    ) -> str:
        """
        Export a single time series document.

        Args:
            ts_doc: TimeSeriesDocument object
            doc_id: Optional custom document ID (defaults to timeseries_id)

        Returns:
            Document ID
        """
        doc_id = doc_id or ts_doc.metadata.timeseries_id
        doc_dict = ts_doc.to_dict()

        self.exporter.export_document(doc_dict, doc_id=doc_id)
        logger.debug(f"Exported time series point: {doc_id}")

        return doc_id

    def export_timeseries_bulk(
        self,
        ts_docs: List[TimeSeriesDocument],
        batch_size: int = 1000
    ) -> Dict[str, Any]:
        """
        Export multiple time series documents in bulk.

        Args:
            ts_docs: List of TimeSeriesDocument objects
            batch_size: Number of documents per bulk request

        Returns:
            Dict with export stats: {
                'total': int,
                'successful': int,
                'failed': int,
                'errors': List[str]
            }
        """
        total = len(ts_docs)
        successful = 0
        failed = 0
        errors = []

        logger.info(f"Starting bulk export of {total} time series points...")

        # Process in batches
        for i in range(0, total, batch_size):
            batch = ts_docs[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total + batch_size - 1) // batch_size

            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} docs)...")

            try:
                # Convert to list of dicts
                docs_list = []
                for ts_doc in batch:
                    docs_list.append({
                        'id': ts_doc.metadata.timeseries_id,
                        'document': ts_doc.to_dict()
                    })

                # Use bulk export
                result = self.exporter.bulk_export(docs_list)

                # Update stats
                successful += result.get('successful', 0)
                failed += result.get('failed', 0)
                if result.get('errors'):
                    errors.extend(result['errors'])

            except Exception as e:
                logger.error(f"Batch {batch_num} failed: {e}")
                failed += len(batch)
                errors.append(f"Batch {batch_num}: {str(e)}")

        logger.info(f"Bulk export complete: {successful} successful, {failed} failed")

        return {
            'total': total,
            'successful': successful,
            'failed': failed,
            'errors': errors
        }

    def export_from_zathras_document(
        self,
        document: ZathrasDocument,
        batch_size: int = 1000
    ) -> Dict[str, Any]:
        """
        Extract and export all time series points from a ZathrasDocument.

        Args:
            document: ZathrasDocument object
            batch_size: Number of documents per bulk request

        Returns:
            Dict with export stats
        """
        # Extract time series documents
        ts_docs = document.extract_timeseries_documents()

        if not ts_docs:
            logger.warning(f"No time series data found in document {document.metadata.document_id}")
            return {
                'total': 0,
                'successful': 0,
                'failed': 0,
                'errors': []
            }

        logger.info(f"Extracted {len(ts_docs)} time series points from {document.metadata.document_id}")

        # Export in bulk
        return self.export_timeseries_bulk(ts_docs, batch_size=batch_size)

    def search(self, query: Dict[str, Any], size: int = 100) -> Dict[str, Any]:
        """
        Search time series documents.

        Args:
            query: OpenSearch query DSL
            size: Maximum number of results to return

        Returns:
            OpenSearch response dict
        """
        return self.exporter.search(query=query, size=size)

    def delete_by_parent_document(self, document_id: str) -> Dict[str, Any]:
        """
        Delete all time series points for a given parent document.

        Args:
            document_id: Parent document ID

        Returns:
            Deletion response
        """
        query = {
            "query": {
                "term": {
                    "document_id.keyword": document_id
                }
            }
        }

        return self.exporter.delete_by_query(query)
