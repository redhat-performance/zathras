"""
Zathras Test Result Processors

Processors convert raw test results into structured JSON documents
using the object-based schema.

Each processor handles a specific benchmark type (CoreMark, FIO, STREAMS, etc.)
"""

__all__ = [
    'base_processor',
    'coremark_processor'
]
