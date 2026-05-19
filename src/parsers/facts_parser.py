"""
XBRL Facts Parser

Module for parsing SEC XBRL company facts data and extracting financial metrics.
"""

import os
import json
import glob
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np
import traceback
from typing import Dict, List, Any, Optional, Tuple, Set, Union

from src.utils.logger import setup_logger
from src.parsers.fact_utils import (
    frame_period,
    item_end_date,
    normalized_form,
    period_start_date,
    period_year,
    quarter_from_end_date,
    quarter_number,
    safe_float,
)

# Set up logger
logger = setup_logger("facts_parser")

class XBRLFactsParser:
    """
    Parser for SEC XBRL company facts data.
    
    This class extracts key financial metrics from company facts files,
    handling different taxonomy variations and data structures.
    """
    
    # 태그 변형을 확장하여 더 많은 재무 데이터 포맷을 처리할 수 있도록 함
    TAG_VARIATIONS = {
        'eps': {
            'us-gaap:EarningsPerShareDiluted',
            'us-gaap:EarningsPerShareBasicAndDiluted',
            'us-gaap:EarningsPerShareBasic',
            'us-gaap:IncomeLossPerShareBasicAndDiluted',
            'us-gaap:IncomeLossFromContinuingOperationsPerShareDiluted',
            'us-gaap:IncomeLossFromContinuingOperationsPerShareBasic'
        },
        'revenue': {
            'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
            'us-gaap:Revenues',
            'us-gaap:SalesRevenueNet',
            'us-gaap:RevenueNet',
            'us-gaap:Revenue',
            'us-gaap:SalesRevenueGoodsNet',
            'us-gaap:SalesRevenueServicesNet',
            'us-gaap:OperatingRevenue'
        },
        'net_income': {
            'us-gaap:NetIncomeLoss',
            'us-gaap:ProfitLoss', 
            'us-gaap:NetIncome',
            'us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic',
            'us-gaap:NetIncomeLossAttributableToParent',
            'us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest'
        },
        'assets': {
            'us-gaap:Assets',
            'us-gaap:AssetsCurrent',
            'us-gaap:AssetsNoncurrent'
        },
        'liabilities': {
            'us-gaap:Liabilities',
            'us-gaap:LiabilitiesCurrent',
            'us-gaap:LiabilitiesNoncurrent'
        },
        'equity': {
            'us-gaap:StockholdersEquity',
            'us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',
            'us-gaap:LiabilitiesAndStockholdersEquity',
            'us-gaap:CommonStockEquity',
            'us-gaap:PartnersCapital'
        }
    }
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the XBRLFactsParser."""
        self.config = config
        
        # Get data paths from config
        data_paths = config.get("data_paths", {})
        self.raw_data_dir = data_paths.get("raw_data_dir", "data/raw")
        self.processed_data_dir = data_paths.get("processed_data_dir", "data/processed")
        self.company_facts_dir = data_paths.get("company_facts_dir", "data/raw/company_facts")
        
        # Define output paths
        self.parsed_metrics_file = os.path.join(self.processed_data_dir, "financial_metrics.parquet")
        
        # Ensure directories exist
        Path(self.processed_data_dir).mkdir(parents=True, exist_ok=True)
    
    def get_company_facts_files(self) -> List[str]:
        """
        Get a de-duplicated list of company facts files.

        Prefer explicitly downloaded files in company_facts_dir, but also include
        missing CIKs from the SEC bulk companyfacts extraction. This prevents newly
        mapped tickers from appearing in the company universe with all metrics NaN
        merely because their per-company file was not downloaded earlier.
        
        Returns:
            List of file paths
        """
        files_by_cik: Dict[str, str] = {}
        for file_path in glob.glob(os.path.join(self.company_facts_dir, "CIK*.json")):
            cik = os.path.basename(file_path).replace("CIK", "").replace(".json", "")
            files_by_cik[cik] = file_path

        extracted_dir = os.path.join(self.raw_data_dir, "submissions_extracted")
        bulk_added = 0
        for file_path in glob.glob(os.path.join(extracted_dir, "CIK*.json")):
            cik = os.path.basename(file_path).replace("CIK", "").replace(".json", "")
            if cik not in files_by_cik:
                files_by_cik[cik] = file_path
                bulk_added += 1

        files = [files_by_cik[cik] for cik in sorted(files_by_cik)]
        logger.info(
            f"Found {len(files)} company facts files "
            f"({len(files) - bulk_added} downloaded, {bulk_added} bulk fallback)"
        )
        return files
    
    def load_company_facts(self, file_path: str) -> Dict[str, Any]:
        """
        Load company facts data from a file.
        
        Args:
            file_path: Path to the company facts JSON file
            
        Returns:
            Dictionary containing the company facts data
        """
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"Error loading company facts from {file_path}: {e}")
            return {}

    def _select_unit_values(self, concept_data: Dict[str, Any], unit_types: List[str]) -> List[Dict[str, Any]]:
        units = concept_data.get('units', {})
        for unit_type in unit_types:
            values = units.get(unit_type)
            if values:
                return values
        return []

    def _fact_records(self, concept_data: Dict[str, Any], unit_types: List[str]) -> List[Dict[str, Any]]:
        records = []
        for item in self._select_unit_values(concept_data, unit_types):
            form = normalized_form(item)
            end_date = item_end_date(item)
            value = safe_float(item.get('val'))
            if not form or not end_date or value is None:
                continue

            start_date = period_start_date(item)
            days = None
            if start_date:
                try:
                    days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
                except Exception:
                    days = None

            records.append({
                'start': start_date,
                'end': end_date,
                'filed': item.get('filed', ''),
                'fy': item.get('fy'),
                'fp': str(item.get('fp', '')).upper() if item.get('fp') else '',
                'form': form,
                'frame': item.get('frame', ''),
                'val': value,
                'days': days,
            })
        return records

    def _quarterly_flow_series(self, concept_data: Dict[str, Any], unit_types: List[str]) -> List[Dict[str, Any]]:
        """
        Build fiscal-quarter values from SEC facts.

        SEC frequently reports Q2/Q3 flow facts as year-to-date values. For CAN SLIM
        YoY checks we need actual quarter values, so this derives Q2/Q3 by subtracting
        the previous YTD value when a standalone quarter value is not available.
        """
        records = self._fact_records(concept_data, unit_types)
        by_period: Dict[Tuple[int, int], Dict[str, Any]] = {}
        ytd_by_period: Dict[Tuple[int, int], Dict[str, Any]] = {}
        annual_by_fy: Dict[int, Dict[str, Any]] = {}

        for record in records:
            fy = period_year(record)
            if fy is None:
                continue

            _, frame_quarter = frame_period(record.get('frame'))
            quarter = (
                quarter_number(record.get('fp'))
                or frame_quarter
                or quarter_from_end_date(record.get('end'))
            )
            frame = str(record.get('frame') or '').upper()
            days = record.get('days')
            key = (fy, quarter) if quarter else None

            if record['form'] == '10-K' and (record.get('fp') == 'FY' or (days and days >= 300)):
                current = annual_by_fy.get(fy)
                if current is None or (record.get('end') or '', record.get('filed') or '') > (current.get('end') or '', current.get('filed') or ''):
                    annual_by_fy[fy] = record
                continue

            if record['form'] != '10-Q' or quarter is None:
                continue

            is_standalone_quarter = (
                (days is not None and 55 <= days <= 130)
                or ('Q' in frame and 'CY' in frame)
            )
            target = by_period if is_standalone_quarter else ytd_by_period
            current = target.get(key)
            if current is None or (record.get('end') or '', record.get('filed') or '') > (current.get('end') or '', current.get('filed') or ''):
                target[key] = record

        derived: Dict[Tuple[int, int], Dict[str, Any]] = dict(by_period)
        for key, record in sorted(ytd_by_period.items()):
            fy, quarter = key
            if key in derived:
                continue
            if quarter == 1:
                derived[key] = record
                continue
            previous_key = (fy, quarter - 1)
            previous_ytd = ytd_by_period.get(previous_key)
            if previous_ytd is None and quarter == 2:
                # Q1 YTD is the same value as standalone Q1, so it is safe here.
                previous_ytd = derived.get(previous_key)
            if previous_ytd:
                quarter_record = dict(record)
                quarter_record['val'] = record['val'] - previous_ytd['val']
                quarter_record['derived_from_ytd'] = True
                derived[key] = quarter_record

        # Q4 is usually not reported as a 10-Q. Derive it from annual minus Q1-Q3
        # when all three quarters are present.
        for fy, annual in annual_by_fy.items():
            q_keys = [(fy, 1), (fy, 2), (fy, 3)]
            if all(q_key in derived for q_key in q_keys) and (fy, 4) not in derived:
                q4_record = dict(annual)
                q4_record['fp'] = 'Q4'
                q4_record['form'] = '10-K'
                q4_record['val'] = annual['val'] - sum(derived[q_key]['val'] for q_key in q_keys)
                q4_record['derived_from_annual'] = True
                derived[(fy, 4)] = q4_record

        series = []
        for (fy, quarter), record in sorted(derived.items(), reverse=True):
            if record.get('val') is None:
                continue
            item = dict(record)
            item['fy'] = fy
            item['quarter'] = quarter
            item['period_key'] = f"{fy}Q{quarter}"
            series.append(item)
        return series

    def _annual_series(self, concept_data: Dict[str, Any], unit_types: List[str]) -> List[Dict[str, Any]]:
        annual: Dict[int, Dict[str, Any]] = {}
        for record in self._fact_records(concept_data, unit_types):
            if record['form'] != '10-K':
                continue
            fy = period_year(record)
            if fy is None:
                continue
            days = record.get('days')
            if record.get('fp') != 'FY' and not (days and days >= 300):
                continue
            current = annual.get(fy)
            if current is None or (record.get('filed') or '', record.get('end') or '') > (current.get('filed') or '', current.get('end') or ''):
                annual[fy] = record

        return [
            {**record, 'fy': fy}
            for fy, record in sorted(annual.items(), reverse=True)
        ]

    @staticmethod
    def _latest_same_quarter_yoy(series: List[Dict[str, Any]]) -> Optional[Tuple[float, Dict[str, Any], Dict[str, Any]]]:
        if not series:
            return None
        latest = series[0]
        latest_fy = latest.get('fy')
        quarter = latest.get('quarter')
        if latest_fy is None or quarter is None:
            return None
        for candidate in series[1:]:
            if candidate.get('fy') == latest_fy - 1 and candidate.get('quarter') == quarter:
                year_ago = candidate
                if year_ago.get('val') and year_ago['val'] > 0:
                    return (latest['val'] / year_ago['val'] - 1, latest, year_ago)
        return None

    @staticmethod
    def _annual_cagr(series: List[Dict[str, Any]], min_years: int = 3) -> Optional[Tuple[float, Dict[str, Any], Dict[str, Any], int]]:
        if not series:
            return None
        latest = series[0]
        if latest.get('val') is None or latest['val'] <= 0:
            return None
        for candidate in series[1:]:
            year_diff = latest.get('fy', 0) - candidate.get('fy', 0)
            if year_diff >= min_years and candidate.get('val') and candidate['val'] > 0:
                return ((latest['val'] / candidate['val']) ** (1 / year_diff) - 1, latest, candidate, year_diff)
        return None

    @staticmethod
    def _latest_end_key(records: List[Dict[str, Any]]) -> pd.Timestamp:
        dates = []
        for record in records:
            try:
                dates.append(pd.Timestamp(record.get('end')))
            except Exception:
                continue
        return max(dates) if dates else pd.Timestamp.min

    @staticmethod
    def _is_stale_concept(latest_concept_end: pd.Timestamp, latest_company_end: Optional[pd.Timestamp]) -> bool:
        if latest_company_end is None or pd.isna(latest_company_end) or latest_concept_end == pd.Timestamp.min:
            return False
        return latest_concept_end < latest_company_end - pd.DateOffset(months=18)

    def _latest_company_fact_end(self, us_gaap_facts: Dict[str, Any]) -> Optional[pd.Timestamp]:
        latest = pd.Timestamp.min
        for concept_data in us_gaap_facts.values():
            units = concept_data.get('units', {})
            for unit_values in units.values():
                for item in unit_values:
                    if not normalized_form(item):
                        continue
                    end_date = item_end_date(item)
                    if not end_date:
                        continue
                    try:
                        latest = max(latest, pd.Timestamp(end_date))
                    except Exception:
                        continue
        return None if latest == pd.Timestamp.min else latest
    
    def find_best_tag(self, concept: str, facts: Dict[str, Any]) -> Optional[str]:
        """Find the best available tag for a given concept."""
        if concept not in self.TAG_VARIATIONS:
            logger.warning(f"Unknown concept: {concept}")
            return None
        
        # Look for exact matches in the variation set
        tag_variations = self.TAG_VARIATIONS[concept]
        
        # us-gaap 네임스페이스에서 찾기
        us_gaap_facts = facts.get('facts', {}).get('us-gaap', {})
        if not us_gaap_facts:
            logger.warning("No us-gaap facts found")
            return None
            
        for tag in tag_variations:
            # us-gaap: 접두사 제거
            tag_name = tag.replace('us-gaap:', '')
            if tag_name in us_gaap_facts:
                return f"us-gaap:{tag_name}"
        
        # 이 개념에 대한 태그를 찾지 못함
        logger.debug(f"No matching tag found for concept '{concept}'. Available us-gaap tags: {list(us_gaap_facts.keys())[:10]}...")
        return None
        
    def extract_quarterly_values(self, concept_data: Dict[str, Any],
                                unit_type: str = "USD") -> Dict[str, float]:
        """Extract quarterly values from concept data."""
        values = {}
        
        # 단위 유형 처리 개선
        units = concept_data.get('units', {})
        
        # EPS의 경우 단위가 USD/shares 또는 USD 등으로 다양할 수 있음
        possible_unit_types = [unit_type]
        if unit_type == "USD":
            possible_unit_types.extend(["USD/shares", "USD/share", "shares", "pure"])
        
        # 가능한 모든 단위 유형에서 데이터 검색
        unit_values = None
        for ut in possible_unit_types:
            if ut in units:
                unit_values = units[ut]
                break
        
        if not unit_values:
            logger.debug(f"No values found for unit types {possible_unit_types}")
            return values
        
        # 분기별 데이터와 연간 데이터 모두 처리
        # 실제 값은 10-Q와 10-K 모두에서 추출 가능
        for item in unit_values:
            # 기간이 지정되어 있는지 확인
            end_date = item_end_date(item)
            form = normalized_form(item)
            if not end_date or not form:
                continue

            # 중복 방지를 위해 end_date + form을 키로 사용
            key = f"{end_date}_{form}"
            try:
                # 항상 숫자로 변환 시도
                values[key] = float(item['val'])
            except (ValueError, TypeError):
                # 숫자로 변환할 수 없는 경우 스킵
                logger.warning(f"Non-numeric value for {end_date}: {item.get('val')}")
        
        return values
    
    def process_company_file(self, file_path: str) -> Dict[str, Any]:
        """
        Process a single company facts file and extract metrics.
        
        Args:
            file_path: Path to company facts JSON file
            
        Returns:
            Dictionary of extracted metrics
        """
        try:
            # Extract CIK from filename
            filename = os.path.basename(file_path)
            cik = filename.replace('CIK', '').replace('.json', '')
            
            # Debug info
            logger.debug(f"Processing file for CIK: {cik}, path: {file_path}")
            
            # Load facts
            facts = self.load_company_facts(file_path)
            if not facts:
                logger.warning(f"Could not load facts from {file_path}")
                return {'cik': cik}
            
            # Skip placeholder files
            if facts.get("no_data") == True:
                logger.info(f"Skipping CIK {cik} due to no data")
                return {'cik': cik}
            
            # Create base metrics entry
            company_metrics = {
                'cik': cik,
                'name': facts.get('entityName', ''),
            }
            
            # Handle tickers field
            tickers = facts.get('tickers', [])
            if isinstance(tickers, list) and tickers:
                company_metrics['ticker'] = tickers[0]
            else:
                company_metrics['ticker'] = ''
            
            # Get us-gaap facts
            if "facts" not in facts:
                logger.warning(f"No 'facts' key in {file_path}")
                return company_metrics
                
            us_gaap_facts = facts.get('facts', {}).get('us-gaap', {})
            if not us_gaap_facts:
                logger.warning(f"No us-gaap facts found for CIK {cik}")
                return company_metrics
            
            # Debug: 사용 가능한 모든 태그를 로그
            logger.debug(f"Available us-gaap tags count: {len(us_gaap_facts)}")
            if len(us_gaap_facts) > 0:
                logger.debug(f"Sample tags: {list(us_gaap_facts.keys())[:5]}")

            company_metrics['_latest_fact_end'] = self._latest_company_fact_end(us_gaap_facts)
            
            # Extract key financial metrics
            self._extract_eps_metrics(us_gaap_facts, company_metrics)
            self._extract_revenue_metrics(us_gaap_facts, company_metrics)
            self._extract_income_metrics(us_gaap_facts, company_metrics)
            self._extract_balance_sheet_metrics(us_gaap_facts, company_metrics)
            
            # Calculate derived metrics (profit margin, ROE, etc.)
            self._calculate_derived_metrics(company_metrics)
            
            # Debug: 추출된 지표 확인
            financial_metrics = [
                'quarterly_eps_growth', 'annual_eps_cagr', 'revenue_growth',
                'profit_margin', 'roe', 'debt_to_equity'
            ]
            extracted = [m for m in financial_metrics if m in company_metrics]
            if extracted:
                logger.debug(f"Extracted metrics ({len(extracted)}): {extracted}")
            else:
                logger.debug(f"No metrics extracted for CIK {cik}")
                
            return company_metrics
            
        except Exception as e:
            logger.error(f"Error processing {file_path}: {str(e)}")
            logger.debug(traceback.format_exc())
            # Return cik if available, otherwise 'unknown'
            return {'cik': cik if 'cik' in locals() else 'unknown'}
    
    def _extract_eps_metrics(self, us_gaap_facts: Dict[str, Any], metrics: Dict[str, Any]) -> None:
        """Extract EPS metrics from us-gaap facts."""
        eps_tags = [
            "EarningsPerShareDiluted",
            "EarningsPerShareBasicAndDiluted",
            "EarningsPerShareBasic",
            "IncomeLossPerShareBasicAndDiluted",
            "IncomeLossFromContinuingOperationsPerShareDiluted",
            "IncomeLossFromContinuingOperationsPerShareBasic",
        ]
        
        # Debug: 무슨 태그가 사용 가능한지 확인
        available_tags = set(us_gaap_facts.keys())
        matching_tags = [tag for tag in eps_tags if tag in available_tags]
        if not matching_tags:
            logger.debug(f"EPS 관련 태그가 없습니다. 사용 가능 태그: {list(available_tags)[:10]} ...")
            return
        
        best_data = None
        for tag in eps_tags:
            if tag not in us_gaap_facts:
                continue

            tag_data = us_gaap_facts[tag]
            units = tag_data.get('units', {})
            if not units:
                logger.debug(f"{tag}에 대한 units 키가 없거나, 값이 비어있습니다.")
                continue

            logger.debug(f"{tag}에 대한 사용 가능 units: {list(units.keys())}")
            unit_types = ["USD/shares", "USD/share", "pure", "USD"]
            quarterly = self._quarterly_flow_series(tag_data, unit_types)
            annual = self._annual_series(tag_data, unit_types)
            if not quarterly and not annual:
                continue

            latest_end = self._latest_end_key(quarterly + annual)
            if best_data is None or latest_end > best_data[0]:
                best_data = (latest_end, quarterly, annual)

        if not best_data:
            return

        latest_end, quarterly, annual = best_data
        if self._is_stale_concept(latest_end, metrics.get('_latest_fact_end')):
            logger.debug("Skipping stale EPS facts")
            return
        if quarterly:
            yoy = self._latest_same_quarter_yoy(quarterly)
            if yoy:
                growth, latest, year_ago = yoy
                metrics['quarterly_eps_growth'] = growth
                metrics['quarterly_eps_latest'] = latest['val']
                metrics['quarterly_eps_year_ago'] = year_ago['val']
                metrics['quarterly_eps_period'] = latest.get('period_key')
                logger.debug(f"분기 EPS 성장률({latest.get('period_key')} vs {year_ago.get('period_key')}): {growth}")
            else:
                logger.debug(f"분기 EPS YoY 계산에 필요한 같은 회계분기 데이터 부족: {len(quarterly)}개")

        if annual:
            cagr = self._annual_cagr(annual)
            if cagr:
                growth, latest, base, years = cagr
                metrics['annual_eps_cagr'] = growth
                metrics['annual_eps_latest'] = latest['val']
                metrics['annual_eps_base'] = base['val']
                metrics['annual_eps_years'] = years
                logger.debug(f"연간 EPS CAGR({latest.get('fy')} vs {base.get('fy')}, {years}년): {growth}")
            else:
                logger.debug(f"연간 EPS CAGR 계산에 필요한 양수 EPS 3년 이상 데이터 부족: {len(annual)}개")
    
    def _extract_revenue_metrics(self, us_gaap_facts: Dict[str, Any], metrics: Dict[str, Any]) -> None:
        """Extract Revenue metrics from us-gaap facts."""
        revenue_tags = [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "Revenues",
            "SalesRevenueNet",
            "RevenueNet",
            "Revenue",
            "SalesRevenueGoodsNet",
            "SalesRevenueServicesNet",
            "OperatingRevenue",
        ]
        
        # Debug: 사용 가능한 태그 확인
        available_tags = set(us_gaap_facts.keys())
        matching_tags = [tag for tag in revenue_tags if tag in available_tags]
        if not matching_tags:
            logger.debug(f"매출 관련 태그가 없습니다. 사용 가능 태그: {list(available_tags)[:10]} ...")
            return
        
        best_data = None
        for tag in revenue_tags:
            if tag not in us_gaap_facts:
                continue

            tag_data = us_gaap_facts[tag]
            units = tag_data.get('units', {})
            if not units:
                logger.debug(f"{tag}에 대한 units 키가 없거나 값이 비어있습니다.")
                continue

            logger.debug(f"{tag}에 대한 사용 가능 units: {list(units.keys())}")
            quarterly = self._quarterly_flow_series(tag_data, ["USD"])
            annual = self._annual_series(tag_data, ["USD"])
            if not quarterly and not annual:
                continue

            latest_end = self._latest_end_key(quarterly + annual)
            if best_data is None or latest_end > best_data[0]:
                best_data = (latest_end, quarterly, annual)

        if not best_data:
            return

        latest_end, quarterly, annual = best_data
        if self._is_stale_concept(latest_end, metrics.get('_latest_fact_end')):
            logger.debug("Skipping stale revenue facts")
            return
        metrics['_quarterly_revenue_values'] = [
            (record['period_key'], record['end'], record['val'])
            for record in quarterly
        ]
        metrics['_annual_revenue_values'] = [
            (record['fy'], record['end'], record['val'])
            for record in annual
        ]

        yoy = self._latest_same_quarter_yoy(quarterly)
        if yoy:
            growth, latest, year_ago = yoy
            metrics['revenue_growth'] = growth
            metrics['revenue_latest'] = latest['val']
            metrics['revenue_year_ago'] = year_ago['val']
            metrics['revenue_period'] = latest.get('period_key')
            logger.debug(f"매출 성장률({latest.get('period_key')} vs {year_ago.get('period_key')}): {growth}")
        elif quarterly:
            logger.debug(f"매출 YoY 계산에 필요한 같은 회계분기 데이터 부족: {len(quarterly)}개")
    
    def _best_flow_data_for_tags(
        self,
        us_gaap_facts: Dict[str, Any],
        tags: List[str],
        unit_types: List[str],
    ) -> Optional[Tuple[pd.Timestamp, List[Dict[str, Any]], List[Dict[str, Any]]]]:
        best_data = None
        for tag in tags:
            tag_data = us_gaap_facts.get(tag)
            if not tag_data:
                continue
            quarterly = self._quarterly_flow_series(tag_data, unit_types)
            annual = self._annual_series(tag_data, unit_types)
            if quarterly or annual:
                latest_end = self._latest_end_key(quarterly + annual)
                if best_data is None or latest_end > best_data[0]:
                    best_data = (latest_end, quarterly, annual)
        return best_data

    def _extract_income_metrics(self, us_gaap_facts: Dict[str, Any], metrics: Dict[str, Any]) -> None:
        """Extract operating income and net income metrics from us-gaap facts."""
        operating_income_tags = [
            "OperatingIncomeLoss",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        ]
        net_income_tags = [
            "NetIncomeLoss",
            "ProfitLoss",
            "NetIncome",
            "NetIncomeLossAvailableToCommonStockholdersBasic",
            "NetIncomeLossAttributableToParent",
        ]

        operating_data = self._best_flow_data_for_tags(us_gaap_facts, operating_income_tags, ["USD"])
        if operating_data:
            latest_end, quarterly, annual = operating_data
            if not self._is_stale_concept(latest_end, metrics.get('_latest_fact_end')):
                if quarterly:
                    metrics['_quarterly_operating_income_values'] = [
                        (record['period_key'], record['end'], record['val'])
                        for record in quarterly
                    ]
                if annual:
                    metrics['_annual_operating_income_values'] = [
                        (record['fy'], record['end'], record['val'])
                        for record in annual
                    ]

        net_data = self._best_flow_data_for_tags(us_gaap_facts, net_income_tags, ["USD"])
        if not net_data:
            return

        latest_end, quarterly, annual = net_data
        if self._is_stale_concept(latest_end, metrics.get('_latest_fact_end')):
            logger.debug("Skipping stale income facts")
            return

        if quarterly:
            metrics['_quarterly_income_values'] = [
                (record['period_key'], record['end'], record['val'])
                for record in quarterly
            ]
        if annual:
            metrics['_annual_income_values'] = [
                (record['fy'], record['end'], record['val'])
                for record in annual
            ]
    
    @staticmethod
    def _instant_values(us_gaap_facts: Dict[str, Any], tags: List[str]) -> List[Tuple[str, float]]:
        """Return sorted instant balance-sheet values for any of the supplied tags."""
        values: List[Tuple[pd.Timestamp, str, float]] = []
        for tag in tags:
            tag_data = us_gaap_facts.get(tag)
            if not tag_data or 'USD' not in tag_data.get('units', {}):
                continue
            for item in tag_data['units']['USD']:
                if normalized_form(item) not in {'10-Q', '10-K'}:
                    continue
                end_date = item_end_date(item)
                value = safe_float(item.get('val'))
                if not end_date or value is None:
                    continue
                try:
                    values.append((pd.Timestamp(end_date), item.get('filed', ''), value))
                except Exception:
                    continue

        values.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [(end.date().isoformat(), value) for end, _, value in values]

    @staticmethod
    def _latest_instant_value(us_gaap_facts: Dict[str, Any], tags: List[str]) -> Optional[Tuple[str, float]]:
        """Return the newest instant balance-sheet value for any of the supplied tags."""
        values = XBRLFactsParser._instant_values(us_gaap_facts, tags)
        return values[0] if values else None

    def _extract_debt_metrics(self, us_gaap_facts: Dict[str, Any], metrics: Dict[str, Any]) -> None:
        """Extract interest-bearing debt, avoiding total liabilities as a debt proxy."""
        debt_components = {
            'debt_current': [
                'LongTermDebtCurrent',
                'CurrentPortionOfLongTermDebt',
                'CurrentPortionOfLongTermDebtAndFinanceLeaseObligations',
                'LongTermDebtAndFinanceLeaseObligationsCurrent',
            ],
            'debt_noncurrent': [
                'LongTermDebtNoncurrent',
                'LongTermDebtAndFinanceLeaseObligationsNoncurrent',
                'LongTermDebtAndFinanceLeaseObligations',
            ],
            'short_term_debt': [
                'ShortTermBorrowings',
                'ShortTermDebt',
                'ShortTermBankLoansAndNotesPayable',
                'CommercialPaper',
            ],
        }

        component_total = 0.0
        found_component = False
        for metric_name, tags in debt_components.items():
            value = self._latest_instant_value(us_gaap_facts, tags)
            if value is None:
                continue
            _, amount = value
            metrics[metric_name] = amount
            component_total += amount
            found_component = True

        if found_component:
            metrics['debt'] = component_total
            return

        total_debt = self._latest_instant_value(
            us_gaap_facts,
            [
                'LongTermDebt',
                'DebtAndFinanceLeaseObligations',
                'ShortTermBorrowingsAndLongTermDebt',
            ],
        )
        if total_debt is not None:
            _, amount = total_debt
            metrics['debt'] = amount

    def _extract_balance_sheet_metrics(self, us_gaap_facts: Dict[str, Any], metrics: Dict[str, Any]) -> None:
        """Extract Balance Sheet metrics from us-gaap facts."""
        assets = self._latest_instant_value(us_gaap_facts, ["Assets"])
        if assets is not None:
            _, value = assets
            metrics['assets'] = value

        liabilities = self._latest_instant_value(us_gaap_facts, ["Liabilities"])
        if liabilities is not None:
            _, value = liabilities
            metrics['liabilities'] = value

        equity_tags = [
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ]
        equity_values = self._instant_values(us_gaap_facts, equity_tags)
        if equity_values:
            _, value = equity_values[0]
            metrics['equity'] = value
            metrics['_equity_values'] = equity_values

        self._extract_debt_metrics(us_gaap_facts, metrics)
    
    def _calculate_derived_metrics(self, metrics: Dict[str, Any]) -> None:
        """Calculate derived metrics from extracted financial data."""
        # Calculate profit margin using like-for-like periods. Prefer operating
        # income to match the screener's operating-margin criterion; fall back to
        # net income when operating income is unavailable.
        income_sources = [
            ("_quarterly_operating_income_values", "operating_income"),
            ("_quarterly_income_values", "net_income"),
        ]
        if '_quarterly_revenue_values' in metrics:
            revenue_dict = {period: val for period, _, val in metrics['_quarterly_revenue_values']}
            for income_key, source in income_sources:
                if income_key not in metrics:
                    continue
                income_dict = {period: val for period, _, val in metrics[income_key]}
                common_periods = set(revenue_dict.keys()) & set(income_dict.keys())
                if common_periods:
                    latest_period = sorted(common_periods, reverse=True)[0]
                    latest_revenue = revenue_dict[latest_period]
                    latest_income = income_dict[latest_period]
                    if latest_revenue > 0:
                        metrics['profit_margin'] = latest_income / latest_revenue
                        metrics['profit_margin_source'] = source
                        break
        elif '_annual_revenue_values' in metrics:
            revenue_dict = {year: val for year, _, val in metrics['_annual_revenue_values']}
            for income_key, source in [
                ("_annual_operating_income_values", "operating_income"),
                ("_annual_income_values", "net_income"),
            ]:
                if income_key not in metrics:
                    continue
                income_dict = {year: val for year, _, val in metrics[income_key]}
                common_years = set(revenue_dict.keys()) & set(income_dict.keys())
                if common_years:
                    latest_year = max(common_years)
                    latest_revenue = revenue_dict[latest_year]
                    latest_income = income_dict[latest_year]
                    if latest_revenue > 0:
                        metrics['profit_margin'] = latest_income / latest_revenue
                        metrics['profit_margin_source'] = source
                        break
        
        # Calculate ROE using average equity when two balance-sheet values exist.
        if 'equity' in metrics and '_annual_income_values' in metrics:
            annual_income = metrics['_annual_income_values']
            equity_values = [value for _, value in metrics.get('_equity_values', []) if value and value > 0]
            if annual_income and equity_values:
                latest_income = annual_income[0][2]
                equity_base = sum(equity_values[:2]) / 2 if len(equity_values) >= 2 else equity_values[0]
                metrics['roe'] = latest_income / equity_base
        
        # Calculate Debt-to-Equity from interest-bearing debt, not total liabilities.
        if 'equity' in metrics and 'debt' in metrics and metrics['equity'] > 0:
            metrics['debt_to_equity'] = metrics['debt'] / metrics['equity']
        if 'equity' in metrics and 'liabilities' in metrics and metrics['equity'] > 0:
            metrics['liabilities_to_equity'] = metrics['liabilities'] / metrics['equity']
        
        # Remove temporary calculation values
        for key in list(metrics.keys()):
            if key.startswith('_'):
                del metrics[key]
    
    def process_all(self, limit: Optional[int] = None, force: bool = False) -> pd.DataFrame:
        """
        Process all company facts files and generate metrics.
        
        Args:
            limit: Optional limit on number of companies to process
            force: If True, reprocess even if output file exists
            
        Returns:
            DataFrame containing processed metrics
        """
        # Check if output file exists and we're not forcing reprocessing
        if os.path.exists(self.parsed_metrics_file) and not force:
            logger.info(f"Loading existing metrics file: {self.parsed_metrics_file}")
            return pd.read_parquet(self.parsed_metrics_file)
        
        # Get company facts files (limited if specified)
        files = self.get_company_facts_files()
        
        if not files:
            logger.warning("No company facts files found.")
            return pd.DataFrame()
        
        if limit and limit < len(files):
            files = files[:limit]
        
        # Process each file with better error handling
        metrics = []
        success_count = 0
        error_count = 0
        
        for i, file_path in enumerate(files):
            if i % 10 == 0:
                logger.info(f"Processing file {i+1}/{len(files)}")
            
            try:
                company_metrics = self.process_company_file(file_path)
                # Add metrics only if they have basic info
                if 'cik' in company_metrics:
                    metrics.append(company_metrics)
                    success_count += 1
            except Exception as e:
                logger.error(f"Unexpected error processing {file_path}: {e}")
                error_count += 1
        
        logger.info(f"File processing complete. Success: {success_count}, Errors: {error_count}")
        
        # Create DataFrame
        df = pd.DataFrame(metrics)
        
        # Check if the DataFrame has any rows
        if df.empty:
            logger.warning("No metrics extracted - empty DataFrame")
            return df
            
        # Ensure CIK column exists
        if 'cik' not in df.columns:
            logger.error("Critical error: 'cik' column missing from processed data")
            return df
        
        # Clean up and validate numeric fields
        cols_to_convert = [
            'quarterly_eps_growth', 'annual_eps_cagr', 'revenue_growth',
            'profit_margin', 'roe', 'debt_to_equity'
        ]
        
        for col in cols_to_convert:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                # Count non-null values for logging
                count = df[col].notna().sum()
                logger.info(f"Metric '{col}': {count} companies have values ({count/len(df)*100:.1f}%)")
            else:
                logger.warning(f"Column '{col}' not found in processed data")
        
        # Save to parquet file
        if not df.empty:
            output_dir = os.path.dirname(self.parsed_metrics_file)
            os.makedirs(output_dir, exist_ok=True)
            df.to_parquet(self.parsed_metrics_file, index=False)
            logger.info(f"Saved metrics for {len(df)} companies to {self.parsed_metrics_file}")
        
        return df
