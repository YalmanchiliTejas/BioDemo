# Testing ingestion, cross-file links and assistant memory by hand

Everything below uses synthetic files. Use an account with organization-wide access: Deliveries currently refuses site-restricted accounts.

## 1. Make the sample deliveries

```bash
cd backend
../.venv/bin/python scripts/make_sample_delivery.py ~/Desktop/sample-delivery-1
../.venv/bin/python scripts/make_sample_delivery.py ~/Desktop/sample-delivery-2 --month 2
```

Month 1 has two batch records (xlsx, csv), a deviation list, a lot master, a CoA PDF and an email. The deviation writes the batch as `B2024117`; the batch record writes `B-2024-117`. Month 2 reuses equipment `BR-07` and lot `L-8812` with batch `B-2024-131` and deviation `DEV-38`.

## 2. Ingestion

1. **Deliveries** → enter a CMO name (e.g. `Sample CMO`) → drop the `sample-delivery-1` folder.
2. Expect: the email is unpacked, every file is listed with what was done with it, and the run moves through Ingest → Classify → Map → Validate.
3. Confirm the column mapping when asked. The run reprocesses; check its timing: unchanged files are reused, not re-parsed.
4. Review values in **To check**, then open **Cross-file links**. Expect:
   - `B-2024-117 ↔ BR-07`, `B-2024-117 ↔ L-8812`, `DEV-31 ↔ BR-07`, `DEV-31 ↔ B2024117`: extracted (same source row).
   - `B-2024-117 ↔ B2024117`: extracted, "equal after ignoring case and separators".
5. Reject one link with a reason; it disappears from what the assistant follows. Upload `sample-delivery-2` under the same CMO name and check the rejection still applies to the same link.

## 3. The assistant building on context

1. **Rule**: in the assistant, write "From now on, always report DO in % and flag anything below 30%". Expect a proposed-rule card. Activate it under **Settings › Assistant rules**.
2. **Correction**: ask about DEV-31. Under the answer choose **Correct this** and write e.g. "Valve V-12 was inspected on 2 Nov and ruled out".
3. **New conversation**: ask "What could have caused DEV-31?". Under the answer, **Built on** should list 1 rule and 1 correction from an earlier conversation, and the answer should not propose V-12.
4. **Precedent**: close a case (open it from an answer → **Close this case…**, needs the QA role) with a root cause. In a new conversation ask about DEV-38: expect a similar-case lookup that finds the closed case, labelled "similar, not established as applicable".

## 4. Following the work

While the assistant runs, **Working · <current step>** shows the plan with completed steps and their durations; afterwards it folds into **How I worked this out**. These are sequential plan steps, not independent sub-agents.

## What to record

Time from drop to first reviewable value, how many questions the product asked you, links you rejected, whether **Built on** matched what you set up, and any answer that ignored a rule or correction.
