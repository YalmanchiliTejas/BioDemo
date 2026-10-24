> Historical implementation note. The current rebuild is documented in [ethos-rebuild.md](ethos-rebuild.md). Product decisions are governed by `Main_Culture_andETHOS.md`.

# Professional landing and workspace refresh

The existing interface combined dark landscape imagery, blue data surfaces, amber decorative accents, very small text and multiple generations of CSS overrides. The landing page used abstract headlines and repeated conversion links; the workspace devoted a large banner to decorative imagery.

The revised direction is a restrained technical product for biomanufacturing teams. Design variance 4, motion intensity 2, density 4 on marketing and 6 in the workspace. It uses the existing native CSS, Manrope typography, Remix icons and Radix interaction foundation. No new component framework or dependency was introduced.

White and pale neutral surfaces share a blue action accent (#315e94). Amber remains a semantic finding indicator. Controls use 6px radii and panels use 8px radii. The landing page keeps existing section anchors and navigation labels. The workspace keeps routes, scenario state, investigation, assistant, search, review and source-system behavior.

Landing changes include direct product copy, a compact split hero, an evidence walkthrough, keyboard-accessible source tabs and a fresh screenshot of the actual workspace. Workspace changes include neutral navigation, a compact heading, clearer finding and metric hierarchy, readable source navigation and simplified panel styling. The user-supplied landscape remains the landing hero and workspace banner, with ambient animation, pause controls and reduced-motion support.

Validation: production TypeScript/Vite build passed. The existing workspace browser check passed at desktop, tablet and mobile sizes, covering navigation history, investigation, assistant, search, review dialog, all four source workspaces, source tabs and overflow. Browser page errors: zero. Desktop and mobile screenshots were visually reviewed. Vite reports large chunks in the broader application.
