import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from src.parsers.submissions_parser import SubmissionsParser


class TestSubmissionsParser(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config = {
            "data_paths": {
                "raw_data_dir": os.path.join(self.temp_dir, "raw"),
                "processed_data_dir": os.path.join(self.temp_dir, "processed"),
            },
            "ticker_mapping": {"force_refresh_on_cached_companies": True},
        }
        os.makedirs(os.path.join(self.temp_dir, "raw", "submissions_extracted"), exist_ok=True)
        os.makedirs(os.path.join(self.temp_dir, "processed"), exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch("src.parsers.submissions_parser.TickerMapper")
    def test_create_company_index_refreshes_ticker_mapping_even_when_cached_index_exists(self, mock_mapper_cls):
        companies_file = os.path.join(
            self.temp_dir, "raw", "submissions_extracted", "companies.json"
        )
        with open(companies_file, "w") as f:
            json.dump(
                {
                    "0002023554": {
                        "name": "Sandisk Corporation",
                        "tickers": [],
                        "exchanges": [],
                    }
                },
                f,
            )

        parser = SubmissionsParser(self.config)
        stale_df_path = os.path.join(self.temp_dir, "processed", "companies_index.parquet")
        import pandas as pd
        pd.DataFrame([{"cik": "1", "ticker": "OLD"}]).to_parquet(stale_df_path, index=False)

        mock_mapper = mock_mapper_cls.return_value
        mock_mapper.download_mapping.return_value = True

        def add_sndk(companies):
            companies["0002023554"]["tickers"] = ["SNDK"]
            companies["0002023554"]["exchanges"] = ["Nasdaq"]
            return companies

        mock_mapper.enrich_companies_with_tickers.side_effect = add_sndk

        df = parser.create_company_index()

        self.assertEqual(df["ticker"].tolist(), ["SNDK"])
        mock_mapper.download_mapping.assert_called_once_with(force=True)

    @patch("src.parsers.submissions_parser.TickerMapper")
    def test_create_company_index_refreshes_ticker_mapping_before_indexing(self, mock_mapper_cls):
        companies_file = os.path.join(
            self.temp_dir, "raw", "submissions_extracted", "companies.json"
        )
        with open(companies_file, "w") as f:
            json.dump(
                {
                    "0002023554": {
                        "name": "Sandisk Corporation",
                        "tickers": [],
                        "exchanges": [],
                    }
                },
                f,
            )

        mock_mapper = mock_mapper_cls.return_value
        mock_mapper.download_mapping.return_value = True

        def add_sndk(companies):
            companies["0002023554"]["tickers"] = ["SNDK"]
            companies["0002023554"]["exchanges"] = ["Nasdaq"]
            return companies

        mock_mapper.enrich_companies_with_tickers.side_effect = add_sndk

        parser = SubmissionsParser(self.config)
        df = parser.create_company_index(force=True)

        self.assertEqual(df["ticker"].tolist(), ["SNDK"])
        mock_mapper.download_mapping.assert_called_once_with(force=True)
        with open(companies_file) as f:
            saved = json.load(f)
        self.assertEqual(saved["0002023554"]["tickers"], ["SNDK"])


if __name__ == "__main__":
    unittest.main()
