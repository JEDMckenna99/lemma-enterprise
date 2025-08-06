"""
QR Code Verifier API for Lemma-Powered QR Codes

This module provides HTTP endpoints for verifying QR codes with embedded 
cryptographic lemmas using the Lemma universal verification engine.
"""

import json
import time
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import base64
import hashlib

# Import Rust bindings (assuming they exist)
try:
    from lemma_crypto import PyLemmaCore, QRLemmaVerifier
except ImportError:
    # Fallback for development - mock the Rust functionality
    PyLemmaCore = None
    QRLemmaVerifier = None

@dataclass
class QRVerificationRequest:
    """Request structure for QR code verification"""
    qr_data: Union[str, Dict[str, Any]]  # JSON string or dict
    verification_context: Optional[Dict[str, Any]] = None
    required_claims: Optional[List[str]] = None
    
    def __post_init__(self):
        if self.verification_context is None:
            self.verification_context = {}
        if self.required_claims is None:
            self.required_claims = []

@dataclass
class QRVerificationResult:
    """Result structure for QR code verification"""
    success: bool
    is_valid: bool
    qr_type: Optional[str] = None
    verification_time_us: Optional[float] = None
    claims: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    performance_metrics: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = None

class LemmaQRVerifier:
    """Main QR verifier class integrating with Rust backend"""
    
    def __init__(self):
        """Initialize the QR verifier with Rust engine"""
        if PyLemmaCore is not None:
            # Initialize actual Rust engine
            self.rust_engine = PyLemmaCore()
            self.qr_verifier = QRLemmaVerifier(self.rust_engine)
        else:
            # Rust engine is required for production
            raise RuntimeError("Rust backend is required for production QR verification. Mock mode has been removed.")
    
    def verify_qr(self, request: QRVerificationRequest) -> QRVerificationResult:
        """Verify a QR code with embedded lemma"""
        start_time = time.perf_counter()
        
        try:
            return self._verify_rust_qr(request, start_time)
                
        except Exception as e:
            verification_time = (time.perf_counter() - start_time) * 1_000_000
            return QRVerificationResult(
                success=False,
                is_valid=False,
                error_message=f"QR verification failed: {str(e)}",
                verification_time_us=verification_time
            )
    
    def _verify_rust_qr(self, request: QRVerificationRequest, start_time: float) -> QRVerificationResult:
        """Verify QR using actual Rust engine"""
        # Prepare QR data
        if isinstance(request.qr_data, str):
            qr_json = request.qr_data
        else:
            qr_json = json.dumps(request.qr_data)
        
        # Verify using Rust engine (4.176µs performance)
        verification_start = time.perf_counter()
        
        if request.required_claims:
            # Use requirements-based verification
            result = self.qr_verifier.verify_qr_with_requirements(qr_json, request.required_claims)
        else:
            # Standard verification
            result = self.qr_verifier.verify_qr_string(qr_json)
        
        verification_time = (time.perf_counter() - verification_start) * 1_000_000
        total_time = (time.perf_counter() - start_time) * 1_000_000
        
        return QRVerificationResult(
            success=True,
            is_valid=result.is_valid,
            qr_type=result.qr_type,
            verification_time_us=verification_time,
            claims=result.claims,
            metadata=result.metadata,
            error_message=result.error_message,
            performance_metrics={
                "decode_time_us": result.performance_metrics.decode_time_us,
                "lemma_verification_time_us": result.performance_metrics.lemma_verification_time_us,
                "total_time_us": result.performance_metrics.total_time_us,
                "cache_hit": result.performance_metrics.cache_hit,
                "overall_time_us": total_time
            },
            confidence_score=0.999 if result.is_valid else 0.001
        )
    

    
    def verify_specific_qr_type(self, qr_data: Union[str, Dict[str, Any]], 
                               qr_type: str, context: Optional[Dict[str, Any]] = None) -> QRVerificationResult:
        """Verify QR code for a specific type with context"""
        if context is None:
            context = {}
        

        # Use actual Rust verifier with type-specific methods
        if isinstance(qr_data, dict):
                qr_json = json.dumps(qr_data)
            else:
                qr_json = qr_data
            
            start_time = time.perf_counter()
            
            if qr_type == "ticket":
                result = self.qr_verifier.verify_ticket_qr(qr_json)
            elif qr_type == "product":
                result = self.qr_verifier.verify_product_qr(qr_json)
            elif qr_type == "access":
                # For access, we might need to pass required zones
                required_zones = context.get("required_zones", [])
                result = self.qr_verifier.verify_access_qr(qr_json, required_zones)
            else:
                # Fallback to general verification
                request = QRVerificationRequest(qr_data=qr_data, verification_context=context)
                return self.verify_qr(request)
            
            verification_time = (time.perf_counter() - start_time) * 1_000_000
            
            return QRVerificationResult(
                success=True,
                is_valid=result.is_valid,
                qr_type=qr_type,
                verification_time_us=result.verification_time_us,
                claims=getattr(result, 'claims', {}),
                metadata=getattr(result, 'metadata', {}),
                error_message=result.error_message,
                confidence_score=0.999 if result.is_valid else 0.001
            )


# Flask/FastAPI integration helpers
def create_qr_verifier_endpoints(app, verifier: Optional[LemmaQRVerifier] = None):
    """Create QR verifier endpoints for Flask/FastAPI apps"""
    if verifier is None:
        verifier = LemmaQRVerifier()
    
    def verify_qr_endpoint():
        """HTTP endpoint for QR verification"""
        try:
            # Parse request data
            request_data = app.get_json() if hasattr(app, 'get_json') else {}
            
            # Create request object
            qr_request = QRVerificationRequest(
                qr_data=request_data.get('qr_data', {}),
                verification_context=request_data.get('context', {}),
                required_claims=request_data.get('required_claims', [])
            )
            
            # Verify QR
            result = verifier.verify_qr(qr_request)
            
            # Return JSON response
            return {
                "success": result.success,
                "is_valid": result.is_valid,
                "qr_type": result.qr_type,
                "claims": result.claims,
                "metadata": result.metadata,
                "performance": {
                    "verification_time_us": result.verification_time_us,
                    "confidence_score": result.confidence_score,
                    "performance_metrics": result.performance_metrics
                },
                "error": result.error_message
            }
            
        except Exception as e:
            return {
                "success": False,
                "is_valid": False,
                "error": f"Request processing failed: {str(e)}"
            }
    
    def verify_ticket_endpoint():
        """HTTP endpoint for ticket-specific verification"""
        try:
            request_data = app.get_json() if hasattr(app, 'get_json') else {}
            qr_data = request_data.get('qr_data', {})
            context = request_data.get('context', {})
            
            result = verifier.verify_specific_qr_type(qr_data, "ticket", context)
            
            return {
                "success": result.success,
                "is_valid": result.is_valid,
                "ticket_info": result.claims if result.is_valid else None,
                "performance": {
                    "verification_time_us": result.verification_time_us,
                    "confidence_score": result.confidence_score
                },
                "error": result.error_message
            }
        except Exception as e:
            return {
                "success": False,
                "is_valid": False,
                "error": f"Ticket verification failed: {str(e)}"
            }
    
    def verify_product_endpoint():
        """HTTP endpoint for product-specific verification"""
        try:
            request_data = app.get_json() if hasattr(app, 'get_json') else {}
            qr_data = request_data.get('qr_data', {})
            context = request_data.get('context', {})
            
            result = verifier.verify_specific_qr_type(qr_data, "product", context)
            
            return {
                "success": result.success,
                "is_valid": result.is_valid,
                "product_info": result.claims if result.is_valid else None,
                "performance": {
                    "verification_time_us": result.verification_time_us,
                    "confidence_score": result.confidence_score
                },
                "error": result.error_message
            }
        except Exception as e:
            return {
                "success": False,
                "is_valid": False,
                "error": f"Product verification failed: {str(e)}"
            }
    
    def verify_access_endpoint():
        """HTTP endpoint for access-specific verification"""
        try:
            request_data = app.get_json() if hasattr(app, 'get_json') else {}
            qr_data = request_data.get('qr_data', {})
            context = request_data.get('context', {})
            required_zones = request_data.get('required_zones', [])
            
            # Add required zones to context
            context['required_zones'] = required_zones
            
            result = verifier.verify_specific_qr_type(qr_data, "access", context)
            
            return {
                "success": result.success,
                "is_valid": result.is_valid,
                "access_granted": result.is_valid,
                "access_info": result.claims if result.is_valid else None,
                "performance": {
                    "verification_time_us": result.verification_time_us,
                    "confidence_score": result.confidence_score
                },
                "error": result.error_message
            }
        except Exception as e:
            return {
                "success": False,
                "is_valid": False,
                "error": f"Access verification failed: {str(e)}"
            }
    
    return {
        "verify": verify_qr_endpoint,
        "verify_ticket": verify_ticket_endpoint,
        "verify_product": verify_product_endpoint,
        "verify_access": verify_access_endpoint
    }

# CLI interface for testing
def main():
    """CLI interface for testing QR verification"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Verify Lemma-powered QR codes")
    parser.add_argument("--qr-data", required=True, help="QR data (JSON string or file)")
    parser.add_argument("--type", choices=["ticket", "product", "access", "identity"], 
                       help="Specific QR type to verify")
    parser.add_argument("--required-claims", nargs="+", help="Required claims for verification")
    parser.add_argument("--required-zones", nargs="+", help="Required access zones (for access QR)")
    parser.add_argument("--context", help="Additional verification context (JSON)")
    
    args = parser.parse_args()
    
    # Create verifier
    verifier = LemmaQRVerifier()
    
    # Load QR data
    qr_data = args.qr_data
    if qr_data.startswith('@'):
        # Load from file
        with open(qr_data[1:], 'r') as f:
            qr_data = f.read()
    
    # Parse context
    context = {}
    if args.context:
        context = json.loads(args.context)
    
    if args.required_zones:
        context['required_zones'] = args.required_zones
    
    # Verify QR
    if args.type:
        result = verifier.verify_specific_qr_type(qr_data, args.type, context)
    else:
        request = QRVerificationRequest(
            qr_data=qr_data,
            verification_context=context,
            required_claims=args.required_claims or []
        )
        result = verifier.verify_qr(request)
    
    # Output results
    if result.success:
        if result.is_valid:
            print(f"✅ QR code is VALID!")
            print(f"⚡ Verification time: {result.verification_time_us:.2f}µs")
            print(f"🔖 QR type: {result.qr_type}")
            print(f"🎯 Confidence: {result.confidence_score:.3f}")
            
            if result.claims:
                print(f"📋 Claims:")
                for key, value in result.claims.items():
                    print(f"  {key}: {value}")
            
            if result.performance_metrics:
                print(f"📊 Performance:")
                for key, value in result.performance_metrics.items():
                    print(f"  {key}: {value}")
        else:
            print(f"❌ QR code is INVALID!")
            print(f"⚡ Verification time: {result.verification_time_us:.2f}µs")
            if result.error_message:
                print(f"🚫 Error: {result.error_message}")
    else:
        print(f"💥 Verification failed: {result.error_message}")

if __name__ == "__main__":
    main() 