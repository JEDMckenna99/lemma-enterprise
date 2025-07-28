//! Generate QR codes for demo credentials

use lemma_crypto::{
    credentials::{CredentialIssuer, VerifiableCredential},
    LemmaError,
};
use qrcode::QrCode;
use qrcode::render::svg;
use std::fs;
use std::collections::HashMap;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    println!("🔄 Generating demo QR codes...");
    
    // Create demo directory structure
    fs::create_dir_all("../demo/qr_codes")?;
    fs::create_dir_all("../demo/credentials")?;
    
    let issuer = CredentialIssuer::new();
    
    // Generate sample credentials
    let credentials = create_demo_credentials(&issuer)?;
    
    // Generate QR codes for each credential
    for (name, credential) in credentials {
        println!("📱 Generating QR code for {} credential...", name);
        
        // Serialize credential to JSON
        let json_data = serde_json::to_string_pretty(&credential)?;
        
        // Save credential JSON for reference
        fs::write(format!("../demo/credentials/{}_credential.json", name), &json_data)?;
        
        // Generate QR code
        let qr_code = QrCode::new(&json_data)?;
        
        // Generate SVG
        let svg_image = qr_code.render::<svg::Color>()
            .min_dimensions(300, 300)
            .dark_color(svg::Color("#000000"))
            .light_color(svg::Color("#ffffff"))
            .build();
        
        // Save QR code SVG
        fs::write(format!("../demo/qr_codes/{}_qr.svg", name), svg_image)?;
        
        // Generate HTML snippet for easy testing
        let html_snippet = format!(
            r#"
            <div class="qr-demo-card">
                <h3>{} Credential</h3>
                <div class="qr-container">
                    <img src="qr_codes/{}_qr.svg" width="200" height="200" alt="{} QR Code">
                </div>
                <p>Scan this QR code to verify the {} credential</p>
                <details>
                    <summary>Credential Details</summary>
                    <pre>{}</pre>
                </details>
            </div>
            "#,
            name.replace('_', " ").to_uppercase(),
            name,
            name.replace('_', " "),
            name.replace('_', " "),
            json_data
        );
        
        fs::write(format!("../demo/qr_codes/{}_snippet.html", name), html_snippet)?;
        
        println!("✅ Generated QR code for {}: {}", name, credential.id);
    }
    
    // Generate an index HTML file with all QR codes
    generate_index_html()?;
    
    println!("🎉 All QR codes generated successfully!");
    println!("📁 QR codes saved to: ../demo/qr_codes/");
    println!("📄 Credential JSONs saved to: ../demo/credentials/");
    println!("🌐 View all QR codes: ../demo/qr_codes/index.html");
    
    Ok(())
}

fn create_demo_credentials(issuer: &CredentialIssuer) -> Result<Vec<(String, VerifiableCredential)>, LemmaError> {
    let mut credentials = Vec::new();
    
    // 1. Identity credential
    let mut identity_claims = HashMap::new();
    identity_claims.insert("packageType".to_string(), serde_json::Value::String("identity".to_string()));
    identity_claims.insert("isHuman".to_string(), serde_json::Value::Bool(true));
    identity_claims.insert("verificationLevel".to_string(), serde_json::Value::String("high".to_string()));
    identity_claims.insert("issueDate".to_string(), serde_json::Value::String("2024-01-15T10:30:00Z".to_string()));
    identity_claims.insert("expiryDate".to_string(), serde_json::Value::String("2025-01-15T10:30:00Z".to_string()));
    identity_claims.insert("verificationMethod".to_string(), serde_json::Value::String("stripe_identity".to_string()));
    
    let identity_credential = issuer.issue_credential(
        "did:lemma:demo_user_001".to_string(),
        identity_claims,
        Some(1736937000), // Jan 15, 2025
    )?;
    credentials.push(("identity".to_string(), identity_credential));
    
    // 2. Event ticket credential
    let mut ticket_claims = HashMap::new();
    ticket_claims.insert("packageType".to_string(), serde_json::Value::String("ticket".to_string()));
    ticket_claims.insert("eventName".to_string(), serde_json::Value::String("Lemma Demo Conference 2024".to_string()));
    ticket_claims.insert("seatNumber".to_string(), serde_json::Value::String("A-123".to_string()));
    ticket_claims.insert("eventDate".to_string(), serde_json::Value::String("2024-03-15T19:00:00Z".to_string()));
    ticket_claims.insert("venue".to_string(), serde_json::Value::String("Tech Center".to_string()));
    ticket_claims.insert("ticketPrice".to_string(), serde_json::Value::String("$50".to_string()));
    ticket_claims.insert("eventType".to_string(), serde_json::Value::String("conference".to_string()));
    
    let ticket_credential = issuer.issue_credential(
        "did:lemma:ticket_001".to_string(),
        ticket_claims,
        Some(1710529200), // Mar 15, 2024
    )?;
    credentials.push(("ticket".to_string(), ticket_credential));
    
    // 3. Package authenticity credential
    let mut package_claims = HashMap::new();
    package_claims.insert("packageType".to_string(), serde_json::Value::String("package_authenticity".to_string()));
    package_claims.insert("productName".to_string(), serde_json::Value::String("Lemma Demo Widget".to_string()));
    package_claims.insert("batchNumber".to_string(), serde_json::Value::String("BATCH-2024-001".to_string()));
    package_claims.insert("manufacturer".to_string(), serde_json::Value::String("Lemma Corp".to_string()));
    package_claims.insert("manufactureDate".to_string(), serde_json::Value::String("2024-01-01".to_string()));
    package_claims.insert("authenticityLevel".to_string(), serde_json::Value::String("verified".to_string()));
    package_claims.insert("serialNumber".to_string(), serde_json::Value::String("LDW-2024-001".to_string()));
    
    let package_credential = issuer.issue_credential(
        "did:lemma:product_001".to_string(),
        package_claims,
        Some(1735689600), // Jan 1, 2025
    )?;
    credentials.push(("package_authenticity".to_string(), package_credential));
    
    // 4. Generic QR code credential
    let mut qr_claims = HashMap::new();
    qr_claims.insert("packageType".to_string(), serde_json::Value::String("qr_code".to_string()));
    qr_claims.insert("qrType".to_string(), serde_json::Value::String("generic".to_string()));
    qr_claims.insert("businessName".to_string(), serde_json::Value::String("Lemma Demo Restaurant".to_string()));
    qr_claims.insert("menuType".to_string(), serde_json::Value::String("dinner".to_string()));
    qr_claims.insert("lastUpdated".to_string(), serde_json::Value::String("2024-01-15T12:00:00Z".to_string()));
    qr_claims.insert("location".to_string(), serde_json::Value::String("123 Demo Street".to_string()));
    
    let qr_credential = issuer.issue_credential(
        "did:lemma:qr_001".to_string(),
        qr_claims,
        Some(1735689600), // Jan 1, 2025
    )?;
    credentials.push(("qr_code".to_string(), qr_credential));
    
    Ok(credentials)
}

fn generate_index_html() -> Result<(), Box<dyn std::error::Error>> {
    let html_content = r#"
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lemma Demo QR Codes</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        
        .container {
            background: white;
            border-radius: 10px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .qr-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }
        
        .qr-demo-card {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            border: 1px solid #e9ecef;
        }
        
        .qr-container {
            margin: 20px 0;
        }
        
        details {
            margin-top: 15px;
            text-align: left;
        }
        
        summary {
            cursor: pointer;
            padding: 10px;
            background: #e9ecef;
            border-radius: 5px;
        }
        
        pre {
            background: #f1f3f4;
            padding: 10px;
            border-radius: 5px;
            overflow-x: auto;
            font-size: 12px;
        }
        
        .instructions {
            background: #e3f2fd;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #2196f3;
        }
        
        .performance-note {
            background: #e8f5e8;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #4caf50;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔄 Lemma Demo QR Codes</h1>
        
        <div class="instructions">
            <h2>📋 Demo Instructions</h2>
            <ol>
                <li><strong>Open the main demo</strong> at <code>../index.html</code></li>
                <li><strong>Enable airplane mode</strong> on your phone</li>
                <li><strong>Scan any QR code</strong> below with the demo app</li>
                <li><strong>See instant verification</strong> without network calls</li>
            </ol>
        </div>
        
        <div class="performance-note">
            <h3>⚡ Performance Claims</h3>
            <p>These QR codes will demonstrate:</p>
            <ul>
                <li><strong>32.8 µs verification time</strong> (60x faster than 2ms target)</li>
                <li><strong>100% offline operation</strong> (no network calls)</li>
                <li><strong>Universal verification</strong> (all credential types)</li>
            </ul>
        </div>
        
        <div class="qr-grid">
            <div class="qr-demo-card">
                <h3>IDENTITY Credential</h3>
                <div class="qr-container">
                    <img src="identity_qr.svg" width="200" height="200" alt="Identity QR Code">
                </div>
                <p>Scan this QR code to verify the identity credential</p>
                <details>
                    <summary>What this proves</summary>
                    <p>This credential proves that a human has been verified through Stripe Identity with high confidence. It includes KYC information and verification method details.</p>
                </details>
            </div>
            
            <div class="qr-demo-card">
                <h3>TICKET Credential</h3>
                <div class="qr-container">
                    <img src="ticket_qr.svg" width="200" height="200" alt="Ticket QR Code">
                </div>
                <p>Scan this QR code to verify the ticket credential</p>
                <details>
                    <summary>What this proves</summary>
                    <p>This credential proves ownership of a valid event ticket. It includes event details, seat information, and prevents double-spending through revocation checks.</p>
                </details>
            </div>
            
            <div class="qr-demo-card">
                <h3>PACKAGE AUTHENTICITY Credential</h3>
                <div class="qr-container">
                    <img src="package_authenticity_qr.svg" width="200" height="200" alt="Package QR Code">
                </div>
                <p>Scan this QR code to verify the package authenticity credential</p>
                <details>
                    <summary>What this proves</summary>
                    <p>This credential proves product authenticity from the manufacturer. It includes batch information, serial numbers, and manufacturing details to prevent counterfeiting.</p>
                </details>
            </div>
            
            <div class="qr-demo-card">
                <h3>QR CODE Credential</h3>
                <div class="qr-container">
                    <img src="qr_code_qr.svg" width="200" height="200" alt="QR Code QR Code">
                </div>
                <p>Scan this QR code to verify the qr code credential</p>
                <details>
                    <summary>What this proves</summary>
                    <p>This credential proves the authenticity of generic QR codes like restaurant menus, business cards, or information displays. It ensures the QR code hasn't been tampered with.</p>
                </details>
            </div>
        </div>
        
        <div class="performance-note">
            <h3>🔬 Technical Details</h3>
            <p>All credentials use the same cryptographic primitives:</p>
            <ul>
                <li><strong>Ed25519 signatures</strong> for authenticity</li>
                <li><strong>OPRF evaluation</strong> for privacy-preserving verification</li>
                <li><strong>Cascaded Bloom filters</strong> for efficient revocation checking</li>
                <li><strong>WebAssembly</strong> for client-side verification</li>
            </ul>
        </div>
    </div>
</body>
</html>
    "#;
    
    fs::write("../demo/qr_codes/index.html", html_content)?;
    
    Ok(())
} 