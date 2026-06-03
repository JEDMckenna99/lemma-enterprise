# Lemma CDN Distribution

This directory contains the CDN-ready builds of all Lemma verification scripts.

## Quick Start

### Basic Integration (Auto-detection)
```html
<script src="https://cdn.lemma.id/js/lemma-auto.min.js" 
        integrity="sha384-..." 
        crossorigin="anonymous"></script>
<div data-lemma-verify="auto">
  <p>Loading verification...</p>
</div>
```

### With Styling
```html
<link rel="stylesheet" 
      href="https://cdn.lemma.id/css/lemma-styles.min.css"
      integrity="sha384-..." 
      crossorigin="anonymous">
<script src="https://cdn.lemma.id/js/lemma-auto.min.js" 
        integrity="sha384-..." 
        crossorigin="anonymous"></script>
```

## Available Files

### JavaScript
- `lemma-auto.js` / `lemma-auto.min.js` - Auto-integration script
- `lemma-verification-flow.js` / `lemma-verification-flow.min.js` - Verification flow components
- `lemma-shield-inline.js` / `lemma-shield-inline.min.js` - Inline shield components

### CSS
- `lemma-styles.css` / `lemma-styles.min.css` - Core Lemma styles
- `stripe-design.css` / `stripe-design.min.css` - Stripe design system

### Compression
All minified files are available in:
- `.gz` (gzip compression)
- `.br` (brotli compression)

## Integrity Verification

All files include SHA-384 integrity hashes for security. Check `manifest.json` for current hashes.

## Version Information

- Version: 1.0.0
- Build Date: 2026-06-03T21:16:12.010Z
- Environment: Production

## Self-Hosting

To self-host these files:

1. Download the entire `dist/` directory
2. Host on your CDN or static file server
3. Update script `src` attributes to point to your hosting location
4. Ensure proper CORS headers for cross-origin requests

## Performance Notes

- All files are optimized for production
- Gzip compression reduces file sizes by ~70%
- Brotli compression reduces file sizes by ~75%
- Use HTTP/2 for optimal performance
- Enable caching headers for better performance

## Support

For issues or questions about CDN distribution:
- Check the manifest.json for current file information
- Verify integrity hashes match
- Ensure proper CORS configuration
- Use the unminified versions for debugging

Built with Lemma CDN Build System v1.0.0
