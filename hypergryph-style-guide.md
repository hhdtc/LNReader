# Hypergryph-Inspired Web Style Guide

This guide summarizes observable design patterns from https://ak.hypergryph.com/ and https://endfield.hypergryph.com/ to help you build a similar **visual system** without copying proprietary assets. Use this as a **directional reference**.

## 1) Visual Direction
- **Mood:** cinematic, high-contrast, sci‑fi with industrial/futuristic motifs.
- **Primary surface:** deep black or near‑black backgrounds with bright highlights.
- **Primary storytelling:** full‑bleed key visuals, large character art, and cinematic stills.
- **Information density:** content sections are visually separated with large imagery and generous spacing.

## 2) Layout & Structure
- **Hero/KV:** full‑viewport or near‑full height key visual with minimal overlay text.
- **Section rhythm:** alternating blocks for **story/lore**, **characters**, **media**, and **news**.
- **Galleries:** grid or carousel‑like sections for character portraits or event stills.
- **Timeline or cards:** recurring content (events/news) shown as stacked cards or time‑based lists.
- **Navigation:** compact top bar or overlay with icon‑plus‑label entries.

**Recommended layout grid**
- 12‑column desktop grid; large left/right margins.
- Mobile layout collapses into single column with carousel interactions.

## 3) Typography
- **Base font:** clean sans‑serif; use a sci‑fi or geometric family for headings.
- **Heading style:** uppercase/condensed feel; sharp tracking for sci‑fi tone.
- **Copy style:** small to medium body text, high line‑height for readability on dark backgrounds.

**Observed fonts (from computed styles)**

**Arknights (ak.hypergryph.com)**
- `Oswald-Medium`
- `Bender-Bold`, `Bender-Regular`
- `SourceHanSans-Regular`, `SourceHanSans-Medium`, `SourceHanSans-Bold`
- `SDK_Sans-Regular`, `SDK_Sans-Medium`
- Fallbacks: `Arial`, `sans-serif`

**Endfield (endfield.hypergryph.com)**
- `Novecentosanswide-DemiBold`, `Novecentosanswide-Medium`
- `Gilroy-Medium` (also `Gilroy-Light`, `Gilroy-ExtraBold` present)
- `Roboto-Regular`, `Roboto-Black`
- `SpaceGrotesk`
- `ProtestStrike-Regular`
- `SansRegular`, `SansMedium`, `SansBold` (site-specific alias)
- `SDK_Sans-Regular`, `SDK_Sans-Medium`
- Fallbacks: `sans-serif`

**Monster Siren (monster-siren.hypergryph.com/info)**
- `Geometos`, `Bender`, `Sans-Regular`, `Sans-Bold`
- `SourceHanSansCN-Regular`, `SourceHanSansCN-Bold`
- Fallback stack includes `Microsoft YaHei`, `Segoe UI`, `Roboto`, `Helvetica Neue`, `Arial`, `sans-serif`

**Suggested type scale**
- Display: 48–72px
- H1: 36–48px
- H2: 28–32px
- H3: 20–24px
- Body: 14–16px
- Caption: 12–13px

## 4) Color System
- **Base:** #0B0B0B to #111111 (background)
- **Primary text:** #FFFFFF
- **Secondary text:** #A0A0A0
- **Accents:** use 1–2 vivid colors (e.g., cyan/teal or orange/red) sparingly for CTAs.

**Contrast guidance**
- Aim for WCAG AA on body text.
- Keep accent color usage <10% of visible UI.

## 5) Imagery & Media
- **Key visuals:** large, high‑detail illustrations or 3D renders.
- **Overlays:** subtle gradients on top of imagery to improve text readability.
- **Framing:** centered composition with UI overlays anchored to edges.
- **Media:** embed trailers and gameplay clips with prominent poster frames.

## 6) Motion & Interaction
- **Transitions:** slow, cinematic fades (300–600ms), parallax on scroll.
- **Hover states:** slight glow, subtle scale‑up, or thin outline.
- **Carousel behavior:** snapping slides with light inertia.

**Observed motion patterns (from JS bundles)**
- **WebGL/Canvas effects:** particle fields, logo/shape particles, and shader-based distortions; updated via `requestAnimationFrame` loops.
- **Cursor interaction:** interactive parallax and mouse‑tracked deformation for certain visuals.
- **Section transitions:** full‑page section switching with width/overlay wipes, eased curves (`easeOutQuad`, `easeInOutQuad`) and 300–1000ms durations.
- **Carousels:** `Swiper` is used with draggable scrollbars, free‑mode, autoplay, and snap transitions.
- **Video handling:** HLS streaming for `.m3u8` sources; autoplay/pause tied to section visibility.
- **Micro‑animations:** timeline‑based text slides, staggered delays, and opacity fades for titles/subtitles.

**Motion implementation notes (summarized)**
- **Fade in/out**: opacity easing with short delays, often combined with `translateY(10–30px)`.
- **Text reveal**: split or stacked lines move from `translateY(100%)` to `0%` with stagger.
- **Section swap**: mask/overlay width animates from `0% → 100% → 0%` during navigation.
- **Interactive background**: mouse/touch position influences shader uniforms or particle target.

**Sample code patterns (safe, generic)**

_1) Intersection-based fade/slide in_
```js
const io = new IntersectionObserver((entries) => {
  entries.forEach((e) => {
    if (e.isIntersecting) {
      e.target.animate(
        [
          { opacity: 0, transform: 'translateY(24px)' },
          { opacity: 1, transform: 'translateY(0px)' },
        ],
        { duration: 450, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)', fill: 'forwards' }
      );
      io.unobserve(e.target);
    }
  });
});
document.querySelectorAll('[data-reveal]').forEach((el) => io.observe(el));
```

_2) Staggered text lines (slide up)_
```js
const lines = document.querySelectorAll('.headline-line');
lines.forEach((line, i) => {
  line.animate(
    [
      { transform: 'translateY(100%)', opacity: 0 },
      { transform: 'translateY(0%)', opacity: 1 },
    ],
    { duration: 600, delay: i * 120, easing: 'cubic-bezier(0.16, 1, 0.3, 1)', fill: 'forwards' }
  );
});
```

_3) Section wipe transition (mask width)_
```js
function runSectionWipe(maskEl, duration = 700) {
  maskEl.animate(
    [
      { width: '0%' },
      { width: '100%' },
      { width: '0%' },
    ],
    { duration, easing: 'ease-in-out' }
  );
}
```

_4) Simple RAF-driven parallax_
```js
let targetX = 0, targetY = 0, x = 0, y = 0;
window.addEventListener('mousemove', (e) => {
  targetX = (e.clientX / window.innerWidth - 0.5) * 20;
  targetY = (e.clientY / window.innerHeight - 0.5) * 20;
});
function tick() {
  x += (targetX - x) * 0.08;
  y += (targetY - y) * 0.08;
  document.documentElement.style.setProperty('--parallax-x', `${x}px`);
  document.documentElement.style.setProperty('--parallax-y', `${y}px`);
  requestAnimationFrame(tick);
}
tick();
```

_5) Tab switch with glow underline + content fade/slide_
```html
<div class="tabset" role="tablist">
  <button class="tab is-active" role="tab" aria-selected="true" data-tab="overview">Overview</button>
  <button class="tab" role="tab" aria-selected="false" data-tab="projects">Projects</button>
  <span class="tab-underline" aria-hidden="true"></span>
</div>
<div class="tab-panels">
  <section class="tab-panel is-active" data-panel="overview">...</section>
  <section class="tab-panel" data-panel="projects">...</section>
</div>
```
```css
.tabset { position: relative; display: inline-flex; gap: 20px; }
.tab { color: var(--text-300); text-transform: uppercase; letter-spacing: .18em; }
.tab.is-active { color: var(--text-100); }
.tab-underline {
  position: absolute; left: 0; bottom: -6px; height: 2px; width: 0;
  background: var(--accent-1); box-shadow: var(--glow);
  transition: transform 500ms cubic-bezier(.2,.8,.2,1), width 500ms cubic-bezier(.2,.8,.2,1);
}
.tab-panel { opacity: 0; transform: translateY(16px); display: none; }
.tab-panel.is-active { display: block; animation: tabIn 500ms cubic-bezier(.2,.8,.2,1) forwards; }
@keyframes tabIn { to { opacity: 1; transform: translateY(0); } }
```
```js
const tabs = document.querySelectorAll('.tab');
const panels = document.querySelectorAll('.tab-panel');
const underline = document.querySelector('.tab-underline');

function moveUnderline(tab) {
  const rect = tab.getBoundingClientRect();
  const parentRect = tab.parentElement.getBoundingClientRect();
  underline.style.width = `${rect.width}px`;
  underline.style.transform = `translateX(${rect.left - parentRect.left}px)`;
}

tabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    tabs.forEach((t) => {
      t.classList.remove('is-active');
      t.setAttribute('aria-selected', 'false');
    });
    tab.classList.add('is-active');
    tab.setAttribute('aria-selected', 'true');

    panels.forEach((p) => p.classList.remove('is-active'));
    const panel = document.querySelector(`[data-panel="${tab.dataset.tab}"]`);
    panel.classList.add('is-active');
    moveUnderline(tab);
  });
});

moveUnderline(document.querySelector('.tab.is-active'));
```

## 7) Components
- **Navigation menu:** icon + label, minimal text, hover glow.
- **Header bar (Endfield‑style):** primary tabs on left, compact utility cluster (user/sound/payments), and a high‑contrast **Download** CTA with platform icons.
- **CTA buttons:** solid or outlined; strong contrast, crisp corners.
- **Cards:** transparent or semi‑transparent panel with thin border.
- **Tabs/filters:** thin underline or glowing marker; underline slides to active tab; panel swaps via fade + short slide.
- **News list:** date + category + thumbnail.

**Header bar sample (structure only)**
```html
<header class="site-header">
  <nav class="primary-tabs">
    <a class="is-active">首页</a>
    <a>干员情报</a>
    <a>世界观资料</a>
    <a>影像资料</a>
    <a>玩法介绍</a>
    <a>公告</a>
  </nav>
  <div class="header-utility">
    <span>用户</span>
    <span>声音:打开</span>
    <span>支付中心</span>
  </div>
  <div class="header-download">
    <button>下载</button>
    <div class="platforms">
      <span>App Store</span>
      <span>PS5</span>
      <span>Android</span>
      <span>PC</span>
      <span>TapTap</span>
    </div>
  </div>
</header>
```

**Monster Siren patterns**
- **Breaking news ticker:** repeated marquee line for announcements.
- **Artist updates list:** date + tag (e.g., artist updates) with large image tiles.
- **Massive track list:** long, ordered list with album/collection title at top.
- **Sectioned nav:** simple top links (About / Music / Updates / Contact) and login/logout state.

## 8) Spacing & Density
- **Vertical spacing:** 64–120px between sections.
- **Card spacing:** 16–24px internal padding.
- **Hero padding:** 48–96px from edges.

**Monster Siren spacing**
- **Long‑scroll layout:** dense vertical rhythm, large media blocks between text lists.
- **List readability:** generous line spacing for very long track lists.

## 9) Accessibility
- Provide text alternatives for all key visuals.
- Ensure focus states are visible on dark backgrounds.
- Avoid small, low‑contrast text over busy images—use overlays.

## 10) Example Design Tokens
```css
:root {
  --bg-900: #0b0b0b;
  --bg-800: #111111;
  --text-100: #ffffff;
  --text-300: #a0a0a0;
  --accent-1: #00d1ff;
  --accent-2: #ff5a3d;
  --border-weak: rgba(255,255,255,0.12);
  --glow: 0 0 24px rgba(0, 209, 255, 0.35);
}
```

## 11) Section Blueprint
1. **Hero/KV** (full viewport)
2. **News/Announcements** (latest content)
3. **Character/Operator** (carousel + detail panel)
4. **Lore/World** (story cards)
5. **Media** (trailers, gameplay)
6. **Gallery** (image grid)
7. **Footer** (legal, social, links)

**Monster Siren page flow (observed)**
1. **Breaking news ticker**
2. **Featured image stack**
3. **Artist updates list** (date + tag)
4. **Music catalog list** (long, numbered track list)
5. **Footer / legal**

---

If you want, tell me your target framework (e.g., React, Vue, Next.js) and I can generate a starter layout and tokens file.