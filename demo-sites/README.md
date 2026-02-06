# Lemma.id Cross-Site Login Demo

This demo showcases the difference between traditional username/password login and Lemma.id authentication across multiple sites.

## The Demo Experience

### With Username/Password:
1. Visit Site 1 → Enter email/password → Sign in
2. Visit Site 2 → Enter email/password AGAIN → Sign in
3. Visit Site 3 → Enter email/password AGAIN → Sign in

**Result:** 3 logins, ~60 keystrokes, ~30 seconds

### With Lemma.id:
1. Unlock wallet once (passkey)
2. Visit Site 1 → Instant sign-in
3. Visit Site 2 → Instant sign-in
4. Visit Site 3 → Instant sign-in

**Result:** 1 passkey, 0 keystrokes, ~2 seconds total

## Demo Sites

| Site | Theme | Purpose |
|------|-------|---------|
| **TechPulse** (📰) | Blue - News | Media/content site |
| **ShopFlow** (🛒) | Purple - E-commerce | Shopping site |
| **SecureBank** (🏦) | Green - Finance | Banking site |

## Local Development

Run all three sites locally:

```bash
# Terminal 1
cd demo-sites/site1-news
pip install -r requirements.txt
python app.py  # Runs on port 5001

# Terminal 2
cd demo-sites/site2-shop
pip install -r requirements.txt
python app.py  # Runs on port 5002

# Terminal 3
cd demo-sites/site3-bank
pip install -r requirements.txt
python app.py  # Runs on port 5003
```

Then visit:
- http://localhost:5001 (TechPulse)
- http://localhost:5002 (ShopFlow)
- http://localhost:5003 (SecureBank)

## Heroku Deployment

### 1. Create three Heroku apps:

```bash
heroku create lemma-demo-news --remote demo-news
heroku create lemma-demo-shop --remote demo-shop
heroku create lemma-demo-bank --remote demo-bank
```

### 2. Set environment variables:

Each site needs cross-site URLs and Lemma.id API credentials.
Get your `LEMMA_API_KEY` and `LEMMA_SITE_ID` from https://lemma.id/developer after registering each site.

```bash
# For Site 1 (News)
heroku config:set SITE1_URL=https://lemma-demo-news.herokuapp.com \
                  SITE2_URL=https://lemma-demo-shop.herokuapp.com \
                  SITE3_URL=https://lemma-demo-bank.herokuapp.com \
                  LEMMA_API_KEY=your_news_api_key \
                  LEMMA_SITE_ID=your_news_site_id \
                  --app lemma-demo-news

# For Site 2 (Shop)
heroku config:set SITE1_URL=https://lemma-demo-news.herokuapp.com \
                  SITE2_URL=https://lemma-demo-shop.herokuapp.com \
                  SITE3_URL=https://lemma-demo-bank.herokuapp.com \
                  LEMMA_API_KEY=your_shop_api_key \
                  LEMMA_SITE_ID=your_shop_site_id \
                  --app lemma-demo-shop

# For Site 3 (Bank)
heroku config:set SITE1_URL=https://lemma-demo-news.herokuapp.com \
                  SITE2_URL=https://lemma-demo-shop.herokuapp.com \
                  SITE3_URL=https://lemma-demo-bank.herokuapp.com \
                  LEMMA_API_KEY=your_bank_api_key \
                  LEMMA_SITE_ID=your_bank_site_id \
                  --app lemma-demo-bank
```

### 3. Deploy each site:

Since each site is in a subdirectory, use git subtree:

```bash
# From the lemma-rebuild root directory

# Deploy Site 1
git subtree push --prefix demo-sites/site1-news demo-news main

# Deploy Site 2
git subtree push --prefix demo-sites/site2-shop demo-shop main

# Deploy Site 3
git subtree push --prefix demo-sites/site3-bank demo-bank main
```

Or manually push each folder:

```bash
cd demo-sites/site1-news
git init
heroku git:remote -a lemma-demo-news
git add .
git commit -m "Deploy news demo"
git push heroku main
```

### 4. Register demo sites with Lemma.id

For the Lemma.id authentication to work, each demo site needs to be registered:

1. Go to https://lemma.id/developer
2. Register each demo domain as an allowed origin
3. The SDK will then work on those domains

## What the Demo Shows

### Metrics Displayed:
- **Login time** - How long the authentication took
- **Keystrokes** - How many keys the user pressed

### User Journey:
1. User arrives at Site 1
2. Chooses either password or Lemma login
3. After login, clicks to visit Site 2
4. With password: must re-enter credentials
5. With Lemma: automatically authenticated
6. Repeat for Site 3

### Key Insight:
The password user enters ~60 keystrokes across 3 sites.
The Lemma user enters 0 keystrokes after initial unlock.

## Customization

Each site's appearance is controlled by `SITE_CONFIG` in its `app.py`:

```python
SITE_CONFIG = {
    'site_name': 'TechPulse',
    'site_icon': '📰',
    'site_tagline': 'Breaking tech news',
    'bg_gradient': 'linear-gradient(135deg, #f0f9ff, #e0f2fe)',
    'header_bg': 'white',
    'accent_color': '#0284c7',
}
```

Each site has its own template in `templates/index.html`.
