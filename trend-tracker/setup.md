# Instagram Trend Tracker — Setup Guide

## What This App Does
Aggregates real-time trend signals from 5 sources and surfaces:
- **Trending NOW** keywords dominating Instagram right now
- **Upcoming** keywords gaining velocity (early-mover opportunity)
- **Trending Reels URLs** — actual links to Reels others are templating
- **Potential Viral Reels** — recent Reels gaining traction fast

---

## 1. Install

```bash
cd trend-tracker
pip install -r requirements.txt
```

---

## 2. Set Up API Keys

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Then fill in the keys you want (details below).

---

## 3. API Keys — What You Need & How to Get Them

### ✅ Google Trends — NO KEY NEEDED
Works out of the box via `pytrends`. No account required.

### ✅ Exploding Topics — NO KEY NEEDED
Uses their public trending page. No account required.

### ✅ Social Blade — NO KEY NEEDED (for basic use)
Scrapes their public fastest-growing accounts page.
Optional: add a paid API key from `socialblade.com/business/api` for more data.

---

### 🔑 Meta Ads Library (Free)
Shows what Instagram ad formats and themes are trending.

1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Click **My Apps** → **Create App** → choose **Business**
3. Add the **Marketing API** product
4. Go to **Tools** → **Graph API Explorer**
5. Select your app, click **Generate Access Token**
6. Add permission: `ads_read`
7. Copy the token → paste into `.env` as `META_ACCESS_TOKEN`

> Token expires after 60 days. Re-generate when it does.

---

### 🔑 Instagram Graph API (For Reels URLs)
This is what unlocks **actual Reels permalink URLs**.

**Requirements:**
- A Facebook Page (any page)
- An **Instagram Business** or **Creator** account (not personal)
- The Instagram account must be connected to the Facebook Page

**Steps:**
1. Connect your Instagram to a Facebook Page:
   - Instagram → Settings → Account → Switch to Professional Account
   - Then link it to a Facebook Page under Settings → Linked Accounts

2. Create/use your Facebook Developer App (same as Meta Ads above)

3. Add **Instagram Graph API** product to your app

4. In Graph API Explorer:
   - Select your app
   - Click **Get User Access Token**
   - Add permissions: `instagram_basic`, `instagram_manage_insights`, `pages_read_engagement`
   - Generate token

5. **Get your Instagram Business Account ID:**
   ```
   GET https://graph.facebook.com/v19.0/me/accounts?access_token=YOUR_TOKEN
   ```
   This returns your Pages. Then:
   ```
   GET https://graph.facebook.com/v19.0/{PAGE_ID}?fields=instagram_business_account&access_token=YOUR_TOKEN
   ```
   The `instagram_business_account.id` is your account ID.

6. **Make it a long-lived token** (valid 60 days):
   ```
   GET https://graph.facebook.com/v19.0/oauth/access_token
     ?grant_type=fb_exchange_token
     &client_id={APP_ID}
     &client_secret={APP_SECRET}
     &fb_exchange_token={SHORT_LIVED_TOKEN}
   ```

7. Paste both into `.env`:
   ```
   INSTAGRAM_ACCESS_TOKEN=EAAxxxxxxx...
   INSTAGRAM_BUSINESS_ACCOUNT_ID=17841400000000000
   ```

---

## 4. Run the App

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`

---

## 5. Using the App

1. **Without API keys**: Google Trends + Exploding Topics + Social Blade work immediately. Click **Fetch Trends**.

2. **With Meta token**: Adds ad format trends and copy themes.

3. **With Instagram token**: Unlocks the Reels URL columns — actual links to trending and upcoming viral Reels.

4. **Niches**: Select content categories in the sidebar to focus hashtag discovery.

5. **Export**: Use the "Full Trend Data Table" expander to download a CSV.

---

## 6. Understanding the Scores

| Score | Meaning |
|-------|---------|
| 70–100 | Strong trend signal, high cross-platform agreement |
| 40–70  | Moderate signal, worth monitoring |
| <40    | Early/weak signal — potential upcoming trend |

**Velocity** > 1.0 means the trend is accelerating.
**Source Count** > 1 means multiple platforms agree — strongest signal.

---

## 7. Trend Types Explained

### 🔥 Trending NOW
- High current search/engagement volume
- Already being widely copied
- **Strategy**: Jump on this format NOW or you'll be late

### ⚡ Upcoming
- High velocity (fast acceleration) but lower current volume
- Early-stage signals
- **Strategy**: Create content NOW to be ahead of the wave

---

## 8. Reels URL Section

### Trending Reels
Direct Instagram URLs to Reels that are currently viral.
These are templates other creators are copying right now.

### Potential Viral Reels
Recent Reels with strong early engagement signals.
These haven't peaked yet — highest opportunity.

---

## Rate Limits

| Source | Limit |
|--------|-------|
| Google Trends | ~10 req/min (pytrends handles this) |
| Meta Ads API | 200 req/hour |
| Instagram Graph | 200 req/hour per token |
| Exploding Topics | Normal web browsing rate |
| Social Blade | Normal web browsing rate |

Don't click Fetch Trends more than once per minute to stay within limits.

---

## Troubleshooting

**"pytrends" errors**: Google Trends sometimes returns 429. Wait 60 seconds and retry.

**Meta token invalid**: Tokens expire. Re-generate at developers.facebook.com.

**Instagram API returns empty**: Make sure your account is a Business/Creator account (not personal) and is linked to a Facebook Page.

**Social Blade returns nothing**: Their site may have changed structure. The app still works with other sources.
