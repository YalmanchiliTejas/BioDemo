# Benchmark comparison

CHO tests authentic experimental bioprocess measurements, especially source discovery and reconstruction. Its fixed-format baseline reconstructed 24 cultivations from the original workbooks; 10,986,364/10,996,791 comparable values (99.905%) met the documented tolerance against publisher alignment. Causal relevance and process explanations remain unscored.

Fresenius tests investigation of simulated manufacturing-quality scenarios constrained by publicly documented FDA findings. The conventional parser recovered all visible record IDs at five replay cutoffs on the earlier v1 export format. A one-pass model retrieved all visible incident action/OOS lab records and made time-valid citations on v1. Three first-signal repeats cited [2, 2, 5] records, with pairwise Jaccard overlaps [1.0, 0.4, 0.4]. The current v2.1 source package adds scanned lab reports, discrete process charts, and a local-time lab export; its five historical snapshots passed data validation, but no agent score exists for v2.1.

Neither benchmark alone proves performance on confidential commercial CDMO records or prevention of real-world manufacturing failures. The benefit of the full RLM architecture over simpler baselines remains unmeasured because its raw-source adapter is not yet connected.
