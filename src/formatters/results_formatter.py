"""
Results Formatter Module

This module provides functionality for formatting screening results and
exporting them to various formats.
"""

import os
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Union
from pathlib import Path

from src.utils.logger import setup_logger

# Set up logger
logger = setup_logger("results_formatter")

class ResultsFormatter:
    """
    Formats and exports screening results.
    
    This class handles formatting and exporting screening results to
    various formats, including CSV.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the ResultsFormatter.
        
        Args:
            config: Application configuration dictionary
        """
        self.config = config
        
        # Get output file path
        data_paths = config.get("data_paths", {})
        self.output_file = data_paths.get("output_file", "data/processed/results.csv")
    
    def format_results(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Format the results for output.
        
        Args:
            df: DataFrame with screening results
            
        Returns:
            Formatted DataFrame
        """
        # Make a copy of the input DataFrame
        result_df = df.copy()
        
        # Define the columns to include in the output
        output_columns = [
            'ticker', 'name', 'canslim_score', 'score_band',
            'c_score', 'a_score', 'n_score', 's_score', 'l_score', 'i_score', 'm_score',
            'market_cap', 'exchange',
            'quarterly_eps_growth', 'annual_eps_cagr', 'revenue_growth',
            'eps_qtr_growth', 'revenue_qtr_growth', 'eps_3yr_cagr',
            'profit_margin', 'roe', 'debt_to_equity',
            'rs_rating', 'price_vs_52w_high', 'avg_dollar_volume_50d',
            'price_performance', 'market_outperformance', 'market_outperformance_12m',
            'buy_zone_low', 'buy_zone_high', 'stop_loss_price', 'profit_target_low', 'profit_target_high',
            'institutional_holders', 'institutional_value', 'institutional_accumulation_score',
            'new_holder_count', 'increased_holder_count', 'decreased_holder_count', 'exited_holder_count',
            'insider_signal', 'insider_buy_count_90d', 'insider_sell_count_90d', 'net_insider_buy_value_90d',
            'pass_reasons', 'fail_reasons'
        ]
        
        # Add institutional ownership if available
        if 'institutional_ownership' in result_df.columns:
            output_columns.append('institutional_ownership')
        
        # Select only the columns that exist in the DataFrame
        existing_columns = [col for col in output_columns if col in result_df.columns]
        result_df = result_df[existing_columns]
        
        # Format percentage columns
        percentage_columns = [
            'quarterly_eps_growth', 'annual_eps_cagr', 'revenue_growth',
            'eps_qtr_growth', 'revenue_qtr_growth', 'eps_3yr_cagr',
            'profit_margin', 'roe', 'price_vs_52w_high', 'price_performance',
            'market_outperformance', 'market_outperformance_12m', 'institutional_ownership'
        ]
        
        for col in percentage_columns:
            if col in result_df.columns:
                result_df[col] = result_df[col].map(lambda x: f"{x*100:.2f}%" if pd.notnull(x) else "N/A")
        
        # Format market cap in millions or billions
        if 'market_cap' in result_df.columns:
            result_df['market_cap'] = result_df['market_cap'].map(
                lambda x: f"${x/1e9:.2f}B" if x >= 1e9 else f"${x/1e6:.2f}M" if pd.notnull(x) else "N/A"
            )
        
        for col in ['pass_reasons', 'fail_reasons']:
            if col in result_df.columns:
                result_df[col] = result_df[col].map(
                    lambda value: '; '.join(value) if isinstance(value, list) else (value if pd.notnull(value) else '')
                )

        # Convert ticker to uppercase
        if 'ticker' in result_df.columns:
            result_df['ticker'] = result_df['ticker'].str.upper()
            
        return result_df
    
    def sort_results(self, df: pd.DataFrame, sort_by: Optional[str] = None) -> pd.DataFrame:
        """
        Sort the results based on specified criteria.
        
        Args:
            df: DataFrame with screening results
            sort_by: Column to sort by (default is eps_qtr_growth or first numeric column)
            
        Returns:
            Sorted DataFrame
        """
        # If sort column is not specified, use eps_qtr_growth or first available numeric column
        if sort_by is None:
            if 'eps_qtr_growth' in df.columns and df['eps_qtr_growth'].dtype != 'object':
                sort_by = 'eps_qtr_growth'
            else:
                # Find the first numeric column
                numeric_columns = df.select_dtypes(include=[np.number]).columns
                if len(numeric_columns) > 0:
                    sort_by = numeric_columns[0]
                else:
                    # No numeric columns, use the first column
                    sort_by = df.columns[0]
        
        # Ensure the sort column exists
        if sort_by not in df.columns:
            logger.warning(f"Sort column '{sort_by}' not found in DataFrame")
            return df
        
        # Sort the DataFrame (descending for numeric columns, ascending for others)
        if df[sort_by].dtype in [np.float64, np.int64]:
            sorted_df = df.sort_values(by=sort_by, ascending=False)
        else:
            sorted_df = df.sort_values(by=sort_by)
            
        logger.info(f"Sorted results by {sort_by}")
        return sorted_df
    
    def add_summary_statistics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate summary statistics for the results.
        
        Args:
            df: DataFrame with screening results
            
        Returns:
            Dictionary with summary statistics
        """
        # Initialize summary dictionary
        summary = {
            "total_companies": len(df),
            "metrics": {}
        }
        
        # Calculate statistics for numeric columns
        numeric_columns = [
            'eps_qtr_growth', 'revenue_qtr_growth', 'eps_3yr_cagr',
            'profit_margin', 'roe', 'price_performance', 
            'market_outperformance', 'institutional_ownership'
        ]
        
        for col in numeric_columns:
            if col in df.columns and df[col].dtype != 'object':
                col_summary = {
                    "mean": df[col].mean(),
                    "median": df[col].median(),
                    "min": df[col].min(),
                    "max": df[col].max()
                }
                summary["metrics"][col] = col_summary
        
        # Add exchange distribution if available
        if 'exchange' in df.columns:
            exchange_counts = df['exchange'].value_counts().to_dict()
            summary["exchanges"] = exchange_counts
            
        return summary
    
    def export_to_csv(self, df: pd.DataFrame) -> str:
        """
        Export the results to a CSV file.
        
        Args:
            df: DataFrame with formatted results
            
        Returns:
            Path to the output file
        """
        # Ensure the output directory exists
        Path(os.path.dirname(self.output_file)).mkdir(parents=True, exist_ok=True)
        
        # Export to CSV
        df.to_csv(self.output_file, index=False)
        logger.info(f"Exported {len(df)} results to {self.output_file}")
        
        return self.output_file
    
    def export_to_markdown(self, df: pd.DataFrame, summary: Dict[str, Any]) -> str:
        """Export a human-readable CAN SLIM Markdown report next to the CSV."""
        markdown_file = str(Path(self.output_file).with_suffix('.md'))
        Path(os.path.dirname(markdown_file)).mkdir(parents=True, exist_ok=True)
        lines = [
            "# CAN SLIM Screening Report",
            "",
            f"Total candidates: {summary.get('total_companies', len(df))}",
            "",
            "## Top Candidates",
            "",
        ]
        if df.empty:
            lines.append("No companies passed the screen.")
        else:
            for _, row in df.head(25).iterrows():
                ticker = row.get('ticker', 'N/A')
                name = row.get('name', 'Unknown')
                score = row.get('canslim_score', 'N/A')
                band = row.get('score_band', 'N/A')
                component_summary = '/'.join(
                    str(row.get(field, 'N/A')) for field in ['c_score', 'a_score', 'n_score', 's_score', 'l_score', 'i_score', 'm_score']
                )
                lines.extend([
                    f"### {ticker} — {name}",
                    f"- CAN SLIM score: {score} ({band})",
                    f"- C/A/N/S/L/I/M: {component_summary}",
                ])
                trade_bits = []
                for label, field in [
                    ('Buy zone', 'buy_zone_low'),
                    ('Buy zone high', 'buy_zone_high'),
                    ('Stop loss', 'stop_loss_price'),
                    ('Profit target low', 'profit_target_low'),
                    ('Profit target high', 'profit_target_high'),
                ]:
                    if field in row and pd.notnull(row[field]):
                        trade_bits.append(f"{label}: {row[field]}")
                if trade_bits:
                    lines.append(f"- Trade plan: {'; '.join(trade_bits)}")
                if row.get('institutional_accumulation_score') is not None and pd.notnull(row.get('institutional_accumulation_score')):
                    lines.append(f"- 13F accumulation score: {row.get('institutional_accumulation_score')}")
                if row.get('insider_signal') is not None and pd.notnull(row.get('insider_signal')):
                    lines.append(f"- Insider signal: {row.get('insider_signal')}")
                for label, field in [('Pass reasons', 'pass_reasons'), ('Watch/fail reasons', 'fail_reasons')]:
                    value = row.get(field)
                    if isinstance(value, list):
                        value = '; '.join(value)
                    if value:
                        lines.append(f"- {label}: {value}")
                lines.append("")
        with open(markdown_file, 'w') as f:
            f.write('\n'.join(lines).rstrip() + '\n')
        logger.info(f"Exported Markdown report to {markdown_file}")
        return markdown_file

    def create_report(self, df: pd.DataFrame, sort_by: Optional[str] = None) -> str:
        """
        Create a formatted report from the screening results.
        
        Args:
            df: DataFrame with screening results
            sort_by: Column to sort by
            
        Returns:
            Path to the output file
        """
        # Format the results
        formatted_df = self.format_results(df)
        
        # Sort the results
        sorted_df = self.sort_results(formatted_df, sort_by)
        
        # Calculate summary statistics
        summary = self.add_summary_statistics(df)
        
        # Export to CSV and Markdown
        output_file = self.export_to_csv(sorted_df)
        self.export_to_markdown(sorted_df, summary)
        
        # Log summary
        logger.info(f"Screening report generated with {summary['total_companies']} companies")
        if 'eps_qtr_growth' in summary.get('metrics', {}):
            eps_summary = summary['metrics']['eps_qtr_growth']
            logger.info(f"EPS growth: mean={eps_summary['mean']*100:.2f}%, median={eps_summary['median']*100:.2f}%, max={eps_summary['max']*100:.2f}%")
        
        return output_file
