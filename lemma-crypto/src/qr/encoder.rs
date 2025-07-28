use super::{QRCode, QRData};
use base64::{Engine as _, engine::general_purpose};

/// QR code encoding options
#[derive(Debug, Clone)]
pub struct QREncodingOptions {
    pub error_correction_level: QRErrorCorrectionLevel,
    pub border_size: u32,
    pub module_size: u32,
    pub include_base64_image: bool,
    pub image_format: QRImageFormat,
}

#[derive(Debug, Clone)]
pub enum QRErrorCorrectionLevel {
    Low,    // ~7% correction
    Medium, // ~15% correction
    Quartile, // ~25% correction
    High,   // ~30% correction
}

#[derive(Debug, Clone)]
pub enum QRImageFormat {
    PNG,
    SVG,
    JPEG,
}

impl Default for QREncodingOptions {
    fn default() -> Self {
        Self {
            error_correction_level: QRErrorCorrectionLevel::Medium,
            border_size: 4,
            module_size: 8,
            include_base64_image: true,
            image_format: QRImageFormat::PNG,
        }
    }
}

/// QR Encoder that handles image generation
pub struct QREncoder {
    options: QREncodingOptions,
}

/// Encoded QR result with image data
#[derive(Debug, Clone)]
pub struct EncodedQRResult {
    pub qr_code: QRCode,
    pub base64_image: Option<String>,
    pub svg_data: Option<String>,
    pub image_size: (u32, u32),
    pub encoding_time_us: f64,
}

impl QREncoder {
    /// Create a new QR encoder with default options
    pub fn new() -> Self {
        Self {
            options: QREncodingOptions::default(),
        }
    }

    /// Create a new QR encoder with custom options
    pub fn with_options(options: QREncodingOptions) -> Self {
        Self { options }
    }

    /// Encode QR data into an image
    pub fn encode_qr(&self, qr_data: QRData) -> crate::Result<EncodedQRResult> {
        let start_time = std::time::Instant::now();
        
        // Create QR code object
        let mut qr_code = QRCode::from_data(qr_data)?;
        
        // Generate image based on format
        let (base64_image, svg_data, image_size) = match self.options.image_format {
            QRImageFormat::PNG => {
                let (image_data, size) = self.generate_png_image(&qr_code.encoded_data)?;
                qr_code = qr_code.with_image(image_data.clone());
                
                let base64 = if self.options.include_base64_image {
                    Some(format!("data:image/png;base64,{}", 
                        general_purpose::STANDARD.encode(&image_data)))
                } else {
                    None
                };
                
                (base64, None, size)
            },
            QRImageFormat::SVG => {
                let (svg_content, size) = self.generate_svg_image(&qr_code.encoded_data)?;
                
                let base64 = if self.options.include_base64_image {
                    Some(format!("data:image/svg+xml;base64,{}", 
                        general_purpose::STANDARD.encode(svg_content.as_bytes())))
                } else {
                    None
                };
                
                (base64, Some(svg_content), size)
            },
            QRImageFormat::JPEG => {
                let (image_data, size) = self.generate_jpeg_image(&qr_code.encoded_data)?;
                qr_code = qr_code.with_image(image_data.clone());
                
                let base64 = if self.options.include_base64_image {
                    Some(format!("data:image/jpeg;base64,{}", 
                        general_purpose::STANDARD.encode(&image_data)))
                } else {
                    None
                };
                
                (base64, None, size)
            },
        };

        let encoding_time = start_time.elapsed().as_micros() as f64;

        Ok(EncodedQRResult {
            qr_code,
            base64_image,
            svg_data,
            image_size,
            encoding_time_us: encoding_time,
        })
    }

    /// Generate PNG image (simplified mock implementation)
    fn generate_png_image(&self, qr_data: &str) -> crate::Result<(Vec<u8>, (u32, u32))> {
        // For now, this is a simplified implementation
        // In a real implementation, you would use a QR code library like `qrcode` crate
        
        // Calculate matrix size based on data length (simplified)
        let data_len = qr_data.len();
        let matrix_size = ((data_len as f64).sqrt().ceil() as u32).max(21); // Minimum 21x21
        
        // Calculate image size with borders
        let module_count = matrix_size;
        let image_width = module_count * self.options.module_size + 2 * self.options.border_size;
        let image_height = image_width;
        
        // Create a simple mock PNG data (in reality, this would generate actual QR matrix)
        let mut image_data = Vec::new();
        
        // PNG header (simplified)
        image_data.extend_from_slice(&[137, 80, 78, 71, 13, 10, 26, 10]); // PNG signature
        
        // For demo purposes, create a pattern based on the QR data hash
        let data_hash = self.simple_hash(qr_data);
        let pattern_size = (image_width * image_height * 4) as usize; // RGBA
        
        for i in 0..pattern_size {
            let value = ((data_hash.wrapping_mul(i as u64 + 1)) % 256) as u8;
            // Create a checkerboard pattern mixed with data
            let pattern_value = if (i / 4) % 2 == 0 { value } else { 255 - value };
            image_data.push(pattern_value);
        }
        
        Ok((image_data, (image_width, image_height)))
    }

    /// Generate JPEG image (simplified mock implementation)
    fn generate_jpeg_image(&self, qr_data: &str) -> crate::Result<(Vec<u8>, (u32, u32))> {
        // Similar to PNG but with JPEG format
        let data_len = qr_data.len();
        let matrix_size = ((data_len as f64).sqrt().ceil() as u32).max(21);
        
        let module_count = matrix_size;
        let image_width = module_count * self.options.module_size + 2 * self.options.border_size;
        let image_height = image_width;
        
        let mut image_data = Vec::new();
        
        // JPEG header (simplified)
        image_data.extend_from_slice(&[255, 216, 255, 224]); // JPEG signature
        
        let data_hash = self.simple_hash(qr_data);
        let pattern_size = (image_width * image_height * 3) as usize; // RGB
        
        for i in 0..pattern_size {
            let value = ((data_hash.wrapping_mul(i as u64 + 1)) % 256) as u8;
            image_data.push(value);
        }
        
        Ok((image_data, (image_width, image_height)))
    }

    /// Generate SVG image
    fn generate_svg_image(&self, qr_data: &str) -> crate::Result<(String, (u32, u32))> {
        let data_len = qr_data.len();
        let matrix_size = ((data_len as f64).sqrt().ceil() as u32).max(21);
        
        let module_count = matrix_size;
        let image_width = module_count * self.options.module_size + 2 * self.options.border_size;
        let image_height = image_width;
        
        // Generate SVG content
        let mut svg = String::new();
        svg.push_str(&format!(
            r#"<svg xmlns="http://www.w3.org/2000/svg" width="{}" height="{}" viewBox="0 0 {} {}">"#,
            image_width, image_height, image_width, image_height
        ));
        
        // Add white background
        svg.push_str(&format!(
            r#"<rect width="{}" height="{}" fill="white"/>"#,
            image_width, image_height
        ));
        
        // Generate pattern based on QR data
        let data_hash = self.simple_hash(qr_data);
        
        for y in 0..matrix_size {
            for x in 0..matrix_size {
                let pos_hash = data_hash.wrapping_mul((y * matrix_size + x + 1) as u64);
                if pos_hash % 2 == 0 {
                    let rect_x = self.options.border_size + x * self.options.module_size;
                    let rect_y = self.options.border_size + y * self.options.module_size;
                    
                    svg.push_str(&format!(
                        r#"<rect x="{}" y="{}" width="{}" height="{}" fill="black"/>"#,
                        rect_x, rect_y, self.options.module_size, self.options.module_size
                    ));
                }
            }
        }
        
        svg.push_str("</svg>");
        
        Ok((svg, (image_width, image_height)))
    }

    /// Simple hash function for demo purposes
    fn simple_hash(&self, data: &str) -> u64 {
        let mut hash = 0xcbf29ce484222325u64; // FNV offset basis
        for byte in data.bytes() {
            hash ^= byte as u64;
            hash = hash.wrapping_mul(0x100000001b3u64); // FNV prime
        }
        hash
    }
}

/// Helper functions for common QR encoding tasks
impl QREncoder {
    /// Create a high-quality QR code for printing
    pub fn encode_for_print(&self, qr_data: QRData) -> crate::Result<EncodedQRResult> {
        let print_options = QREncodingOptions {
            error_correction_level: QRErrorCorrectionLevel::High,
            border_size: 8,
            module_size: 12,
            include_base64_image: true,
            image_format: QRImageFormat::PNG,
        };
        
        let encoder = QREncoder::with_options(print_options);
        encoder.encode_qr(qr_data)
    }

    /// Create a compact QR code for web display
    pub fn encode_for_web(&self, qr_data: QRData) -> crate::Result<EncodedQRResult> {
        let web_options = QREncodingOptions {
            error_correction_level: QRErrorCorrectionLevel::Medium,
            border_size: 2,
            module_size: 4,
            include_base64_image: true,
            image_format: QRImageFormat::SVG,
        };
        
        let encoder = QREncoder::with_options(web_options);
        encoder.encode_qr(qr_data)
    }

    /// Create a mobile-optimized QR code
    pub fn encode_for_mobile(&self, qr_data: QRData) -> crate::Result<EncodedQRResult> {
        let mobile_options = QREncodingOptions {
            error_correction_level: QRErrorCorrectionLevel::Quartile,
            border_size: 4,
            module_size: 6,
            include_base64_image: true,
            image_format: QRImageFormat::PNG,
        };
        
        let encoder = QREncoder::with_options(mobile_options);
        encoder.encode_qr(qr_data)
    }
}

/// QR decoding functionality
impl QREncoder {
    /// Decode QR data from image bytes (simplified implementation)
    pub fn decode_qr_image(&self, image_data: &[u8]) -> crate::Result<String> {
        // This would use a QR decoding library in a real implementation
        // For now, return a mock decoded result
        
        if image_data.len() < 100 {
            return Err(crate::Error::QRError("Image data too small".to_string()));
        }
        
        // Mock decoding - in reality this would analyze the image
        let mock_decoded = format!(
            r#"{{"lemma": {{"claims": {{"mockDecoded": true}}}}, "qr_type": "EventTicket", "metadata": {{"created_at": {}}}}}"#,
            chrono::Utc::now().timestamp()
        );
        
        Ok(mock_decoded)
    }

    /// Decode QR data from base64 image string
    pub fn decode_qr_base64(&self, base64_data: &str) -> crate::Result<String> {
        // Remove data URL prefix if present
        let base64_content = if base64_data.starts_with("data:image/") {
            base64_data.split(',').nth(1).unwrap_or(base64_data)
        } else {
            base64_data
        };

        // Decode base64
        let image_data = general_purpose::STANDARD
            .decode(base64_content)
            .map_err(|e| crate::Error::QRError(format!("Base64 decode error: {}", e)))?;
        
        self.decode_qr_image(&image_data)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::qr::{QRType, QRMetadata};
    use crate::credentials::LemmaCredential;

    fn create_test_qr_data() -> QRData {
        // Create a mock lemma credential
        let credential = LemmaCredential {
            id: "test_qr_123".to_string(),
            issuer: "did:lemma:test".to_string(),
            subject: "did:lemma:user".to_string(),
            claims: std::collections::HashMap::new(),
            signature: "mock_signature".to_string(),
            created_at: chrono::Utc::now().timestamp() as u64,
            expires_at: None,
        };

        QRData::new(
            credential,
            QRType::EventTicket,
            QRMetadata::new(),
        )
    }

    #[test]
    fn test_encode_png_qr() {
        let encoder = QREncoder::new();
        let qr_data = create_test_qr_data();
        
        let result = encoder.encode_qr(qr_data);
        assert!(result.is_ok());
        
        let encoded = result.unwrap();
        assert!(encoded.base64_image.is_some());
        assert!(encoded.encoding_time_us > 0.0);
        assert_eq!(encoded.image_size.0, encoded.image_size.1); // Square image
    }

    #[test]
    fn test_encode_svg_qr() {
        let options = QREncodingOptions {
            image_format: QRImageFormat::SVG,
            ..Default::default()
        };
        let encoder = QREncoder::with_options(options);
        let qr_data = create_test_qr_data();
        
        let result = encoder.encode_qr(qr_data);
        assert!(result.is_ok());
        
        let encoded = result.unwrap();
        assert!(encoded.svg_data.is_some());
        assert!(encoded.svg_data.unwrap().contains("<svg"));
    }

    #[test]
    fn test_encode_for_print() {
        let encoder = QREncoder::new();
        let qr_data = create_test_qr_data();
        
        let result = encoder.encode_for_print(qr_data);
        assert!(result.is_ok());
        
        let encoded = result.unwrap();
        // Print version should have larger dimensions
        assert!(encoded.image_size.0 > 200); // Larger for printing
    }

    #[test]
    fn test_encode_for_web() {
        let encoder = QREncoder::new();
        let qr_data = create_test_qr_data();
        
        let result = encoder.encode_for_web(qr_data);
        assert!(result.is_ok());
        
        let encoded = result.unwrap();
        assert!(encoded.svg_data.is_some()); // Web version uses SVG
    }
} 