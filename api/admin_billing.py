"""Admin billing summary for operator console."""

from __future__ import annotations

import logging
import os

from flask import Blueprint, jsonify
from flask_cors import cross_origin

from auth.decorators import require_site_admin

logger = logging.getLogger(__name__)

admin_billing_bp = Blueprint('admin_billing', __name__)


@admin_billing_bp.route('/api/admin/billing/summary', methods=['GET'])
@cross_origin()
@require_site_admin
def get_admin_billing_summary():
    """Cross-tenant MAU vs plan summary for operator billing view."""
    try:
        from api.dashboard_api import _enrich_admin_site, _load_admin_sites

        rows = []
        over_limit = 0
        for site in _load_admin_sites():
            enriched = _enrich_admin_site(site)
            mau_current = int(enriched.get('mau_current') or 0)
            mau_limit = enriched.get('mau_limit')
            overage = int(enriched.get('mau_overage') or 0)
            if mau_limit and mau_current > mau_limit:
                over_limit += 1
            stripe_id = enriched.get('stripe_customer_id') or ''
            rows.append({
                'site_id': enriched.get('site_id'),
                'site_domain': enriched.get('site_domain'),
                'company_name': enriched.get('company_name'),
                'plan': enriched.get('plan') or 'starter',
                'status': enriched.get('status') or 'active',
                'mau_current': mau_current,
                'mau_limit': mau_limit,
                'mau_overage': overage,
                'stripe_customer_id': stripe_id,
                'stripe_dashboard_url': (
                    f'https://dashboard.stripe.com/customers/{stripe_id}' if stripe_id else None
                ),
                'billing_status': 'over_limit' if overage else 'ok',
            })

        rows.sort(key=lambda r: r.get('mau_overage') or 0, reverse=True)

        return jsonify({
            'success': True,
            'sites': rows,
            'total_sites': len(rows),
            'sites_over_limit': over_limit,
            'stripe_mode': os.environ.get('STRIPE_SECRET_KEY', '')[:7] + '…' if os.environ.get('STRIPE_SECRET_KEY') else None,
        })
    except Exception as exc:
        logger.error('Admin billing summary failed: %s', exc)
        return jsonify({'success': False, 'error': 'billing_summary_failed'}), 500
