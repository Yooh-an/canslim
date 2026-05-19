import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from src.utils.ticker_mapper import TickerMapper


class TestTickerMapper(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config = {
            "data_paths": {
                "processed_data_dir": os.path.join(self.temp_dir, "processed"),
            },
            "sec_api": {"user_agent": "Unit Test (test@example.com)"},
        }

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    @patch("src.utils.ticker_mapper.requests.get")
    def test_download_mapping_uses_sec_exchange_master_with_exchange_and_name(self, mock_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[2023554, "Sandisk Corp", "SNDK", "Nasdaq"]],
        }
        mock_get.return_value = response

        mapper = TickerMapper(self.config)

        self.assertTrue(mapper.download_mapping(force=True))

        self.assertEqual(mapper.get_cik("SNDK"), "0002023554")
        self.assertEqual(mapper.get_ticker("2023554"), "SNDK")
        df = pd.read_csv(mapper.mapping_file)
        row = df[df["ticker"] == "SNDK"].iloc[0]
        self.assertEqual(str(row["cik"]).zfill(10), "0002023554")
        self.assertEqual(row["exchange"], "Nasdaq")
        self.assertEqual(row["name"], "Sandisk Corp")
        self.assertEqual(row["source"], "company_tickers_exchange")

    @patch("src.utils.ticker_mapper.requests.get")
    def test_download_mapping_falls_back_to_company_tickers_json(self, mock_get):
        exchange_response = Mock()
        exchange_response.raise_for_status.side_effect = RuntimeError("exchange master unavailable")
        company_response = Mock()
        company_response.raise_for_status.return_value = None
        company_response.json.return_value = {
            "0": {"cik_str": 2023554, "ticker": "SNDK", "title": "Sandisk Corp"}
        }
        mock_get.side_effect = [exchange_response, company_response]

        mapper = TickerMapper(self.config)

        self.assertTrue(mapper.download_mapping(force=True))

        self.assertEqual(mapper.get_cik("SNDK"), "0002023554")
        df = pd.read_csv(mapper.mapping_file)
        self.assertEqual(df.iloc[0]["source"], "company_tickers")

    @patch("src.utils.ticker_mapper.requests.get")
    def test_manual_overrides_take_precedence(self, mock_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"fields": ["cik", "name", "ticker", "exchange"], "data": []}
        mock_get.return_value = response

        override_file = os.path.join(self.temp_dir, "ticker_overrides.csv")
        with open(override_file, "w") as f:
            f.write("cik,ticker,exchange,name,reason\n")
            f.write("2023554,SNDK,Nasdaq,Sandisk Corp,spin-off\n")
        self.config["data_paths"]["ticker_overrides_file"] = override_file

        mapper = TickerMapper(self.config)

        self.assertTrue(mapper.download_mapping(force=True))

        self.assertEqual(mapper.get_cik("sndk"), "0002023554")
        self.assertEqual(mapper.get_ticker("0002023554"), "SNDK")
        df = pd.read_csv(mapper.mapping_file)
        self.assertEqual(df.iloc[0]["source"], "manual_override")


if __name__ == "__main__":
    unittest.main()
