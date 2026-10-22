# Landing page and workspace hub

Run `cd ui && npm run dev`.

| Route | What |
| --- | --- |
| `/` | Landing page |
| `/app` | The workspace hub: one place to open every application, with the Work queue (A) and Batch record (B) inside it and one Assistant beside whatever is open (C) |
| `/app?view=historian` · `lims` · `mes` · `qms` · `queue` · `record` | Deep links into the hub; add `&instant` to skip the detection sequence |
| `/benchmarks` | The previous benchmark app (was `/`). `/?tab=cases` and `/?tab=ingestion` still open it |
| `/concepts` | The three-concept study |

## Decisions

- **Start with C, centralised.** The hub's sidebar lists the customer's own applications (PlantView Historian, LabWare LIMS, Syncade MES, QualityTrack QMS). Each opens unchanged inside the sheet. The Assistant panel reads what is open: it explains the historian tag you are on and can draw the reference band on it; in LIMS it explains the out-of-range results; in QMS it explains its drafted fields, which you check and save with QMS's own button.
- **A and B live inside the hub.** Work queue and Batch F-2408 sit under Workspace in the same sidebar, so findings, the batch record and the applications are one click apart.
- **Type:** Manrope for everything, IBM Plex Mono only for tags and sample IDs. The simulated host apps keep a Windows system face on purpose, so they look like the software engineers already have.
- **Colour, after cardiatec.ai:** navy `#09155A` as ink and primary, white sheets, a navy-tinted grey frame, and teal `#66ACA3` (darkened to `#2A7067` for text contrast) for the batch's data and the Assistant. The landing page uses navy fields and white sections, with large display type at weight 200, the way the reference does.

## Checks (taste-skill)

- Lint: landing **0 FAIL, 0 WARN**; hub and lab **0 FAIL, 0 WARN**.
- Inspector at 1440, 768 and 390 px: landing **0 FAIL**, with 1 warning: no video, because the only bioreactor clips in the open collections are research-paper supplements, not honest footage of this subject. Hub Home, Work queue, Batch record and MES are clean. QMS is **0 FAIL, 0 WARN** too. Historian and LIMS each have 1 warning: three typefaces, because the host keeps its own face.
- The concept walkthrough (`node frontend/scripts/check_lab.cjs`) still passes. The production build succeeds.

## Pictures (landing page; credits are in its footer)

All four are from Wikimedia Commons and show the subject's world, not the customer's plant.

- "Bioreactor in operation", Habin Zhang, CC BY-SA 4.0
- "BTEC Bioreactors", RickLawless, CC BY 3.0
- "Bioreactor 1", Luis Fernando Flores LAB, CC BY-SA 4.0
- "Bioreactor Akureyri", Fribbi, public domain

Files are in `ui/public/os/assets/`, with their licences in `credits.json`.

## To replace before real use

- The landing page's contact address is a placeholder: `hello@example.com`.
- All plant data comes from `frontend/src/lab/scenario.ts`.
