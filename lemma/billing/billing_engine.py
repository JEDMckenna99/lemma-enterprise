#!/usr/bin/env python3
"""
💰 LEMMA BILLING ENGINE
=======================
Calculates charges using configurable formulas per contract
Generates PDF/CSV invoices and posts to Stripe/Billing API
"""

import json
import os
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal, ROUND_HALF_UP
import csv
import io

# PDF generation
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from .rollup_engine import get_rollup_engine

logger = logging.getLogger(__name__)

class BillingEngine:
    """Production-grade billing engine with configurable pricing formulas."""
    
    def __init__(self, storage_dir: str = None):
        self.storage_dir = storage_dir or os.environ.get('STORAGE_DIR', '.lemma_enterprise')
        self.billing_dir = os.path.join(self.storage_dir, 'billing', 'invoices')
        self.contracts_dir = os.path.join(self.storage_dir, 'billing', 'contracts')
        
        # Ensure directories exist
        os.makedirs(self.billing_dir, exist_ok=True)
        os.makedirs(self.contracts_dir, exist_ok=True)
        
        # Default pricing (can be overridden per contract)
        self.default_rates = {
            "mah_rate": Decimal("0.10"),      # $0.10 per Monthly Active Human
            "new_human_rate": Decimal("2.00"), # $2.00 per New Human
            "currency": "USD"
        }
        
        # Load contract configurations
        self.contracts = self._load_contracts()
        
        # Rollup engine instance (for testing)
        self._rollup_engine = None
        
    def _load_contracts(self) -> Dict[str, Dict[str, Any]]:
        """Load customer contract configurations."""
        contracts = {}
        
        # Load default contract
        contracts["default"] = {
            "mah_rate": self.default_rates["mah_rate"],
            "new_human_rate": self.default_rates["new_human_rate"],
            "currency": self.default_rates["currency"],
            "billing_day": 1,  # 1st of month
            "payment_terms": 30,  # Net 30
            "volume_discounts": []
        }
        
        # Load custom contracts from files
        if os.path.exists(self.contracts_dir):
            for filename in os.listdir(self.contracts_dir):
                if filename.endswith('.json'):
                    contract_id = filename[:-5]  # Remove .json
                    try:
                        with open(os.path.join(self.contracts_dir, filename), 'r') as f:
                            contract_data = json.load(f)
                            # Convert decimal strings to Decimal objects
                            if 'mah_rate' in contract_data:
                                contract_data['mah_rate'] = Decimal(str(contract_data['mah_rate']))
                            if 'new_human_rate' in contract_data:
                                contract_data['new_human_rate'] = Decimal(str(contract_data['new_human_rate']))
                            contracts[contract_id] = contract_data
                    except Exception as e:
                        logger.error(f"Error loading contract {contract_id}: {e}")
        
        return contracts
    
    def set_rollup_engine(self, rollup_engine):
        """Set the rollup engine instance (for testing)."""
        self._rollup_engine = rollup_engine
    
    def create_contract(self, site_id: str, contract_terms: Dict[str, Any]) -> bool:
        """Create a custom contract for a customer."""
        try:
            # Validate and normalize contract terms
            normalized_contract = {
                "site_id": site_id,
                "mah_rate": Decimal(str(contract_terms.get("mah_rate", self.default_rates["mah_rate"]))),
                "new_human_rate": Decimal(str(contract_terms.get("new_human_rate", self.default_rates["new_human_rate"]))),
                "currency": contract_terms.get("currency", "USD"),
                "billing_day": contract_terms.get("billing_day", 1),
                "payment_terms": contract_terms.get("payment_terms", 30),
                "volume_discounts": contract_terms.get("volume_discounts", []),
                "created_at": time.time(),
                "active": True
            }
            
            # Save contract
            contract_file = os.path.join(self.contracts_dir, f'{site_id}.json')
            with open(contract_file, 'w') as f:
                # Convert Decimal to string for JSON serialization
                contract_json = {}
                for key, value in normalized_contract.items():
                    if isinstance(value, Decimal):
                        contract_json[key] = str(value)
                    else:
                        contract_json[key] = value
                json.dump(contract_json, f, indent=2)
            
            # Update in-memory contracts
            self.contracts[site_id] = normalized_contract
            
            logger.info(f"Created contract for site {site_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating contract for {site_id}: {e}")
            return False
    
    def calculate_monthly_bill(self, site_id: str, month: str) -> Dict[str, Any]:
        """
        Calculate monthly bill for a site using contract terms.
        
        Args:
            site_id: Customer site identifier
            month: Month in YYYY-MM format
            
        Returns:
            Billing calculation details
        """
        try:
            # Get rollup data - use instance if available, otherwise global
            if self._rollup_engine:
                rollup_engine = self._rollup_engine
            else:
                rollup_engine = get_rollup_engine()
            monthly_data = rollup_engine.get_monthly_rollup(month)
            
            if not monthly_data:
                return {
                    "success": False,
                    "error": f"No usage data found for month {month}",
                    "site_id": site_id,
                    "month": month
                }
            
            # Get site-specific metrics
            site_metrics = self._extract_site_metrics(monthly_data, site_id)
            
            if not site_metrics:
                return {
                    "success": False,
                    "error": f"No usage data found for site {site_id} in month {month}",
                    "site_id": site_id,
                    "month": month
                }
            
            # Get contract terms
            contract = self.contracts.get(site_id, self.contracts["default"])
            
            # Calculate charges
            mah_count = site_metrics["monthly_active_humans"]
            new_humans_count = site_metrics["new_humans"]
            
            # Apply base rates
            mah_charge = Decimal(str(mah_count)) * contract["mah_rate"]
            new_humans_charge = Decimal(str(new_humans_count)) * contract["new_human_rate"]
            
            # Apply volume discounts
            total_usage = mah_count + new_humans_count
            discount_percent = self._calculate_volume_discount(contract, total_usage)
            
            subtotal = mah_charge + new_humans_charge
            discount_amount = subtotal * (Decimal(str(discount_percent)) / Decimal("100"))
            total_amount = subtotal - discount_amount
            
            # Round to currency precision
            total_amount = total_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            
            return {
                "success": True,
                "site_id": site_id,
                "month": month,
                "currency": contract["currency"],
                "usage": {
                    "monthly_active_humans": mah_count,
                    "new_humans": new_humans_count,
                    "total_verifications": site_metrics["total_verifications"]
                },
                "rates": {
                    "mah_rate": str(contract["mah_rate"]),
                    "new_human_rate": str(contract["new_human_rate"])
                },
                "charges": {
                    "mah_charge": str(mah_charge),
                    "new_humans_charge": str(new_humans_charge),
                    "subtotal": str(subtotal),
                    "discount_percent": discount_percent,
                    "discount_amount": str(discount_amount),
                    "total_amount": str(total_amount)
                },
                "billing_date": datetime.now(timezone.utc).isoformat(),
                "due_date": (datetime.now(timezone.utc) + timedelta(days=contract["payment_terms"])).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error calculating bill for site {site_id}, month {month}: {e}")
            return {
                "success": False,
                "error": str(e),
                "site_id": site_id,
                "month": month
            }
    
    def _extract_site_metrics(self, monthly_data: Dict[str, Any], site_id: str) -> Optional[Dict[str, Any]]:
        """Extract metrics for a specific site from monthly rollup data."""
        try:
            # Aggregate site metrics across all days
            site_total_verifications = 0
            site_unique_humans = set()
            site_new_humans = set()
            
            for date, daily_metrics in monthly_data["daily_rollups"].items():
                if site_id in daily_metrics["site_metrics"]:
                    site_data = daily_metrics["site_metrics"][site_id]
                    site_total_verifications += site_data["total_verifications"]
                    site_unique_humans.update(site_data["unique_human_hashes"])
                    site_new_humans.update(site_data["new_human_hashes"])
            
            if site_total_verifications == 0:
                return None
            
            return {
                "total_verifications": site_total_verifications,
                "monthly_active_humans": len(site_unique_humans),
                "new_humans": len(site_new_humans)
            }
            
        except Exception as e:
            logger.error(f"Error extracting site metrics for {site_id}: {e}")
            return None
    
    def _calculate_volume_discount(self, contract: Dict[str, Any], total_usage: int) -> float:
        """Calculate volume discount percentage based on usage."""
        discounts = contract.get("volume_discounts", [])
        
        applicable_discount = 0.0
        for discount in discounts:
            min_usage = discount.get("min_usage", 0)
            discount_percent = discount.get("discount_percent", 0.0)
            
            if total_usage >= min_usage:
                applicable_discount = max(applicable_discount, discount_percent)
        
        return applicable_discount
    
    def generate_invoice_pdf(self, billing_data: Dict[str, Any]) -> bytes:
        """Generate PDF invoice from billing data."""
        try:
            # Create PDF buffer
            buffer = io.BytesIO()
            
            # Create document
            doc = SimpleDocTemplate(buffer, pagesize=letter)
            story = []
            
            # Get styles
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                spaceAfter=30,
                alignment=1  # Center
            )
            
            # Invoice header
            story.append(Paragraph("LEMMA VERIFICATION INVOICE", title_style))
            story.append(Spacer(1, 20))
            
            # Invoice details table
            invoice_data = [
                ['Invoice Date:', billing_data['billing_date'][:10]],
                ['Due Date:', billing_data['due_date'][:10]],
                ['Site ID:', billing_data['site_id']],
                ['Billing Period:', billing_data['month']],
                ['Currency:', billing_data['currency']]
            ]
            
            invoice_table = Table(invoice_data, colWidths=[2*inch, 3*inch])
            invoice_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 12),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ]))
            story.append(invoice_table)
            story.append(Spacer(1, 30))
            
            # Usage summary
            story.append(Paragraph("Usage Summary", styles['Heading2']))
            usage_data = [
                ['Metric', 'Count', 'Rate', 'Amount'],
                [
                    'Monthly Active Humans',
                    str(billing_data['usage']['monthly_active_humans']),
                    f"${billing_data['rates']['mah_rate']}",
                    f"${billing_data['charges']['mah_charge']}"
                ],
                [
                    'New Humans',
                    str(billing_data['usage']['new_humans']),
                    f"${billing_data['rates']['new_human_rate']}",
                    f"${billing_data['charges']['new_humans_charge']}"
                ]
            ]
            
            usage_table = Table(usage_data, colWidths=[2.5*inch, 1*inch, 1*inch, 1.5*inch])
            usage_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 14),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(usage_table)
            story.append(Spacer(1, 20))
            
            # Billing summary
            summary_data = [
                ['Subtotal:', f"${billing_data['charges']['subtotal']}"],
                ['Discount ({:.1f}%):'.format(billing_data['charges']['discount_percent']), 
                 f"-${billing_data['charges']['discount_amount']}"],
                ['Total Amount:', f"${billing_data['charges']['total_amount']}"]
            ]
            
            summary_table = Table(summary_data, colWidths=[4*inch, 2*inch])
            summary_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, -1), (-1, -1), 14),
                ('LINEBELOW', (0, -1), (-1, -1), 2, colors.black),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(summary_table)
            
            # Build PDF
            doc.build(story)
            
            # Get PDF bytes
            pdf_bytes = buffer.getvalue()
            buffer.close()
            
            return pdf_bytes
            
        except Exception as e:
            logger.error(f"Error generating PDF invoice: {e}")
            raise
    
    def generate_invoice_csv(self, billing_data: Dict[str, Any]) -> str:
        """Generate CSV invoice from billing data."""
        try:
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Header
            writer.writerow(['Lemma Verification Invoice'])
            writer.writerow([])
            
            # Invoice details
            writer.writerow(['Invoice Date', billing_data['billing_date'][:10]])
            writer.writerow(['Due Date', billing_data['due_date'][:10]])
            writer.writerow(['Site ID', billing_data['site_id']])
            writer.writerow(['Billing Period', billing_data['month']])
            writer.writerow(['Currency', billing_data['currency']])
            writer.writerow([])
            
            # Usage details
            writer.writerow(['Usage Summary'])
            writer.writerow(['Metric', 'Count', 'Rate', 'Amount'])
            writer.writerow([
                'Monthly Active Humans',
                billing_data['usage']['monthly_active_humans'],
                billing_data['rates']['mah_rate'],
                billing_data['charges']['mah_charge']
            ])
            writer.writerow([
                'New Humans',
                billing_data['usage']['new_humans'],
                billing_data['rates']['new_human_rate'],
                billing_data['charges']['new_humans_charge']
            ])
            writer.writerow([])
            
            # Billing summary
            writer.writerow(['Billing Summary'])
            writer.writerow(['Subtotal', billing_data['charges']['subtotal']])
            writer.writerow(['Discount (%)', billing_data['charges']['discount_percent']])
            writer.writerow(['Discount Amount', billing_data['charges']['discount_amount']])
            writer.writerow(['Total Amount', billing_data['charges']['total_amount']])
            
            csv_content = output.getvalue()
            output.close()
            
            return csv_content
            
        except Exception as e:
            logger.error(f"Error generating CSV invoice: {e}")
            raise
    
    def save_invoice(self, billing_data: Dict[str, Any], formats: List[str] = None) -> Dict[str, str]:
        """Save invoice in multiple formats."""
        if formats is None:
            formats = ["pdf", "csv"]
        
        invoice_id = f"{billing_data['site_id']}_{billing_data['month']}"
        saved_files = {}
        
        try:
            for format_type in formats:
                if format_type == "pdf":
                    pdf_bytes = self.generate_invoice_pdf(billing_data)
                    pdf_file = os.path.join(self.billing_dir, f'invoice_{invoice_id}.pdf')
                    with open(pdf_file, 'wb') as f:
                        f.write(pdf_bytes)
                    saved_files["pdf"] = pdf_file
                    
                elif format_type == "csv":
                    csv_content = self.generate_invoice_csv(billing_data)
                    csv_file = os.path.join(self.billing_dir, f'invoice_{invoice_id}.csv')
                    with open(csv_file, 'w') as f:
                        f.write(csv_content)
                    saved_files["csv"] = csv_file
                
                elif format_type == "json":
                    json_file = os.path.join(self.billing_dir, f'invoice_{invoice_id}.json')
                    with open(json_file, 'w') as f:
                        json.dump(billing_data, f, indent=2)
                    saved_files["json"] = json_file
            
            logger.info(f"Saved invoice {invoice_id} in formats: {list(saved_files.keys())}")
            return saved_files
            
        except Exception as e:
            logger.error(f"Error saving invoice {invoice_id}: {e}")
            raise
    
    def post_to_stripe(self, billing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Post invoice to Stripe billing."""
        try:
            import stripe
            
            # Get Stripe API key
            stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
            if not stripe.api_key:
                return {"success": False, "error": "Stripe API key not configured"}
            
            # Create Stripe invoice
            invoice = stripe.Invoice.create(
                customer=billing_data['site_id'],  # Assuming site_id maps to Stripe customer
                currency=billing_data['currency'].lower(),
                description=f"Lemma Verification - {billing_data['month']}",
                due_date=int(datetime.fromisoformat(billing_data['due_date'].replace('Z', '+00:00')).timestamp()),
                metadata={
                    'lemma_site_id': billing_data['site_id'],
                    'billing_month': billing_data['month'],
                    'mah_count': billing_data['usage']['monthly_active_humans'],
                    'new_humans': billing_data['usage']['new_humans']
                }
            )
            
            # Add invoice items
            stripe.InvoiceItem.create(
                customer=billing_data['site_id'],
                invoice=invoice.id,
                amount=int(float(billing_data['charges']['mah_charge']) * 100),  # Amount in cents
                currency=billing_data['currency'].lower(),
                description=f"Monthly Active Humans ({billing_data['usage']['monthly_active_humans']} × ${billing_data['rates']['mah_rate']})"
            )
            
            stripe.InvoiceItem.create(
                customer=billing_data['site_id'],
                invoice=invoice.id,
                amount=int(float(billing_data['charges']['new_humans_charge']) * 100),
                currency=billing_data['currency'].lower(),
                description=f"New Humans ({billing_data['usage']['new_humans']} × ${billing_data['rates']['new_human_rate']})"
            )
            
            # Apply discount if applicable
            if float(billing_data['charges']['discount_amount']) > 0:
                stripe.InvoiceItem.create(
                    customer=billing_data['site_id'],
                    invoice=invoice.id,
                    amount=-int(float(billing_data['charges']['discount_amount']) * 100),
                    currency=billing_data['currency'].lower(),
                    description=f"Volume Discount ({billing_data['charges']['discount_percent']}%)"
                )
            
            # Finalize invoice
            finalized_invoice = stripe.Invoice.finalize_invoice(invoice.id)
            
            return {
                "success": True,
                "stripe_invoice_id": finalized_invoice.id,
                "stripe_invoice_url": finalized_invoice.hosted_invoice_url,
                "amount": finalized_invoice.amount_due / 100,
                "currency": finalized_invoice.currency.upper()
            }
            
        except Exception as e:
            logger.error(f"Error posting to Stripe: {e}")
            return {"success": False, "error": str(e)}

# Global billing engine instance
_billing_engine = None

def get_billing_engine() -> BillingEngine:
    """Get or create global billing engine instance."""
    global _billing_engine
    if _billing_engine is None:
        _billing_engine = BillingEngine()
    return _billing_engine 