# Lemma Shield API - Python Quick Start

Get up and running with Lemma Shield in under 15 lines of Python code.

## Installation

```bash
pip install requests
```

## Basic Usage

```python
import requests
import json

# Configure the API client
class LemmaShield:
    def __init__(self, api_key):
        self.base_url = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/v1'
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
    
    def start_kyc(self, user_id, callback_url=None):
        """Start KYC verification for a user"""
        data = {'user_id': user_id}
        if callback_url:
            data['callback_url'] = callback_url
        
        response = requests.post(f'{self.base_url}/kyc/start', 
                               headers=self.headers, json=data)
        response.raise_for_status()
        return response.json()
    
    def get_challenge(self):
        """Generate a verification challenge"""
        response = requests.get(f'{self.base_url}/challenge')
        response.raise_for_status()
        return response.json()['challenge']
    
    def verify_presentation(self, presentation, challenge):
        """Verify a credential presentation"""
        data = {'presentation': presentation, 'challenge': challenge}
        response = requests.post(f'{self.base_url}/verify', json=data)
        response.raise_for_status()
        return response.json()['verified']

# Example usage
lemma = LemmaShield('YOUR_API_KEY_HERE')

# Start verification
kyc_response = lemma.start_kyc('user_12345')
print(f"KYC URL: {kyc_response['verification_url']}")

# Verify a user (assuming you have their presentation)
challenge = lemma.get_challenge()
is_verified = lemma.verify_presentation(user_presentation, challenge)
print(f"User verified: {is_verified}")
```

## Flask Integration

```python
from flask import Flask, request, jsonify

app = Flask(__name__)
lemma = LemmaShield('YOUR_API_KEY_HERE')

@app.route('/protected', methods=['POST'])
def protected_endpoint():
    """Protected endpoint requiring human verification"""
    presentation = request.json.get('presentation')
    
    if not presentation:
        return jsonify({'error': 'Presentation required'}), 400
    
    try:
        # Get fresh challenge and verify
        challenge = lemma.get_challenge()
        is_verified = lemma.verify_presentation(presentation, challenge)
        
        if is_verified:
            return jsonify({'message': 'Access granted to verified human!'})
        else:
            return jsonify({'error': 'Human verification failed'}), 403
            
    except requests.exceptions.HTTPError as e:
        return jsonify({'error': f'Verification error: {e}'}), 500

if __name__ == '__main__':
    app.run(debug=True)
```

## Django Integration

```python
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json

lemma = LemmaShield('YOUR_API_KEY_HERE')

@csrf_exempt
@require_http_methods(["POST"])
def verify_human(request):
    """Django view for human verification"""
    try:
        data = json.loads(request.body)
        presentation = data.get('presentation')
        
        if not presentation:
            return JsonResponse({'error': 'Presentation required'}, status=400)
        
        challenge = lemma.get_challenge()
        is_verified = lemma.verify_presentation(presentation, challenge)
        
        if is_verified:
            return JsonResponse({'verified': True, 'message': 'Human verified'})
        else:
            return JsonResponse({'verified': False, 'error': 'Verification failed'}, status=403)
            
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
```

## Error Handling

```python
import requests

def safe_verification(lemma, presentation):
    """Robust verification with error handling"""
    try:
        challenge = lemma.get_challenge()
        result = lemma.verify_presentation(presentation, challenge)
        return {'success': True, 'verified': result}
    
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            return {'success': False, 'error': 'Invalid API key'}
        elif e.response.status_code == 429:
            return {'success': False, 'error': 'Rate limit exceeded'}
        else:
            return {'success': False, 'error': f'HTTP {e.response.status_code}'}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}

# Usage
result = safe_verification(lemma, user_presentation)
if result['success']:
    print(f"Verification result: {result['verified']}")
else:
    print(f"Error: {result['error']}")
```

## Async Support (Python 3.7+)

```python
import aiohttp
import asyncio

class AsyncLemmaShield:
    def __init__(self, api_key):
        self.base_url = 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/v1'
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
    
    async def verify_async(self, presentation):
        """Async verification flow"""
        async with aiohttp.ClientSession() as session:
            # Get challenge
            async with session.get(f'{self.base_url}/challenge') as resp:
                challenge_data = await resp.json()
                challenge = challenge_data['challenge']
            
            # Verify presentation
            data = {'presentation': presentation, 'challenge': challenge}
            async with session.post(f'{self.base_url}/verify', 
                                  headers=self.headers, json=data) as resp:
                result = await resp.json()
                return result['verified']

# Usage
async def main():
    lemma = AsyncLemmaShield('YOUR_API_KEY_HERE')
    is_verified = await lemma.verify_async(user_presentation)
    print(f"Verified: {is_verified}")

# Run async
asyncio.run(main())
```

That's it! You now have human verification in your Python application with minimal code. 