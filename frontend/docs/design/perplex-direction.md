> Historical implementation note. The current rebuild is documented in [ethos-rebuild.md](ethos-rebuild.md). Product decisions are governed by `Main_Culture_andETHOS.md`.

# Perplex visual direction

## Reference and scope

The supplied `perplex-Image 30.png` is the source of the new landing-page hero and workspace overview banner. The original is preserved. Web JPEGs are copied into `frontend/public/os/assets/perplex-landscape.jpg` (2048 px) and `perplex-landscape-mobile.jpg` (1120 px). Their colors and composition are unchanged; resizing/encoding reduces delivery size from roughly 10 MB to 577 KB on desktop or 118 KB on phones.

This is an evolution of the existing React application. Routes, source-system navigation, demo fixtures, evidence/review actions, keyboard navigation, and the existing icon/font families remain in use. Native CSS and IntersectionObserver handle the motion without additional dependencies. Optimized JPEGs also deliver the existing generated laboratory visual and real workspace screenshot; the PNG originals remain available.

## Audit and decisions

The previous landing page used generated cellular imagery, powder-blue surfaces, a scroll listener and a continuously zooming hero. The workspace had white chrome, blue accents and little interaction feedback. The new reference instead has charcoal stone, cold daylight and amber reflections.

The landing page uses one dark charcoal theme with ice-blue type and controls. The workspace uses charcoal navigation, ice-tinted chrome, and solid light data surfaces. Amber is reserved for findings and restrained reflected light. There is no amber replacement for blue actions.

The design-taste skill applies to the marketing page, not the data views. Landing settings: design variance 6, motion intensity 6, density 3. Workspace motion stays around 2 to support reading and investigation. Radius rule: landing CTA pills, 12 px panels; workspace 8 px controls and 12 px cards. Layers: background 0, scrim 1, content 2, landing nav 3; shared application dialogs retain their established layers.

## Motion

- Slow image drift, cool shafts and warm reflected light reinforce the image's depth and lighting.
- Hero text arrives in reading order. IntersectionObserver reveals sections once. The laboratory image uses a progressive CSS view timeline where supported, with static fallback.
- Workspace views enter with 6 px displacement over 220 ms. Assistant entry and button feedback stay short. Data and numbers do not continuously animate.
- Animation loops change transform/opacity only. No per-frame React updates, scroll listener, animated blur, or added WebGL runtime.
- A visible control pauses the background at its current frame. The preference survives reloads and navigation. Backgrounds also pause offscreen and in hidden tabs.
- Live reduced-motion changes remove depth/zoom/movement while keeping 150 ms fades and focus feedback. Reduced-transparency users get solid navigation/control backgrounds.

## Skills applied

- [Design taste](../../../skills/design-taste-frontend/SKILL.md): audit, palette, hierarchy and marketing-page composition.
- [Animation performance](../../../skills/60fps-animation/SKILL.md): transform/opacity animation and runtime profiling.
- [Accessible animation](../../../skills/accessible-animation/SKILL.md): live preference handling, pause control and tiered fallbacks.
- [Micro-interactions](../../../skills/micro-interaction/SKILL.md): view, button and assistant feedback.
- [Glassmorphism](../../../skills/glassmorphism/SKILL.md): limited frosted landing navigation with solid fallback. Data panels remain opaque.

## Verification

`check_workspace.cjs` covers investigation actions, history, assistant, review, search, source-preview keyboard navigation and responsive layout. `check_atmosphere.cjs` covers pause/resume persistence, live reduced-motion changes, offscreen pausing, image loading, CTA placement at 320/390/768/1024/1440 px, and a steady-state Chrome rendering trace. Screenshots and Lighthouse results are local review artifacts under `/private/tmp/`.


Browser verification passed with no page errors across the workspace flows and all four source views. The background steady-state trace recorded 0 Layout and 0 Paint events over the sampled 1.5-second loop. That is a bounded Chrome trace, not a guarantee for every device. The production Lighthouse audit, screenshots, and follow-up measurements are kept as local review artifacts.

Final local production Lighthouse mobile run: accessibility 100, performance 89, LCP 3.7 s, CLS 0.011, total blocking time 10 ms. The initial production run was 90/100 with a larger image payload; these single-run performance scores vary and do not establish an improvement or a field Core Web Vitals pass. The current LCP remains above the 2.5 s target. The active supporting imagery now uses JPEGs instead of the original large PNGs.
