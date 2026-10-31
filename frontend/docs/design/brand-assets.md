# Transparent Sievance brand assets

The header logo and favicon use transparent artwork rather than the white canvas in the supplied `public/brand/sievance.png`. The original reference remains available.

Outputs:

- `public/brand/symbol-transparent.png`: RGBA symbol, 1278 × 1230; transparent corners verified.
- `public/brand/favicon-transparent.svg`: self-contained square favicon using the transparent PNG with a centered viewport.
- `public/brand/symbol.svg`: compatibility copy for existing icon references.

`BrandMark.tsx` uses a tighter SVG viewport for the header symbol. The wordmark remains text. The layout metadata uses the new favicon filename to avoid reusing the previous favicon cache. Old image-cropping and blend-mode rules were removed.

Generated with the built-in image editor, transparency enabled, referencing the supplied logo. Final prompt:

> Use case: background-extraction. Edit the supplied Sievance brand artwork. Extract ONLY the teal folded S ribbon symbol on the left (remove the SIEVANCE text and all white background). Preserve the existing symbol's exact silhouette, folds, teal/mint gradient colors and proportions; do not redesign or add anything. Produce a tightly framed isolated symbol with a small transparent safety margin, true transparent alpha background, clean antialiased edges with no white halo, border, matte, shadow or checkerboard. This asset will be used on light and dark website backgrounds and as a favicon.

Verified by browser rendering on light and dark surfaces at header size and 16, 32 and 64 pixel favicon sizes. TypeScript checks pass. A frontend deployment is required to publish the changes.
