"""
Data Validator

This module validates the quality and completeness of downloaded company financial data.
"""

import os
import json
import glob
import pandas as pd
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

from src.utils.logger import setup_logger

# Setup logger
logger = setup_logger("data_validator")

class DataValidator:
    """SEC financial data validation class"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the validator
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        
        # Get paths
        data_paths = config.get("data_paths", {})
        self.raw_data_dir = data_paths.get("raw_data_dir", "data/raw")
        self.processed_data_dir = data_paths.get("processed_data_dir", "data/processed")
        self.company_facts_dir = data_paths.get("company_facts_dir", "data/raw/company_facts")
        
        # File paths
        self.companies_list_file = os.path.join(self.processed_data_dir, "companies_list.json")
        self.financial_metrics_file = os.path.join(self.processed_data_dir, "financial_metrics.parquet")
    
    def validate_directory_structure(self) -> Dict[str, bool]:
        """Validate data directory structure"""
        result = {
            "raw_data_dir": os.path.exists(self.raw_data_dir),
            "processed_data_dir": os.path.exists(self.processed_data_dir),
            "company_facts_dir": os.path.exists(self.company_facts_dir)
        }
        
        logger.info(f"Directory structure validation results: {result}")
        return result
    
    def validate_companies_list(self) -> Dict[str, Any]:
        """Validate companies list file"""
        result = {
            "exists": False,
            "count": 0,
            "valid_format": False,
            "sample": None,
            "ticker_coverage": 0.0
        }
        
        if not os.path.exists(self.companies_list_file):
            logger.warning(f"Companies list file not found: {self.companies_list_file}")
            return result
            
        result["exists"] = True
        
        try:
            with open(self.companies_list_file, 'r') as f:
                companies = json.load(f)
                
            if not isinstance(companies, list):
                logger.warning("Companies list file has incorrect format (should be a list)")
                return result
                
            result["valid_format"] = True
            result["count"] = len(companies)
            
            # Check ticker information
            ticker_count = 0
            for company in companies:
                if company.get("ticker_x") or company.get("ticker"):
                    ticker_count += 1
                    
            result["ticker_coverage"] = ticker_count / len(companies) if companies else 0
            
            # Add sample data
            if companies:
                result["sample"] = companies[0]
                
            logger.info(f"Companies list validation: {result['count']} companies, ticker coverage: {result['ticker_coverage']*100:.1f}%")
            
        except Exception as e:
            logger.error(f"Error validating companies list file: {e}")
            
        return result
    
    def validate_company_facts(self, sample_size: int = 10) -> Dict[str, Any]:
        """Validate raw company financial data (XBRL) files"""
        result = {
            "total_files": 0,
            "no_data_files": 0,
            "valid_files": 0,
            "invalid_files": 0,
            "valid_percent": 0.0,
            "has_key_metrics": {
                "eps": 0,
                "revenue": 0,
                "net_income": 0,
                "assets": 0,
                "liabilities": 0,
                "equity": 0
            },
            "samples": []
        }
        
        # Get all company facts files
        files = glob.glob(os.path.join(self.company_facts_dir, "CIK*.json"))
        result["total_files"] = len(files)
        
        if not files:
            logger.warning("No company facts files found.")
            return result
        
        # Adjust sample size (should not exceed total files)
        sample_size = min(sample_size, len(files))
        sample_files = files[:sample_size]
        
        for file_path in sample_files:
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # Check for placeholder file
                if data.get("no_data") == True:
                    result["no_data_files"] += 1
                    continue
                
                # Check if it has valid format
                if not ("cik" in data and "entityName" in data and "facts" in data):
                    result["invalid_files"] += 1
                    continue
                    
                result["valid_files"] += 1
                
                # Check us-gaap namespace
                us_gaap = data.get("facts", {}).get("us-gaap", {})
                if not us_gaap:
                    continue
                    
                # Check for key metrics existence
                key_metrics = result["has_key_metrics"]
                
                # EPS check
                for tag in ["EarningsPerShareDiluted", "EarningsPerShareBasic"]:
                    if tag in us_gaap:
                        key_metrics["eps"] += 1
                        break
                
                # Revenue check
                for tag in ["Revenue", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomer"]:
                    if tag in us_gaap:
                        key_metrics["revenue"] += 1
                        break
                
                # Net income check
                for tag in ["NetIncomeLoss", "ProfitLoss", "NetIncome"]:
                    if tag in us_gaap:
                        key_metrics["net_income"] += 1
                        break
                
                # Assets check
                if "Assets" in us_gaap:
                    key_metrics["assets"] += 1
                
                # Liabilities check
                if "Liabilities" in us_gaap:
                    key_metrics["liabilities"] += 1
                
                # Equity check
                for tag in ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]:
                    if tag in us_gaap:
                        key_metrics["equity"] += 1
                        break
                
                # Add to samples
                result["samples"].append({
                    "cik": data.get("cik", ""),
                    "name": data.get("entityName", ""),
                    "has_metrics": {
                        "eps": any(tag in us_gaap for tag in ["EarningsPerShareDiluted", "EarningsPerShareBasic"]),
                        "revenue": any(tag in us_gaap for tag in ["Revenue", "Revenues", "SalesRevenueNet"])
                    }
                })
                
            except Exception as e:
                logger.error(f"Error validating file: {file_path}, {e}")
                result["invalid_files"] += 1
        
        # Calculate overall statistics (estimated from sample ratio)
        if result["valid_files"] + result["invalid_files"] > 0:
            valid_ratio = result["valid_files"] / (result["valid_files"] + result["invalid_files"])
            result["valid_percent"] = valid_ratio * 100
            
            # Calculate estimates for all files
            if sample_size < result["total_files"]:
                estimated_valid = int(valid_ratio * result["total_files"])
                logger.info(f"Sample-based estimate of valid files: {estimated_valid}/{result['total_files']} ({valid_ratio*100:.1f}%)")
        
        # Log sample results
        sample_metrics = result["has_key_metrics"]
        for metric, count in sample_metrics.items():
            coverage = count / sample_size if sample_size > 0 else 0
            logger.info(f"{metric} metric coverage: {count}/{sample_size} ({coverage*100:.1f}%)")
        
        return result
    
    def validate_financial_metrics(self) -> Dict[str, Any]:
        """Validate processed financial metrics"""
        result = {
            "exists": False,
            "count": 0,
            "columns": [],
            "metric_coverage": {},
            "sample": None
        }
        
        if not os.path.exists(self.financial_metrics_file):
            logger.warning(f"Financial metrics file not found: {self.financial_metrics_file}")
            return result
            
        result["exists"] = True
        
        try:
            # Load file
            df = pd.read_parquet(self.financial_metrics_file)
            result["count"] = len(df)
            result["columns"] = list(df.columns)
            
            # Calculate key metric coverage
            key_metrics = [
                'quarterly_eps_growth', 'annual_eps_cagr', 'revenue_growth',
                'profit_margin', 'roe', 'debt_to_equity'
            ]
            
            for metric in key_metrics:
                if metric in df.columns:
                    count = df[metric].notna().sum()
                    coverage = count / len(df) if len(df) > 0 else 0
                    result["metric_coverage"][metric] = {
                        "count": int(count),
                        "coverage": float(coverage)
                    }
                    logger.info(f"{metric} coverage ratio: {count}/{len(df)} ({coverage*100:.1f}%)")
            
            # Add sample data
            if not df.empty:
                result["sample"] = df.iloc[0].to_dict()
            
        except Exception as e:
            logger.error(f"Error validating financial metrics file: {e}")
            
        return result
    
    def run_full_validation(self, fact_sample_size: int = 10) -> Dict[str, Any]:
        """Run complete data validation"""
        logger.info("Starting data validation...")
        
        # Comprehensive results dictionary
        validation_results = {
            "directory_structure": self.validate_directory_structure(),
            "companies_list": self.validate_companies_list(),
            "company_facts": self.validate_company_facts(fact_sample_size),
            "financial_metrics": self.validate_financial_metrics()
        }
        
        # Overall assessment
        overall_status = "PASS"
        warnings = []
        critical_issues = []
        
        # Check essential directories
        dir_check = validation_results["directory_structure"]
        if not all(dir_check.values()):
            missing_dirs = [d for d, exists in dir_check.items() if not exists]
            critical_issues.append(f"Missing required directories: {', '.join(missing_dirs)}")
            overall_status = "FAIL"
        
        # Check companies list
        companies_check = validation_results["companies_list"]
        if not companies_check["exists"]:
            critical_issues.append("Companies list file is missing")
            overall_status = "FAIL"
        elif not companies_check["valid_format"]:
            critical_issues.append("Companies list file has invalid format")
            overall_status = "FAIL"
        elif companies_check["ticker_coverage"] < 0.5:
            warnings.append(f"Low ticker coverage: {companies_check['ticker_coverage']*100:.1f}%")
            
        # Check company facts files
        facts_check = validation_results["company_facts"]
        if facts_check["total_files"] == 0:
            critical_issues.append("No company facts files found")
            overall_status = "FAIL"
        elif facts_check["valid_percent"] < 70:
            warnings.append(f"Low percentage of valid company facts files: {facts_check['valid_percent']:.1f}%")
            
        # Check metrics data
        metrics_check = validation_results["financial_metrics"]
        if not metrics_check["exists"]:
            warnings.append("Processed financial metrics file is missing")
        elif metrics_check["count"] == 0:
            warnings.append("Financial metrics file contains no data")
            
        # Add overall results
        validation_results["overall"] = {
            "status": overall_status,
            "warnings": warnings,
            "critical_issues": critical_issues
        }
        
        # Output summary results
        logger.info("\n============= DATA VALIDATION SUMMARY =============")
        logger.info(f"Overall status: {overall_status}")
        
        if critical_issues:
            logger.error("Critical issues:")
            for issue in critical_issues:
                logger.error(f"- {issue}")
                
        if warnings:
            logger.warning("Warnings:")
            for warning in warnings:
                logger.warning(f"- {warning}")
                
        logger.info("==================================================")
        
        return validation_results


def validate_data(config_path: str = "config/config.json") -> Dict[str, Any]:
    """
    Execute data validation
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Validation results dictionary
    """
    # Load configuration file
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Error loading configuration file: {e}")
        return {"error": str(e)}
    
    # Execute validation
    validator = DataValidator(config)
    return validator.run_full_validation()


if __name__ == "__main__":
    validate_data()
