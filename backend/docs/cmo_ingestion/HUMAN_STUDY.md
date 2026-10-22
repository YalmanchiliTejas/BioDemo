# Human work study protocol

Primary endpoint: total observed human minutes from receipt of a raw package to
an accepted, analysis-ready export, including layout confirmation, correction,
missing-record follow-up, and external spreadsheet/PDF inspection. Processing
duration and model cost are separate measures.

No completed human study has been performed for the checked-in results.
Automated calibration is labeled `study_protocol`; browser automation accrues
no human minutes. Never substitute processing duration for human work.

1. Recruit at least three bioprocess engineers or manufacturing data reviewers.
   Assign pseudonymous reviewer IDs and retain consent and training records
   locally. Use disjoint calibration packages to learn the workflow.
2. Randomize held-out package/configuration order across participants. Include
   a manual cleanup baseline using the same raw files and required deliverable.
   Do not show answer keys, expected defect counts, or the other condition's
   output. Separate repeated packages sufficiently to reduce recall effects.
3. Start an observer timer at package receipt. Log setup, template review,
   measurement review/correction, and missing-information follow-up separately.
   Include work in external tools. Record breaks and blocked waiting explicitly.
4. In the UI, select a measurement or mapping. Focused, visible screens with
   recent input send server-timed activity heartbeats at 10-second intervals.
   Gaps over 15 seconds are not credited; activity ends after 30 seconds without
   input. This is a conservative **partial screen-time** measure. Observer logs
   are required for total work and work outside the UI. Browser/heartbeat errors
   are study data-quality issues, not zero-time success.
5. Stop only after all issues have documented dispositions, source verification
   is complete, and the verified read-only interface accepts the package.
   Dispositions that waive missing data must be labeled incomplete for scientific
   use in the observer's study record. Record abandoned packages and censoring.
6. Score accepted outputs independently after participants finish. Report per
   package/participant minutes, corrections, omissions, wrong acceptances,
   completion rate, and paired manual-baseline differences with uncertainty.
   Report setup separately for unseen layouts and recurring work for returning
   layouts. Do not claim savings before a controlled baseline is measured.

The ≤15 minute target is not met merely because an automated run finishes in
seconds. No assertion of superiority to Invert follows from these benchmarks.
