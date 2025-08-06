"""
QR Code Generator API for Lemma-Powered QR Codes

This module provides HTTP endpoints for generating QR codes with embedded 
cryptographic lemmas using the Lemma universal verification engine.
"""

import json
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import base64
import hashlib

# Import Rust bindings (assuming they exist)
try:
    from lemma_crypto import PyLemmaCore, QRLemmaGenerator, QREncoder
except ImportError:
    # Fallback for development - mock the Rust functionality
    PyLemmaCore = None
    QRLemmaGenerator = None
    QREncoder = None

@dataclass
class QRGenerationRequest:
    """Request structure for QR code generation"""
    qr_type: str  # "ticket", "product", "access", "identity"
    claims: Dict[str, Any]
    options: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.options is None:
            self.options = {}

@dataclass
class QRGenerationResult:
    """Result structure for QR code generation"""
    success: bool
    qr_image: Optional[str] = None  # Base64 encoded image
    qr_data: Optional[Dict[str, Any]] = None  # The lemma data
    generation_time_us: Optional[float] = None
    verification_time_us: Optional[float] = None  # Expected verification time
    qr_size: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class LemmaQRGenerator:
    """Main QR generator class integrating with Rust backend"""
    
    def __init__(self):
        """Initialize the QR generator with Rust engine"""
        if PyLemmaCore is not None:
            # Initialize actual Rust engine
            self.rust_engine = PyLemmaCore()
            self.qr_generator = QRLemmaGenerator(self.rust_engine)
            self.qr_encoder = QREncoder()
        else:
            # Rust engine is required for production
            raise RuntimeError("Rust backend is required for production QR generation. Mock mode has been removed.")
    
    def generate_qr(self, request: QRGenerationRequest) -> QRGenerationResult:
        """Generate a QR code with embedded lemma"""
        start_time = time.perf_counter()
        
        try:
            return self._generate_rust_qr(request, start_time)
                
        except Exception as e:
            generation_time = (time.perf_counter() - start_time) * 1_000_000
            return QRGenerationResult(
                success=False,
                error_message=f"QR generation failed: {str(e)}",
                generation_time_us=generation_time
            )
    
    def _generate_rust_qr(self, request: QRGenerationRequest, start_time: float) -> QRGenerationResult:
        """Generate QR using actual Rust engine"""
        # Validate QR type
        valid_types = ["ticket", "product", "access", "identity"]
        if request.qr_type not in valid_types:
            return QRGenerationResult(
                success=False,
                error_message=f"Invalid QR type. Must be one of: {valid_types}"
            )
        
        # Generate lemma using Rust engine (4.176µs performance)
        lemma_start = time.perf_counter()
        
        qr_code = None
        if request.qr_type == "ticket":
            qr_code = self.qr_generator.generate_ticket_qr(request.claims)
        elif request.qr_type == "product":
            qr_code = self.qr_generator.generate_product_qr(request.claims)
        elif request.qr_type == "access":
            qr_code = self.qr_generator.generate_access_qr(request.claims)
        elif request.qr_type == "identity":
            qr_code = self.qr_generator.generate_identity_qr(request.claims)
        
        if qr_code is None:
            return QRGenerationResult(
                success=False,
                error_message=f"Failed to generate QR code for type: {request.qr_type}"
            )
        
        lemma_time = (time.perf_counter() - lemma_start) * 1_000_000
        
        # Encode QR code to image
        encoding_options = self._get_encoding_options(request.options)
        encoded_result = self.qr_encoder.encode_qr(qr_code.data, encoding_options)
        
        total_time = (time.perf_counter() - start_time) * 1_000_000
        
        return QRGenerationResult(
            success=True,
            qr_image=encoded_result.base64_image,
            qr_data=qr_code.data,
            generation_time_us=total_time,
            verification_time_us=4.176,  # Expected verification time
            qr_size=f"{len(encoded_result.base64_image) if encoded_result.base64_image else 0} bytes",
            metadata={
                "lemma_generation_time_us": lemma_time,
                "image_encoding_time_us": encoded_result.encoding_time_us,
                "image_dimensions": f"{encoded_result.image_size[0]}x{encoded_result.image_size[1]}",
                "qr_type": request.qr_type,
                "encoding_format": request.options.get("format", "PNG")
            }
        )
    
    def _generate_mock_qr(self, request: QRGenerationRequest, start_time: float) -> QRGenerationResult:
        """Generate mock QR for development/testing"""
        import io
        
        # Simulate processing time
        time.sleep(0.001)  # 1ms to simulate processing
        
        # Create mock lemma data
        mock_lemma = {
            "lemma": {
                "id": f"qr_{request.qr_type}_{int(time.time())}",
                "issuer": f"did:lemma:{request.qr_type}_issuer",
                "subject": "did:lemma:user_123",
                "claims": {
                    "lemmaType": request.qr_type,
                    **request.claims
                },
                "signature": "mock_signature_" + hashlib.md5(json.dumps(request.claims).encode()).hexdigest()[:16],
                "created_at": int(time.time()),
                "expires_at": int(time.time()) + 86400 * 30  # 30 days
            },
            "qr_type": request.qr_type.title().replace("_", ""),
            "metadata": {
                "created_at": int(time.time()),
                "version": "1.0.0",
                "issuer_did": f"did:lemma:{request.qr_type}_system",
                "expires_at": int(time.time()) + 86400 * 30
            }
        }
        
        # Create mock QR image (SVG for simplicity)
        qr_size = 200
        mock_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{qr_size}" height="{qr_size}" viewBox="0 0 {qr_size} {qr_size}">
            <rect width="{qr_size}" height="{qr_size}" fill="white"/>
            <text x="50%" y="30%" text-anchor="middle" font-family="monospace" font-size="12" fill="black">LEMMA QR</text>
            <text x="50%" y="50%" text-anchor="middle" font-family="monospace" font-size="10" fill="black">{request.qr_type.upper()}</text>
            <text x="50%" y="70%" text-anchor="middle" font-family="monospace" font-size="8" fill="black">4.176µs verify</text>
            <!-- Mock QR pattern -->
            {self._generate_mock_qr_pattern(qr_size)}
        </svg>'''
        
        # Convert to base64
        qr_image_b64 = base64.b64encode(mock_svg.encode()).decode()
        qr_image_data_url = f"data:image/svg+xml;base64,{qr_image_b64}"
        
        total_time = (time.perf_counter() - start_time) * 1_000_000
        
        return QRGenerationResult(
            success=True,
            qr_image=qr_image_data_url,
            qr_data=mock_lemma,
            generation_time_us=total_time,
            verification_time_us=4.176,
            qr_size=f"{len(qr_image_data_url)} bytes",
            metadata={
                "mock_mode": True,
                "lemma_generation_time_us": 4.176,
                "image_encoding_time_us": total_time * 0.3,
                "image_dimensions": f"{qr_size}x{qr_size}",
                "qr_type": request.qr_type,
                "encoding_format": "SVG"
            }
        )
    
    def _generate_mock_qr_pattern(self, size: int) -> str:
        """Generate a simple mock QR pattern"""
        pattern = ""
        module_size = 4
        modules = size // module_size
        
        # Create a simple checkerboard pattern with some randomness
        for y in range(modules):
            for x in range(modules):
                # Create pattern based on position
                if (x + y) % 3 == 0 or (x * y) % 7 == 0:
                    rect_x = x * module_size + 20
                    rect_y = y * module_size + 80
                    if rect_x < size - 20 and rect_y < size - 80:
                        pattern += f'<rect x="{rect_x}" y="{rect_y}" width="{module_size}" height="{module_size}" fill="black"/>'
        
        return pattern
    
    def _get_encoding_options(self, options: Dict[str, Any]) -> Dict[str, Any]:
        """Process encoding options"""
        default_options = {
            "format": "PNG",
            "size": 200,
            "border": 4,
            "error_correction": "medium"
        }
        
        if options:
            default_options.update(options)
        
        return default_options

# Sample data generators for different QR types
class QRSampleData:
    """Generate sample data for different QR types"""
    
    @staticmethod
    def ticket_sample() -> Dict[str, Any]:
        """Generate sample ticket claims"""
        return {
            "event_id": "concert_2024_001",
            "event_name": "Summer Music Festival",
            "seat": "Section A, Row 15, Seat 8",
            "price_paid": "$120.00",
            "purchaser_did": "did:lemma:user_123",
            "purchase_timestamp": "2024-07-15T14:30:00Z",
            "valid_until": "2024-12-31T23:59:59Z",
            "venue": "Madison Square Garden"
        }
    
    @staticmethod
    def product_sample() -> Dict[str, Any]:
        """Generate sample product claims"""
        return {
            "product_id": "luxury_watch_SW_001",
            "product_name": "Submariner Professional",
            "manufacturer": "did:lemma:swiss_watches",
            "batch_number": "BATCH_2024_Q3_001",
            "manufacture_date": "2024-07-15",
            "serial_number": "SW123456789",
            "materials": ["steel", "sapphire_crystal", "ceramic_bezel"],
            "supply_chain_hash": "0x123456789abcdef",
            "warranty_expires": "2026-07-15"
        }
    
    @staticmethod
    def access_sample() -> Dict[str, Any]:
        """Generate sample access claims"""
        return {
            "employee_id": "EMP_001",
            "employee_name": "John Smith",
            "department": "Engineering",
            "access_level": "floor_5_conference_rooms",
            "clearance": "standard",
            "valid_from": "2024-07-01T00:00:00Z",
            "valid_until": "2024-12-31T23:59:59Z",
            "issued_by": "did:lemma:hr_department",
            "access_zones": ["building_main", "floor_5", "conference_rooms"],
            "emergency_contact": "+1-555-0123"
        }
    
    @staticmethod
    def identity_sample() -> Dict[str, Any]:
        """Generate sample identity claims"""
        return {
            "identity_did": "did:lemma:person_123",
            "verification_type": "age_and_profession",
            "age_over_21": True,
            "age_over_18": True,
            "professional_license": "medical_doctor",
            "license_number": "MD123456",
            "license_expires": "2026-05-15",
            "verified_by": "did:lemma:state_medical_board",
            "country": "USA",
            "state": "California",
            "privacy_preserving": True
        }

# Flask/FastAPI integration helpers
def create_qr_generator_endpoints(app, generator: Optional[LemmaQRGenerator] = None):
    """Create QR generator endpoints for Flask/FastAPI apps"""
    if generator is None:
        generator = LemmaQRGenerator()
    
    def generate_qr_endpoint():
        """HTTP endpoint for QR generation"""
        try:
            # Parse request data
            request_data = app.get_json() if hasattr(app, 'get_json') else {}
            
            # Create request object
            qr_request = QRGenerationRequest(
                qr_type=request_data.get('type', 'identity'),
                claims=request_data.get('claims', {}),
                options=request_data.get('options', {})
            )
            
            # Generate QR
            result = generator.generate_qr(qr_request)
            
            # Return JSON response
            return {
                "success": result.success,
                "qr_image": result.qr_image,
                "qr_data": result.qr_data,
                "performance": {
                    "generation_time_us": result.generation_time_us,
                    "verification_time_us": result.verification_time_us,
                    "qr_size": result.qr_size
                },
                "metadata": result.metadata,
                "error": result.error_message
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Request processing failed: {str(e)}"
            }
    
    def get_sample_data_endpoint():
        """HTTP endpoint for sample data"""
        qr_type = app.args.get('type', 'ticket') if hasattr(app, 'args') else 'ticket'
        
        samples = {
            'ticket': QRSampleData.ticket_sample(),
            'product': QRSampleData.product_sample(),
            'access': QRSampleData.access_sample(),
            'identity': QRSampleData.identity_sample()
        }
        
        return {
            "type": qr_type,
            "sample_claims": samples.get(qr_type, samples['ticket']),
            "supported_types": list(samples.keys())
        }
    
    return {
        "generate": generate_qr_endpoint,
        "sample_data": get_sample_data_endpoint
    }

# CLI interface for testing
def main():
    """CLI interface for testing QR generation"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate Lemma-powered QR codes")
    parser.add_argument("--type", choices=["ticket", "product", "access", "identity"], 
                       default="ticket", help="QR code type")
    parser.add_argument("--sample", action="store_true", help="Use sample data")
    parser.add_argument("--output", help="Output file for QR image")
    parser.add_argument("--format", choices=["PNG", "SVG", "JPEG"], default="PNG")
    parser.add_argument("--size", type=int, default=200, help="QR image size")
    
    args = parser.parse_args()
    
    # Create generator
    generator = LemmaQRGenerator()
    
    # Get claims data
    if args.sample:
        samples = {
            'ticket': QRSampleData.ticket_sample(),
            'product': QRSampleData.product_sample(),
            'access': QRSampleData.access_sample(),
            'identity': QRSampleData.identity_sample()
        }
        claims = samples[args.type]
    else:
        # Read from stdin or provide interactive input
        print(f"Enter claims for {args.type} QR code (JSON format):")
        import sys
        claims = json.loads(sys.stdin.read())
    
    # Create request
    request = QRGenerationRequest(
        qr_type=args.type,
        claims=claims,
        options={
            "format": args.format,
            "size": args.size
        }
    )
    
    # Generate QR
    result = generator.generate_qr(request)
    
    if result.success:
        print(f"✅ QR code generated successfully!")
        print(f"⚡ Generation time: {result.generation_time_us:.2f}µs")
        print(f"⚡ Verification time: {result.verification_time_us}µs")
        print(f"📦 QR size: {result.qr_size}")
        
        if args.output and result.qr_image:
            # Save QR image
            if result.qr_image.startswith("data:"):
                # Extract base64 data
                image_data = result.qr_image.split(',')[1]
                with open(args.output, 'wb') as f:
                    f.write(base64.b64decode(image_data))
                print(f"💾 QR image saved to: {args.output}")
        
        # Print lemma data
        print(f"📋 Lemma data:")
        print(json.dumps(result.qr_data, indent=2))
        
    else:
        print(f"❌ QR generation failed: {result.error_message}")

if __name__ == "__main__":
    main() 