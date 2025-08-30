"""
Database models for Lemma.id platform (Mock implementation for testing)
"""

from datetime import datetime
from enum import Enum
import uuid

class ActivityType(Enum):
    POH_NETWORK = "poh_network"
    SITE_IAM = "site_iam"

class PaymentStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"

class BillingInvoice:
    def __init__(self, invoice_id, customer_id, amount, status=PaymentStatus.PENDING):
        self.invoice_id = invoice_id
        self.customer_id = customer_id
        self.amount = amount
        self.status = status
        self.created_at = datetime.utcnow()

class Site:
    def __init__(self, site_id, site_domain, company_name, admin_email, plan='starter'):
        self.site_id = site_id
        self.site_domain = site_domain
        self.company_name = company_name
        self.admin_email = admin_email
        self.plan = plan
        self.api_key = f"lemma_api_{uuid.uuid4().hex[:16]}"
        self.oauth_client_id = f"lemma_oauth_{site_id}"
        self.oauth_client_secret = f"secret_{uuid.uuid4().hex[:16]}"
        self.created_at = datetime.utcnow()

class Permission:
    def __init__(self, site_id, permission_id, display_name, scope, conditions=None, 
                 delegation_allowed=False, priority=0, created_by=None):
        self.site_id = site_id
        self.permission_id = permission_id
        self.display_name = display_name
        self.scope = scope
        self.conditions = conditions or []
        self.delegation_allowed = delegation_allowed
        self.priority = priority
        self.created_at = datetime.utcnow()
        self.created_by = created_by

class DatabaseManager:
    """Mock database manager for testing"""
    
    def __init__(self):
        self.sites = {}
        self.permissions = {}
    
    def create_site(self, data):
        """Create a new site"""
        site_id = f"site_{uuid.uuid4().hex[:8]}"
        site = Site(
            site_id=site_id,
            site_domain=data['site_domain'],
            company_name=data['company_name'],
            admin_email=data['admin_email'],
            plan=data.get('plan', 'starter')
        )
        self.sites[site_id] = site
        return site
    
    def get_site(self, site_id):
        """Get site by ID"""
        return self.sites.get(site_id)
    
    def create_permission(self, site_id, data):
        """Create a new permission"""
        permission = Permission(
            site_id=site_id,
            permission_id=data['permission_id'],
            display_name=data['display_name'],
            scope=data['scope'],
            conditions=data.get('conditions', []),
            delegation_allowed=data.get('delegation_allowed', False),
            priority=data.get('priority', 0),
            created_by=data.get('created_by')
        )
        perm_key = f"{site_id}_{data['permission_id']}"
        self.permissions[perm_key] = permission
        return permission
    
    def track_user_activity(self, customer_id, user_id, activity_type, site_id=None):
        """Track user activity for billing"""
        # Mock implementation - just return success
        return {
            'success': True,
            'customer_id': customer_id,
            'user_id': user_id,
            'activity_type': activity_type.value,
            'site_id': site_id,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def get_monthly_active_users(self, customer_id, year, month):
        """Get monthly active users for billing"""
        # Mock implementation - return sample data
        return {
            'customer_id': customer_id,
            'year': year,
            'month': month,
            'poh_mau': 1247,
            'iam_mau': 856,
            'total_operations': 45623
        }
    
    def calculate_monthly_bill(self, customer_id, year, month):
        """Calculate monthly bill for a customer"""
        usage = self.get_monthly_active_users(customer_id, year, month)
        poh_cost = usage['poh_mau'] * 0.05
        iam_cost = usage['iam_mau'] * 0.15
        total_cost = poh_cost + iam_cost
        
        return {
            'customer_id': customer_id,
            'year': year,
            'month': month,
            'poh_mau': usage['poh_mau'],
            'iam_mau': usage['iam_mau'],
            'poh_cost': round(poh_cost, 2),
            'iam_cost': round(iam_cost, 2),
            'total_cost': round(total_cost, 2),
            'savings_vs_competitors': round(max(0, (usage['poh_mau'] + usage['iam_mau']) * 2.0 - total_cost), 2)
        }

# Global database instance for testing
db = DatabaseManager()