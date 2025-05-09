"""
QR code generator utility for the Lemma Human Verification System.
"""
import qrcode
import io
import base64

def generate_qr_code_base64(data, box_size=10, border=4):
    """
    Generate a QR code and return it as a base64-encoded string.
    
    Args:
        data: The data to encode in the QR code
        box_size: The size of each box in the QR code
        border: The size of the border around the QR code
        
    Returns:
        A base64-encoded string of the QR code image
    """
    # Create QR code instance
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=box_size,
        border=border,
    )
    
    # Add data to the QR code
    qr.add_data(data)
    qr.make(fit=True)
    
    # Create an image from the QR code
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save the image to a bytes buffer
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    
    # Convert to base64
    img_str = base64.b64encode(buffer.getvalue()).decode('ascii')
    
    return f"data:image/png;base64,{img_str}"
