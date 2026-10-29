# Tester guide: CMO deliveries

Open the site and choose **Try the live demo** for the guided CHO walkthrough ([details](CHO_DEMO.md)), or go to **Deliveries** to use your own files. If asked, enter the access code you were given.

## What to try (about 10 minutes)

1. Type your name at the top right once. It is recorded on every decision.
2. Type the CMO name and drop the files exactly as you received them (PDF,
   Excel, CSV or ZIP). Checking starts immediately.
3. **Check how we read these files**: each column is shown with its proposed
   meaning. Only unclear columns ask you to choose. Click **Looks right, apply**.
   Values that match the original and pass every check are verified.
4. **To check**: one line per item. *Accept* or *Noted* take one click;
   rejecting values or dismissing missing information asks for a short reason.
   *View source* shows the original page or spreadsheet row.
5. Click **Export CSV**. The batch × parameter table and filters below cover
   everything in the delivery; *Details* lists files, checks and history.
6. Send a second delivery from the same CMO: confirmed formats and ignored
   boilerplate are reused, so it should need fewer or no decisions.

## What the system guarantees, and what it does not

For every delivery, *Details → Checks on this delivery* confirms that:

- every non-empty cell and text line is a value, a batch/time identifier,
  excluded by a rule you confirmed, or listed for your decision;
- values are accepted without a person only from a confirmed mapping, matching
  the original file byte-for-byte, with no failed check;
- every human acceptance, correction and rejection has a name and reason;
- no two accepted values disagree for the same batch, time and parameter;
- "Verified" means zero pending values, open issues and unaccounted content;
- the audit chain verifies.

It does **not** prove a CMO document is itself correct or complete, and it
does not extract every value from arbitrary PDFs: unfamiliar prose (for example
CoA result tables) is listed for you to read unless hosted extraction is
enabled. Reviewer receipts are not regulated electronic signatures.

## Please tell us

- Time from receiving the files to an export you would use, and what you did
  outside the tool.
- Any value you found that the system accepted wrongly, or anything present in
  the files that you could not find in the tool.
- Which decisions felt repetitive or unnecessary.
