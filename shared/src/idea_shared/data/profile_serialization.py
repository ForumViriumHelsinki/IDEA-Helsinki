"""Profile serialization utilities for DataFrame ↔ Parquet bytes.

Keeps repository storage-format agnostic by isolating the serialization
concern. Uses Parquet via pandas/pyarrow for compact binary representation
(~2-5KB per profile with 168 rows × 6 columns).
"""

from __future__ import annotations

import io

import pandas as pd


def serialize_profile(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to Parquet bytes.

    Args:
        df: Profile DataFrame to serialize.

    Returns:
        Parquet-encoded bytes.
    """
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    return buffer.getvalue()


def deserialize_profile(data: bytes) -> pd.DataFrame:
    """Deserialize Parquet bytes to a DataFrame.

    Args:
        data: Parquet-encoded bytes.

    Returns:
        Reconstructed DataFrame.
    """
    buffer = io.BytesIO(data)
    return pd.read_parquet(buffer, engine="pyarrow")
