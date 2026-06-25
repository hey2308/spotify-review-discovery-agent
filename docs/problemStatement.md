
This builds directly on the product chosen: **Spotify**. The goal is to transform scattered, unstructured user feedback — spread across app stores, play stores, Reddit threads, community forums, and social media — into structured, actionable intelligence that answers specific questions about why Spotify users fail to discover new music.

The feedback signal already exists publicly. Your job is to aggregate it at scale, run it through an AI-powered analysis pipeline, and surface every insight through a live interactive dashboard — with a real backend processing the data and a real frontend rendering the intelligence — so that any stakeholder can understand the discovery problem without reading a single raw review.

---

## End-to-End Flow — What "Done" Looks Like

```
Pull public reviews + discussions from multiple sources
                    ↓
Run AI analysis pipeline to extract themes, sentiments, patterns
                    ↓
Answer all 6 discovery questions from the analyzed data
                    ↓
Store structured insights in backend
                    ↓
Render everything on a live interactive frontend dashboard
                    ↓
Stakeholder opens dashboard → sees the full picture instantly
```

---

## Data Sources to Pull From

Aggregate feedback from all of the following public sources covering the **last 6 months**:

| Source | What to Pull | Fields to Capture |
|---|---|---|
| App Store | Spotify reviews | Rating, title, review text, date |
| Play Store | Spotify reviews | Rating, title, review text, date |
| Reddit | r/spotify, r/Music, r/ifyoulikeblank | Post title, body, top comments, date |
| Community Forums | Spotify Community boards | Thread title, post text, date |
| Social Media | Public posts about Spotify discovery | Post text, platform, date |

> **Constraint:** Public data only. No scraping behind login walls or any ToS-violating automation.

---

## What the AI Pipeline Must Answer

Every piece of collected feedback must flow through an AI analysis layer designed to answer these **6 specific discovery questions**. These are not optional — each question must have a dedicated, visible answer on the dashboard:

**Q1 — Why do users struggle to discover new music?**
Root cause analysis across all sources. What specific barriers, moments, and product failures do users describe?

**Q2 — What are the most common frustrations with recommendations?**
Frequency-ranked list of recommendation failures — what the algorithm gets wrong, how often, and in what contexts.

**Q3 — What listening behaviors are users trying to achieve?**
Intent mapping — what goals (focus, mood, exploration, workout, sleep) users bring to a listening session and whether the product serves them.

**Q4 — What causes users to repeatedly listen to the same content?**
Behavioral pattern extraction — what triggers comfort-listening loops and whether users describe them as intentional or accidental.

**Q5 — Which user segments experience different discovery challenges?**
Segment identification from review language — power users vs casual listeners, genre-locked vs eclectic, new users vs long-term subscribers.

**Q6 — What unmet needs emerge consistently across all sources?**
Gap analysis — what users explicitly wish existed, what they do outside the product to compensate, what they describe as missing.

---

## Dashboard Architecture

```
BACKEND                          FRONTEND
─────────────────────            ──────────────────────────────
Review ingestion pipeline   →    Dashboard renders structured data
AI analysis layer           →    Charts, filters, quote explorer
Structured data store       →    Segment drill-downs
API endpoints               →    Real-time or near-real-time updates
```

---

## Dashboard Sections — What Must Be Visible

### Section 1 — Discovery Overview
High-level snapshot of the discovery problem across all sources:
- Total reviews analyzed, date range covered, source breakdown
- Overall sentiment distribution (positive / neutral / negative) as a visual chart
- Single headline insight: the most common reason users fail to discover new music

### Section 2 — Theme Clusters (Max 5 Themes)
Visual clustering of all feedback into at most 5 themes:
- Each theme displayed as a card or panel with its name, volume of mentions, and sentiment score
- Clicking a theme expands it to show representative quotes and sub-patterns
- A visual (bar chart, bubble chart, or treemap) showing relative theme size

### Section 3 — Q&A Intelligence Panel
Six dedicated panels — one per discovery question — each showing:
- The AI-generated answer in plain language
- Supporting evidence (quote snippets, mention counts, source breakdown)
- Confidence or frequency signal so the reader knows how strongly the data supports the answer

### Section 4 — Verbatim Quote Explorer
A searchable, filterable table of real user quotes:
- Filter by theme, source, rating, date range
- No PII — all usernames, device IDs, and identifiable information stripped
- Each quote tagged with its theme, source, and sentiment

### Section 5 — User Segment Breakdown
Visual segmentation of who is experiencing which discovery challenges:
- Segment labels derived from review language (e.g. power user, casual listener, genre-locked, new subscriber)
- Per-segment: top frustration, top unmet need, most common behavior pattern
- Comparative view so segments can be read side by side

### Section 6 — Unmet Needs Tracker
Ranked list of unmet needs extracted from Q6 analysis:
- Each need shown with mention frequency across sources
- Color-coded by urgency signal (how emotionally charged the language is)
- Source attribution showing whether the need appears across all platforms or is concentrated in one

---

## Key Constraints

| Constraint | Rule |
|---|---|
| Data sources | Public exports and APIs only — no login-gated scraping |
| Theme limit | Maximum 5 themes for clustering |
| Questions | All 6 discovery questions must be answered and displayed |
| Privacy | No usernames, emails, device IDs, or any reviewer PII in any artifact or dashboard view |
| Quotes | Verbatim only — no paraphrased or invented wording |
| Integration | Real backend + real frontend — not a static mockup |
| AI requirement | AI must perform the analysis — not manual tagging or keyword rules |

---

## Who This Dashboard Serves

| Audience | What They Get From It |
|---|---|
| Product / Growth PM | Prioritize which discovery failures to fix first, backed by real user signal |
| Algorithm Team | Understand which recommendation failures users notice and articulate most |
| UX Research | Validate qualitative hypotheses with quantitative review data |
| Leadership | Instant health check on the discovery experience without reading raw data |

---

## Definition of Done

A stakeholder opens the dashboard and within **5 minutes** can clearly answer:

1. What is the single biggest reason Spotify users fail to discover new music?
2. Which user segment is most affected?
3. What does the algorithm get wrong most often?
4. What are users doing instead of using Spotify for discovery?
5. What three things should the product team prioritize next?

> If the dashboard answers all five of those questions without the stakeholder needing to read a single raw review — **the system is done.**