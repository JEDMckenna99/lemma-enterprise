"""
Lemma Enterprise - Enhanced Analytics Service
Provides comprehensive analytics, monitoring, and business intelligence for pilot readiness.
"""

import os
import json
import csv
import time
import threading
# Conditional import for file locking (Unix/Linux only)
try:
    import fcntl
    FILE_LOCKING_AVAILABLE = True
except ImportError:
    # Windows doesn't have fcntl, but we can still provide thread safety
    FILE_LOCKING_AVAILABLE = False
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict, Counter
import logging
from flask import current_app

logger = logging.getLogger(__name__)

class AnalyticsService:
    """Enhanced analytics service for comprehensive business intelligence and monitoring."""
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or 'instance/data'
        self.analytics_dir = os.path.join(self.storage_dir, 'analytics')
        self.customers_dir = os.path.join(self.storage_dir, 'customers')
        self.reports_dir = os.path.join(self.storage_dir, 'reports')
        
        # Thread lock for Windows compatibility
        self._file_lock = threading.Lock() if not FILE_LOCKING_AVAILABLE else None
        
        # Ensure directories exist
        for directory in [self.analytics_dir, self.customers_dir, self.reports_dir]:
            os.makedirs(directory, exist_ok=True)

    def log_verification_event(self, customer_id: str, event_type: str = 'verification', 
                             metadata: Dict = None) -> bool:
        """Log a verification event with enhanced metadata and file locking to prevent race conditions."""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            usage_file = os.path.join(self.analytics_dir, f'{today}.json')
            
            # Use appropriate locking mechanism based on platform
            if FILE_LOCKING_AVAILABLE:
                return self._log_with_fcntl_lock(usage_file, customer_id, event_type, metadata, today)
            else:
                return self._log_with_thread_lock(usage_file, customer_id, event_type, metadata, today)
                
        except Exception as e:
            logger.error(f"Failed to log verification event: {e}")
            return False

    def _log_with_fcntl_lock(self, usage_file: str, customer_id: str, event_type: str, metadata: Dict, today: str) -> bool:
        """Log verification event using fcntl file locking (Unix/Linux)."""
        with open(usage_file, 'a+') as f:
            try:
                # Acquire exclusive lock
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                
                # Move to beginning to read existing content
                f.seek(0)
                content = f.read()
                
                daily_data = self._get_or_create_daily_data(content, today)
                self._add_event_to_daily_data(daily_data, customer_id, event_type, metadata)
                
                # Write updated data (truncate and rewrite)
                f.seek(0)
                f.truncate()
                json.dump(daily_data, f, indent=2)
                f.flush()  # Ensure data is written to disk
                
            finally:
                # Release lock
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return True

    def _log_with_thread_lock(self, usage_file: str, customer_id: str, event_type: str, metadata: Dict, today: str) -> bool:
        """Log verification event using thread locking (Windows fallback)."""
        # Ensure we have a valid lock
        if self._file_lock is None:
            # Fallback: no locking, but still functional
            return self._log_without_lock(usage_file, customer_id, event_type, metadata, today)
        
        # We know _file_lock is not None here, so it's safe to use in context manager
        with self._file_lock:
            # Load existing data or create new structure
            if os.path.exists(usage_file):
                with open(usage_file, 'r') as f:
                    content = f.read()
            else:
                content = ""
            
            daily_data = self._get_or_create_daily_data(content, today)
            self._add_event_to_daily_data(daily_data, customer_id, event_type, metadata)
            
            # Write updated data
            with open(usage_file, 'w') as f:
                json.dump(daily_data, f, indent=2)
        return True

    def _log_without_lock(self, usage_file: str, customer_id: str, event_type: str, metadata: Dict, today: str) -> bool:
        """Log verification event without locking (fallback)."""
        # Load existing data or create new structure
        if os.path.exists(usage_file):
            with open(usage_file, 'r') as f:
                content = f.read()
        else:
            content = ""
        
        daily_data = self._get_or_create_daily_data(content, today)
        self._add_event_to_daily_data(daily_data, customer_id, event_type, metadata)
        
        # Write updated data
        with open(usage_file, 'w') as f:
            json.dump(daily_data, f, indent=2)
        return True

    def _get_or_create_daily_data(self, content: str, today: str) -> Dict:
        """Get existing daily data or create new structure."""
        if content.strip():
            return json.loads(content)
        else:
            return {
                'date': today,
                'customers': {},
                'summary': {
                    'total_verifications': 0,
                    'unique_customers': 0,
                    'events_by_type': {}
                }
            }

    def _add_event_to_daily_data(self, daily_data: Dict, customer_id: str, event_type: str, metadata: Dict):
        """Add event to daily data structure."""
        # Initialize customer data if not exists
        if customer_id not in daily_data['customers']:
            daily_data['customers'][customer_id] = {
                'verifications': 0,
                'events': [],
                'first_verification': datetime.now().isoformat(),
                'last_verification': None
            }
        
        # Add event
        event = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'metadata': metadata or {}
        }
        
        daily_data['customers'][customer_id]['events'].append(event)
        daily_data['customers'][customer_id]['verifications'] += 1
        daily_data['customers'][customer_id]['last_verification'] = event['timestamp']
        
        # Update summary
        daily_data['summary']['total_verifications'] += 1
        daily_data['summary']['unique_customers'] = len(daily_data['customers'])
        
        if event_type not in daily_data['summary']['events_by_type']:
            daily_data['summary']['events_by_type'][event_type] = 0
        daily_data['summary']['events_by_type'][event_type] += 1

    def get_customer_analytics(self, customer_id: str, days: int = 30) -> Dict:
        """Get comprehensive analytics for a specific customer."""
        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            analytics = {
                'customer_id': customer_id,
                'period': {
                    'start': start_date.strftime('%Y-%m-%d'),
                    'end': end_date.strftime('%Y-%m-%d'),
                    'days': days
                },
                'usage': {
                    'total_verifications': 0,
                    'daily_breakdown': {},
                    'hourly_patterns': defaultdict(int),
                    'event_types': defaultdict(int)
                },
                'performance': {
                    'average_daily_usage': 0,
                    'peak_day': None,
                    'peak_day_count': 0,
                    'active_days': 0,
                    'usage_trend': 'stable'  # 'growing', 'declining', 'stable'
                },
                'financial': {
                    'estimated_cost': 0,
                    'pricing_tier': 'network_pricing',
                    'monthly_rate': 0,
                    'verification_fee': 2.00,
                    'network_discount': 0
                }
            }
            
            # Process daily data
            current_date = start_date
            daily_totals = []
            
            while current_date <= end_date:
                date_str = current_date.strftime('%Y-%m-%d')
                usage_file = os.path.join(self.analytics_dir, f'{date_str}.json')
                
                day_usage = 0
                if os.path.exists(usage_file):
                    with open(usage_file, 'r') as f:
                        daily_data = json.load(f)
                        customer_data = daily_data.get('customers', {}).get(customer_id, {})
                        day_usage = customer_data.get('verifications', 0)
                        
                        # Process events for patterns
                        for event in customer_data.get('events', []):
                            event_time = datetime.fromisoformat(event['timestamp'])
                            hour = event_time.hour
                            analytics['usage']['hourly_patterns'][hour] += 1
                            analytics['usage']['event_types'][event.get('type', 'verification')] += 1
                
                analytics['usage']['daily_breakdown'][date_str] = day_usage
                analytics['usage']['total_verifications'] += day_usage
                daily_totals.append(day_usage)
                
                if day_usage > 0:
                    analytics['performance']['active_days'] += 1
                    
                if day_usage > analytics['performance']['peak_day_count']:
                    analytics['performance']['peak_day'] = date_str
                    analytics['performance']['peak_day_count'] = day_usage
                
                current_date += timedelta(days=1)
            
            # Calculate performance metrics
            if analytics['performance']['active_days'] > 0:
                analytics['performance']['average_daily_usage'] = (
                    analytics['usage']['total_verifications'] / analytics['performance']['active_days']
                )
            
            # Calculate usage trend (simple linear trend)
            if len(daily_totals) >= 7:
                first_week = sum(daily_totals[:7])
                last_week = sum(daily_totals[-7:])
                if last_week > first_week * 1.2:
                    analytics['performance']['usage_trend'] = 'growing'
                elif last_week < first_week * 0.8:
                    analytics['performance']['usage_trend'] = 'declining'
            
            # Calculate financial metrics using network pricing model
            total_verifications = analytics['usage']['total_verifications']
            
            # Import network pricing calculation
            try:
                from lemma.routes.onboarding import calculate_network_pricing
                network_pricing = calculate_network_pricing()
                monthly_rate = network_pricing['current_rate']
                verification_fee = network_pricing['verification_fee']
                
                analytics['financial']['estimated_cost'] = monthly_rate * total_verifications
                analytics['financial']['pricing_tier'] = network_pricing['tier']['name']
                analytics['financial']['monthly_rate'] = monthly_rate
                analytics['financial']['verification_fee'] = verification_fee
                analytics['financial']['network_discount'] = network_pricing['discount_percentage']
                
            except ImportError:
                # Fallback if import fails
                base_rate = 0.10
                analytics['financial']['estimated_cost'] = base_rate * total_verifications
                analytics['financial']['pricing_tier'] = 'network_pricing'
                analytics['financial']['monthly_rate'] = base_rate
            
            return analytics
            
        except Exception as e:
            logger.error(f"Error getting customer analytics: {e}")
            return {}

    def get_platform_analytics(self, days: int = 30) -> Dict:
        """Get platform-wide analytics for business intelligence."""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            platform_analytics = {
                'period': {
                    'start': start_date.strftime('%Y-%m-%d'),
                    'end': end_date.strftime('%Y-%m-%d'),
                    'days': days
                },
                'customers': {
                    'total_customers': 0,
                    'active_customers': 0,
                    'new_customers': 0,
                    'customers_by_tier': {'free': 0, 'standard': 0, 'enterprise': 0}
                },
                'usage': {
                    'total_verifications': 0,
                    'daily_breakdown': {},
                    'peak_day': None,
                    'peak_day_count': 0
                },
                'financial': {
                    'total_revenue': 0,
                    'revenue_by_tier': {'free': 0, 'standard': 0, 'enterprise': 0},
                    'average_revenue_per_customer': 0
                },
                'growth': {
                    'daily_growth_rate': 0,
                    'customer_acquisition_rate': 0,
                    'usage_growth_rate': 0
                },
                'top_customers': []
            }
            
            # Get all customers
            all_customers = set()
            daily_totals = []
            
            # Process daily data
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime('%Y-%m-%d')
                usage_file = os.path.join(self.analytics_dir, f'{date_str}.json')
                
                day_total = 0
                if os.path.exists(usage_file):
                    with open(usage_file, 'r') as f:
                        daily_data = json.load(f)
                        day_total = daily_data.get('summary', {}).get('total_verifications', 0)
                        all_customers.update(daily_data.get('customers', {}).keys())
                
                platform_analytics['usage']['daily_breakdown'][date_str] = day_total
                platform_analytics['usage']['total_verifications'] += day_total
                daily_totals.append(day_total)
                
                if day_total > platform_analytics['usage']['peak_day_count']:
                    platform_analytics['usage']['peak_day'] = date_str
                    platform_analytics['usage']['peak_day_count'] = day_total
                
                current_date += timedelta(days=1)
            
            # Analyze each customer
            customer_analytics = {}
            for customer_id in all_customers:
                customer_data = self.get_customer_analytics(customer_id, days)
                customer_analytics[customer_id] = customer_data
                
                if customer_data.get('usage', {}).get('total_verifications', 0) > 0:
                    platform_analytics['customers']['active_customers'] += 1
                
                # Count by tier
                tier = customer_data.get('financial', {}).get('pricing_tier', 'free')
                platform_analytics['customers']['customers_by_tier'][tier] += 1
                
                # Add revenue
                cost = customer_data.get('financial', {}).get('estimated_cost', 0)
                platform_analytics['financial']['total_revenue'] += cost
                platform_analytics['financial']['revenue_by_tier'][tier] += cost
            
            platform_analytics['customers']['total_customers'] = len(all_customers)
            
            # Calculate average revenue per customer
            if platform_analytics['customers']['active_customers'] > 0:
                platform_analytics['financial']['average_revenue_per_customer'] = (
                    platform_analytics['financial']['total_revenue'] / 
                    platform_analytics['customers']['active_customers']
                )
            
            # Get top customers by usage
            customer_usage = [(cid, data.get('usage', {}).get('total_verifications', 0)) 
                             for cid, data in customer_analytics.items()]
            customer_usage.sort(key=lambda x: x[1], reverse=True)
            platform_analytics['top_customers'] = customer_usage[:10]
            
            # Calculate growth rates
            if len(daily_totals) >= 14:
                first_week_avg = sum(daily_totals[:7]) / 7
                last_week_avg = sum(daily_totals[-7:]) / 7
                if first_week_avg > 0:
                    platform_analytics['growth']['usage_growth_rate'] = (
                        (last_week_avg - first_week_avg) / first_week_avg * 100
                    )
            
            return platform_analytics
            
        except Exception as e:
            logger.error(f"Error getting platform analytics: {e}")
            return {}

    def generate_analytics_report(self, report_type: str = 'daily', 
                                format: str = 'json') -> Tuple[bool, str, Any]:
        """Generate comprehensive analytics reports."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            if report_type == 'daily':
                today = datetime.now().strftime('%Y-%m-%d')
                usage_file = os.path.join(self.analytics_dir, f'{today}.json')
                
                if os.path.exists(usage_file):
                    with open(usage_file, 'r') as f:
                        report_data = json.load(f)
                else:
                    report_data = {'error': 'No data available for today'}
                    
            elif report_type == 'weekly':
                report_data = self.get_platform_analytics(7)
                
            elif report_type == 'monthly':
                report_data = self.get_platform_analytics(30)
                
            elif report_type == 'customer_summary':
                report_data = {}
                # Get all customers and their analytics
                for customer_file in os.listdir(self.customers_dir):
                    if customer_file.endswith('.json'):
                        customer_id = customer_file.replace('.json', '')
                        customer_analytics = self.get_customer_analytics(customer_id, 30)
                        report_data[customer_id] = customer_analytics
                        
            else:
                return False, f"Unknown report type: {report_type}", None
            
            # Save report
            if format == 'json':
                report_filename = f"{report_type}_report_{timestamp}.json"
                report_path = os.path.join(self.reports_dir, report_filename)
                
                with open(report_path, 'w') as f:
                    json.dump(report_data, f, indent=2)
                    
            elif format == 'csv':
                report_filename = f"{report_type}_report_{timestamp}.csv"
                report_path = os.path.join(self.reports_dir, report_filename)
                
                # Convert to CSV format
                self._write_csv_report(report_data, report_path, report_type)
                
            else:
                return False, f"Unsupported format: {format}", None
            
            return True, report_path, report_data
            
        except Exception as e:
            logger.error(f"Error generating analytics report: {e}")
            return False, f"Error generating report: {str(e)}", None

    def _write_csv_report(self, data: Dict, file_path: str, report_type: str):
        """Write analytics data to CSV format."""
        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            if report_type == 'daily':
                writer = csv.writer(csvfile)
                writer.writerow(['Date', 'Customer ID', 'Verifications', 'Events'])
                
                date = data.get('date', 'unknown')
                for customer_id, customer_data in data.get('customers', {}).items():
                    writer.writerow([
                        date,
                        customer_id,
                        customer_data.get('verifications', 0),
                        len(customer_data.get('events', []))
                    ])
                    
            elif report_type in ['weekly', 'monthly']:
                writer = csv.writer(csvfile)
                writer.writerow([
                    'Metric', 'Value'
                ])
                
                # Flatten the nested data structure
                def flatten_dict(d, parent_key='', sep='_'):
                    items = []
                    for k, v in d.items():
                        new_key = f"{parent_key}{sep}{k}" if parent_key else k
                        if isinstance(v, dict):
                            items.extend(flatten_dict(v, new_key, sep=sep).items())
                        else:
                            items.append((new_key, v))
                    return dict(items)
                
                flattened = flatten_dict(data)
                for key, value in flattened.items():
                    writer.writerow([key, value])

    def get_system_health(self) -> Dict:
        """Get system health and analytics service status."""
        try:
            health = {
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'directories': {},
                'recent_activity': {},
                'storage_usage': {}
            }
            
            # Check directory status
            for name, path in [
                ('analytics', self.analytics_dir),
                ('customers', self.customers_dir),
                ('reports', self.reports_dir)
            ]:
                health['directories'][name] = {
                    'exists': os.path.exists(path),
                    'writable': os.access(path, os.W_OK) if os.path.exists(path) else False,
                    'file_count': len(os.listdir(path)) if os.path.exists(path) else 0
                }
            
            # Check recent activity (last 7 days)
            recent_days = []
            for i in range(7):
                date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                usage_file = os.path.join(self.analytics_dir, f'{date}.json')
                if os.path.exists(usage_file):
                    recent_days.append(date)
            
            health['recent_activity'] = {
                'days_with_data': len(recent_days),
                'last_activity': recent_days[0] if recent_days else None,
                'data_continuity': len(recent_days) == 7
            }
            
            # Check storage usage
            total_size = 0
            file_count = 0
            for root, dirs, files in os.walk(self.storage_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.exists(file_path):
                        total_size += os.path.getsize(file_path)
                        file_count += 1
            
            health['storage_usage'] = {
                'total_files': file_count,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2)
            }
            
            # Determine overall health status
            if not all(dir_info['exists'] for dir_info in health['directories'].values()):
                health['status'] = 'degraded'
            elif health['recent_activity']['days_with_data'] == 0:
                health['status'] = 'warning'
            
            return health
            
        except Exception as e:
            logger.error(f"Error checking system health: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

# Global analytics service instance
analytics_service = None

def get_analytics_service() -> AnalyticsService:
    """Get or create the global analytics service instance."""
    global analytics_service
    
    if analytics_service is None:
        storage_dir = os.getenv('LEMMA_STORAGE_DIR', 'instance/data')
        analytics_service = AnalyticsService(storage_dir)
    
    return analytics_service 