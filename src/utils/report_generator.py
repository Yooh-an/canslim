"""
Validation Results Report Generator

Converts data validation results into text and HTML reports
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List

class ReportGenerator:
    """Class for generating user-friendly reports from validation results"""
    
    def __init__(self, results: Dict[str, Any]):
        """
        Initialize the report generator
        
        Args:
            results: Data validation results
        """
        self.results = results
        self.timestamp = datetime.now()
    
    def generate_text_report(self) -> str:
        """Generate text format report"""
        lines = []
        
        # Header
        lines.append("=" * 80)
        lines.append("Growth Stock Screener Data Validation Report")
        lines.append(f"Generated: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)
        
        # Overall summary
        overall = self.results.get("overall", {})
        status = overall.get("status", "Unknown")
        lines.append(f"\nOverall Validation Status: {status}")
        
        # Critical issues
        critical_issues = overall.get("critical_issues", [])
        if critical_issues:
            lines.append("\n[Critical Issues]")
            for issue in critical_issues:
                lines.append(f"- {issue}")
        
        # Warnings
        warnings = overall.get("warnings", [])
        if warnings:
            lines.append("\n[Warnings]")
            for warning in warnings:
                lines.append(f"- {warning}")
        
        # Directory structure
        lines.append("\n[Directory Structure]")
        dir_check = self.results.get("directory_structure", {})
        for dir_name, exists in dir_check.items():
            status_str = "✓" if exists else "✗"
            lines.append(f"- {dir_name}: {status_str}")
        
        # Companies list
        lines.append("\n[Companies List File]")
        companies_check = self.results.get("companies_list", {})
        if companies_check.get("exists", False):
            count = companies_check.get("count", 0)
            ticker_coverage = companies_check.get("ticker_coverage", 0) * 100
            lines.append(f"- Company count: {count}")
            lines.append(f"- Ticker coverage: {ticker_coverage:.1f}%")
        else:
            lines.append("- File does not exist.")
        
        # Company facts files
        lines.append("\n[Company Financial Data Files]")
        facts_check = self.results.get("company_facts", {})
        total = facts_check.get("total_files", 0)
        valid = facts_check.get("valid_files", 0)
        invalid = facts_check.get("invalid_files", 0)
        no_data = facts_check.get("no_data_files", 0)
        
        lines.append(f"- Total files: {total}")
        if total > 0:
            valid_percent = facts_check.get("valid_percent", 0)
            lines.append(f"- Valid files: {valid_percent:.1f}% (based on sample)")
            lines.append(f"- Files marked as 'no data': {no_data}")
            
            # Key metrics presence
            metrics = facts_check.get("has_key_metrics", {})
            sample_size = valid + invalid
            if sample_size > 0:
                lines.append("\n  [Key Metrics Coverage (sample-based)]")
                for metric, count in metrics.items():
                    rate = count / sample_size * 100 if sample_size > 0 else 0
                    lines.append(f"  - {metric}: {rate:.1f}%")
        
        # Financial metrics file
        lines.append("\n[Processed Financial Metrics]")
        metrics_check = self.results.get("financial_metrics", {})
        if metrics_check.get("exists", False):
            count = metrics_check.get("count", 0)
            columns = metrics_check.get("columns", [])
            lines.append(f"- Company count: {count}")
            lines.append(f"- Included columns: {', '.join(columns[:10])}...")
            
            # Metric coverage
            coverage = metrics_check.get("metric_coverage", {})
            if coverage:
                lines.append("\n  [Key Metrics Coverage]")
                for metric, data in coverage.items():
                    metric_count = data.get("count", 0)
                    metric_coverage = data.get("coverage", 0) * 100
                    lines.append(f"  - {metric}: {metric_count}/{count} ({metric_coverage:.1f}%)")
        else:
            lines.append("- File does not exist.")
        
        # Conclusions and recommendations
        lines.append("\n[Conclusions and Recommendations]")
        if status == "PASS":
            lines.append("- Data files have been successfully downloaded and processed.")
        else:
            lines.append("- Issues were found with data files. Check warnings and errors above.")
            
            # Add recommendations
            if "Companies list file is missing" in str(critical_issues):
                lines.append("  * Run download mode to generate the 'Companies List' file:")
                lines.append("    python growth_stock_screener.py --mode download")
                
            if "No company facts files found" in str(critical_issues):
                lines.append("  * Run download mode to download 'Company Financial Data':")
                lines.append("    python growth_stock_screener.py --mode download")
                
            if "Processed financial metrics file is missing" in str(warnings):
                lines.append("  * Run parse mode to calculate 'Financial Metrics':")
                lines.append("    python growth_stock_screener.py --mode parse")
            
        return "\n".join(lines)
    
    def generate_html_report(self) -> str:
        """Generate HTML format report"""
        # HTML template implementation omitted (will primarily use text reports)
        pass
    
    def save_report(self, output_dir: str = "reports") -> str:
        """
        Save report to a file
        
        Args:
            output_dir: Output directory
            
        Returns:
            Path to generated file
        """
        # Create directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Create filename (with timestamp)
        timestamp_str = self.timestamp.strftime("%Y%m%d_%H%M%S")
        filename = f"data_validation_{timestamp_str}.txt"
        filepath = os.path.join(output_dir, filename)
        
        # Generate and save text report
        report = self.generate_text_report()
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report)
            
        return filepath
