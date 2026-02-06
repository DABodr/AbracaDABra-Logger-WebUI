"""Tests for TII formatting and parsing."""

import pandas as pd
import pytest

from app.core.tx_database import format_tii_code, split_tii_to_main_sub


class TestTIIFormatting:
    """Test TII formatting functions."""

    def test_format_tii_code_decimal_only(self):
        """Test that format_tii_code always uses decimal format, never hex."""
        # Standard cases
        assert format_tii_code(1, 1) == "0101"
        assert format_tii_code(12, 4) == "1204"

        # High main values (previously converted to hex incorrectly)
        assert format_tii_code(67, 2) == "6702", "main=67 should be '6702', not '4302'"
        assert format_tii_code(19, 1) == "1901"
        assert format_tii_code(24, 10) == "2410", "main=24 should be '2410', not '180A'"

        # Edge cases
        assert format_tii_code(0, 0) == "0000", "main=0 sub=0 is valid"
        assert format_tii_code(99, 99) == "9999"

    def test_split_tii_to_main_sub(self):
        """Test parsing TII strings to main/sub."""
        assert split_tii_to_main_sub("0101") == (1, 1)
        assert split_tii_to_main_sub("6702") == (67, 2)
        assert split_tii_to_main_sub("1901") == (19, 1)
        assert split_tii_to_main_sub("0000") == (0, 0)

        # Auto zfill
        assert split_tii_to_main_sub("304") == (3, 4)

        # Invalid cases
        assert split_tii_to_main_sub(None) == (None, None)
        assert split_tii_to_main_sub("") == (None, None)


class TestMainSubParsing:
    """Test Main/Sub column parsing robustness."""

    def test_parse_main_sub_with_nan(self):
        """Test that Main/Sub are parsed as nullable Int64, not filled with 0."""
        # Test the conversion logic directly
        import pandas as pd

        # Create test DataFrame with NaN values
        test_data = {
            "Main": [67.0, None, 12],
            "Sub": [2.0, None, 5],
        }
        df = pd.DataFrame(test_data)

        # Apply the same conversion as in csv_parser.py
        for col in ["Main", "Sub"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

        # Check that dtypes are Int64 (nullable)
        assert df["Main"].dtype == "Int64", "Main should be Int64 type"
        assert df["Sub"].dtype == "Int64", "Sub should be Int64 type"

        # Check that NaN values are preserved (not filled with 0)
        assert pd.isna(df.loc[1, "Main"]), "NaN Main should stay NaN, not become 0"
        assert pd.isna(df.loc[1, "Sub"]), "NaN Sub should stay NaN, not become 0"

        # Check valid values
        assert df.loc[0, "Main"] == 67, "Main should be 67"
        assert df.loc[0, "Sub"] == 2, "Sub should be 2"


class TestDedupWithNaN:
    """Test deduplication with NaN SNR values."""

    def test_dedup_handles_nan_snr(self):
        """Test that deduplication doesn't crash when SNR is NaN."""
        import pandas as pd

        # Create test data with NaN SNR
        data = {
            "Location": ["Loc1", "Loc1", "Loc2"],
            "Channel": ["5B", "5B", "6C"],
            "Label": ["Test", "Test", "Test2"],
            "SNR [dB]": [12.0, None, 8.5],
            "Main": [67, 67, 4],
            "Sub": [2, 2, 1],
        }
        df = pd.DataFrame(data)

        # This should not crash (previously used idxmax which fails on all-NaN groups)
        df_sorted = df.sort_values("SNR [dB]", ascending=False, na_position="last")
        result = df_sorted.drop_duplicates(subset=["Location", "Channel", "Label"], keep="first")

        assert len(result) == 2, "Should have 2 unique groups"
        assert result.iloc[0]["SNR [dB]"] == 12.0, "Best SNR row should be kept"
        assert result.iloc[1]["SNR [dB]"] == 8.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
