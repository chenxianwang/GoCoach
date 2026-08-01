# 一目弈镜 · iOS App — Feasibility & Project Plan

*Prepared for a solo builder (you + AI), free-to-launch with optional later monetization. Estimates assume part-time work (~15–20 hrs/week) unless noted.*

---

## 0. TL;DR — verdict & recommendation

**Feasible, and a strong portfolio/contest story — but it is a real project, not a weekend port.** The web app you have cannot ship to strangers as-is, for one reason: it depends on a local Python server calling KataGo through **your personal ikatago cloud account**. You cannot put your account (or a Python server) inside an App Store app.

The single most important design decision is therefore *how analysis runs*. My recommendation:

- **Build approach:** a **native SwiftUI shell** that **reuses your existing HTML/CSS/JS report** inside a bundled `WKWebView`. You keep months of front-end work (charts, 失误集, 终局估计); you rewrite navigation, import, and the analysis glue natively. A *pure* web wrapper is likely to be rejected (App Store rule 4.2), so "native shell + embedded report view" is the sweet spot.
- **Analysis engine:** **on-device KataGo** (CoreML/Metal). It eliminates the account problem entirely, has **no server cost**, works offline, and is proven on iOS. It is the hardest part, so **phase it**: ship a viewer/import MVP first, add on-device analysis second.
- **Drop the 野狐 auto-download** for the public app (it scrapes an unofficial endpoint with a logged-in account — legal/ToS/technical risk on mobile). Instead let users **import SGFs** (share sheet / Files / iCloud), plus later on-device analysis.

**Rough total (solo + AI, part-time): ~4–6 months** to a polished on-device release; **~6–8 weeks** to an import-only viewer MVP. **Cash to launch: ~US$100–400** plus the **$99/year** Apple fee.

---

## 1. The core challenge, stated plainly

| Today (desktop) | Why it can't ship to iOS | iOS answer |
|---|---|---|
| Local Python `http.server` | Apps can't run a Python server; no background local server model | Native Swift app; logic ported to Swift/JS |
| ikatago (your cloud KataGo account) | You'd be shipping your credentials to every user — ToS violation, abuse, cost | On-device KataGo (CoreML) — each phone analyzes itself |
| 野狐 UID auto-download | Unofficial endpoint + user's login; fragile & IP-sensitive | Import SGF; (optional) official share/export flows |
| `report.py` builds HTML | Python can't run on iOS | Port aggregation to JS (reuse your HTML/CSS) or Swift |
| Reports as local files | Fine — this part maps well to iOS | Keep; store in app sandbox / iCloud |

The good news: your **report front-end** (the HTML/CSS/SVG dashboard, 失误集, 逐局回顾, 终局估计) is portable almost verbatim into a `WKWebView`. The **parsing/aggregation** (`import_lizzie.py`, `report.py`, `sgfparse.py`, `estimate_score.py`) is pure logic you can port to Swift or JavaScript.

---

## 2. Recommended architecture

```
┌─────────────────────────────────────────────┐
│  SwiftUI app shell (native)                   │
│  • report list / sidebar / navigation         │
│  • SGF import (share sheet, Files, iCloud)     │
│  • settings, paywall stub (later)              │
│                                                │
│  ┌───────────────┐   ┌──────────────────────┐ │
│  │ KataGo engine │   │  Report renderer      │ │
│  │ (CoreML/Metal)│──▶│  WKWebView + your      │ │
│  │  on-device    │   │  HTML/CSS/JS (reused)  │ │
│  └───────────────┘   └──────────────────────┘ │
│         │  analysis → per-move JSON  ▲          │
│         └───── aggregation (JS/Swift)┘          │
└─────────────────────────────────────────────┘
   No server. No accounts. Works offline.
```

**What you reuse:** the entire report UI (HTML/CSS/JS charts you already built), the JSON schema, the analysis *definitions* (blunder = ≥6目 or 胜率−15%, phases, improvement metric, territory estimate).
**What you rewrite:** the server → native shell; Python aggregation → JS/Swift; ikatago call → on-device KataGo; Fox download → SGF import.

---

## 3. Project breakdown (phases → milestones)

### Phase 0 — Validation spikes (go/no-go) · ~2–3 wks
- [ ] Enroll in Apple Developer Program; get Xcode + a physical test iPhone.
- [ ] **KataGo-on-device spike:** get a CoreML KataGo net to analyze *one* SGF on an iPhone and print per-move winrate/score. **This is the gate — do it before anything else.**
- [ ] Confirm the report HTML renders correctly inside a `WKWebView` (charts, fonts, SVG).
- [ ] Decide data model: reuse your per-game JSON schema unchanged.

### Phase 1 — Import-only viewer MVP · ~4–6 wks
- [ ] SwiftUI shell: report list, open report, delete, settings.
- [ ] SGF import via share sheet / Files / iCloud Drive / paste.
- [ ] Port aggregation (`report.py` logic) to **JavaScript**, bundle with your existing HTML → full report renders offline in `WKWebView`.
- [ ] Port `import_lizzie` parsing (LizzieYZY analyzed SGF → your JSON) to JS/Swift.
- [ ] App icon, launch screen, basic onboarding.
- [ ] **Shippable:** a real, useful app (view & organize analyzed games) even without on-device analysis.

### Phase 2 — On-device analysis · ~6–10 wks (the hard part)
- [ ] Integrate KataGo CoreML engine into the Swift app (background thread, cancel/progress).
- [ ] Feed a raw SGF → run analysis at a chosen visit budget → emit the same per-move JSON.
- [ ] Port `estimate_score.py` (ownership → territory) to Swift/JS.
- [ ] Performance/thermal tuning: visit caps, model size choice, "analyze while charging" option, older-device fallback.
- [ ] Progress UI + battery-aware defaults.

### Phase 3 — Polish, compliance & submission · ~3–4 wks
- [ ] Empty states, error handling, accessibility, Dark Mode, iPad layout (optional).
- [ ] Privacy policy + App Privacy "nutrition label" (likely "No data collected" if fully offline — a selling point).
- [ ] Screenshots, App Store description, keywords, age rating, export-compliance answer.
- [ ] TestFlight beta (10–20 testers), fix crash/feedback, submit for review, handle rejections.

*(Optional Phase 4 — monetization later: IAP for premium features, RevenueCat, paywall. Add ~2–3 wks when you decide.)*

---

## 4. Time estimate

| Path | Part-time (~15–20 h/wk) | Full-time |
|---|---|---|
| Import-only viewer MVP | ~6–8 weeks | ~3–4 weeks |
| + On-device analysis (full app) | ~4–6 months total | ~2.5–3.5 months |
| + Monetization layer (later) | +2–3 weeks | +1–1.5 weeks |

**Biggest variance drivers:** your Swift ramp-up, and the KataGo CoreML integration (Phase 0 spike will tell you if it's 2 weeks or 6). Budget generous buffer around Phase 2.

---

## 5. Budget estimate (solo)

| Item | Cost | Notes |
|---|---|---|
| Apple Developer Program | **$99 / year** | Required to publish. Individual enrollment. |
| Mac + Xcode | $0 | You already have a Mac; Xcode is free. |
| Test iPhone(s) | $0–200 | Ideally test on one mid/older device; a cheap used unit helps. |
| KataGo engine + models | $0 | Open source (MIT); nets are freely available. |
| App icon / screenshots / marketing | $0–300 | AI-generated or a cheap designer. |
| Privacy policy hosting | ~$0 | GitHub Pages / a simple page. |
| Optional hosted backend | $0 (on-device path) | Only if you ever choose cloud analysis: ~$15–60/mo + scaling. |
| **Cash to launch (on-device path)** | **~$100–400** + **$99/yr** | Mostly your time. |

If you instead *hired out* just the KataGo CoreML integration: realistically **$3k–15k** to a competent iOS/ML freelancer — but this is exactly the piece AI + the existing open-source forks make DIY-able.

*Later monetization note:* Apple takes **30%** (or **15%** under the Small Business Program, <$1M/yr, or year-2+ subscriptions). Factor this if you charge.

---

## 6. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **App Store 4.2 "minimum functionality"** (looks like a repackaged website) | Medium | High (rejection) | Native shell + native import/analysis + on-device features; don't ship a bare WebView. |
| **On-device KataGo perf/battery** on older iPhones | Medium | Medium | Visit caps, smaller net option, "analyze while charging", set a min-iOS/min-device. |
| **5.2 Intellectual Property** — 野狐 games/trademark, KataGo license | Medium | High | Drop Fox auto-download & branding; import-only; keep KataGo MIT attribution; verify network-weights license. |
| **Solo scope creep / time overrun** | High | Medium | Ship the import-only MVP first; treat on-device analysis as a fast-follow. |
| **Swift learning curve** | Medium | Medium | Lean on AI; the report UI is reused, so native surface area is smaller than it looks. |
| **Privacy/App Privacy labels** | Low | Medium | Stay fully offline → "No data collected"; publish a privacy policy anyway. |
| **Market saturation** (many Go apps) | Medium | Medium | Your differentiator = *multi-game review & improvement trends*, not single-game analysis. Lead with that. |
| **Shipping your ikatago credentials by accident** | Low | Critical | They're already git-ignored; never bundle `config.json`; on-device path removes the account entirely. |

---

## 7. App Store review gotchas to plan for

- **4.2 Minimum functionality** — the #1 reason simple "wrapper" apps get rejected. Make it feel native.
- **5.2 IP** — don't use the 野狐 name/logo or scrape their content in the shipped app; credit KataGo; check the neural-net weights' license.
- **5.1 Privacy** — App Privacy labels + a privacy policy URL are mandatory even for offline apps.
- **2.1 Completeness** — no placeholder screens, no crashes; reviewers test real flows.
- **Export compliance** — you'll answer an encryption question; standard HTTPS/none is a trivial declaration.
- **Age rating & metadata** — straightforward for a Go app.
- **Account-name on the store** — publishing as an individual shows your legal name; publishing under a *company* name needs a **D-U-N-S number** (free but takes 1–2+ weeks). Decide early if you care about the seller name.

---

## 8. What to prepare / notice *before* you start

1. **Enroll in Apple Developer now** (it can take a few days; ID verification). Decide individual vs. org (D-U-N-S) — this gates your store display name.
2. **Pick & clear a name.** Check App Store + a basic trademark search; secure the bundle ID and matching handles. ("一目弈镜" / an English name.)
3. **Get a test device**, ideally not your newest iPhone (you want to feel real-world performance).
4. **Do the Phase-0 KataGo spike first.** Everything else depends on it; don't build UI before you've analyzed one game on-device.
5. **Legal/hygiene:** finalize the privacy policy, keep credentials out of the bundle, and decide the 野狐 story (import-only is safest).
6. **Port plan:** list exactly which Python files become JS vs Swift (`report.py`+`sgfparse.py`+`import_lizzie.py` → JS alongside your HTML is the highest-leverage reuse).
7. **Scope discipline:** write down the MVP feature list and *freeze* it; ship the viewer, then iterate.

---

## 9. Recommended path (my honest advice)

1. **Weeks 1–3:** enroll + Phase-0 spike (KataGo on device + report in WebView). Go/no-go.
2. **Weeks 4–10:** ship the **import-only viewer** to TestFlight, then the App Store. Real users, real feedback, contest-ready — *without* the hardest part.
3. **Then:** add **on-device analysis** as v2. This sequencing gets you a live App Store app in ~2 months while de-risking the ML work.
4. **Keep the desktop app** as the "power user / batch analysis" companion — it's genuinely a strength, not a thing to throw away.

Monetization, when you want it: freemium — free viewer + a few free analyses/day, paid unlock for unlimited on-device analysis and advanced trends. Clean, honest, and it fits Apple's rules.

---

*Estimates are planning-grade, not commitments; the Phase-0 spike will sharpen the Phase-2 numbers the most. Apple fee ($99/yr) and on-device-KataGo feasibility verified against current sources (July 2026).*
