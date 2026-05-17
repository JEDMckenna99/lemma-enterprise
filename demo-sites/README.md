# isHuman Relying-Site Demo Apps

These tiny Flask apps simulate real third-party relying sites for the isHuman demo.

Each app serves one page that loads:

```html
<script src="https://lemma.id/sdk/ishuman-verifier.js"></script>
```

and calls:

```js
new IsHumanVerifier({
  siteId: "<site binding>",
  lemmaOrigin: "https://lemma.id"
}).verify()
```

## Expected Heroku Apps

- `lemma-demo-tickets`
  - `LEMMA_DEMO_SITE_ID=tickets-demo.lemma.id`
  - `LEMMA_DEMO_SITE_NAME=Lemma Ticketing Demo`
  - `LEMMA_DEMO_SITE_KIND=ticketing`
- `lemma-demo-trials`
  - `LEMMA_DEMO_SITE_ID=trials-demo.lemma.id`
  - `LEMMA_DEMO_SITE_NAME=Lemma Free Trial Demo`
  - `LEMMA_DEMO_SITE_KIND=free trial`

## Deploy

From the repository root:

```powershell
git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-tickets.git main
git subtree push --prefix demo-sites https://git.heroku.com/lemma-demo-trials.git main
```

