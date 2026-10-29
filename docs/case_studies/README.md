# Manufacturing intelligence experiments

For the new thesis about **agents with versus without executable physical models**, see the [pilot implementation](../../backend/benchmarks/physics_value/README.md), [generated simulation audit](../../backend/results/physics-value/pilot-20261027-final/report.md), and [paired-agent execution and publication record](physics-value-publication.md). The restricted-tool comparison records actual model decisions and synthetic outcomes. It does not establish general manufacturing validity or human-workflow savings. The historical results below remain separate.

Start with [measured results](results.md), then [limitations and remaining work](limitations.md).
This implementation does **not** establish that the product delivers autonomous,
scalable causal investigation: the benchmark deliberately exposes failures.

- [Architecture audit](architecture_audit.md): actual existing files, baseline commands and gaps.
- [Data provenance](data_provenance.md): FDA findings, fictional evidence boundary, real IndPenSim data and licenses.
- [Benchmark methodology](benchmark_methodology.md): isolation, scoring, comparison methods and reproducibility.
- [Simulator feasibility](indpensim_feasibility.md): installation, controls, numerical failures and measured paired tests.
- [Implementation and execution](implementation.md): file responsibilities, generation, investigation, evaluation and demo commands.
- [DagsHub storage and cold execution](storage.md): large remote artifacts, temporary downloads, verification and recovery.
- [Run receipts](results/): compact measured summaries, an inspectable complete baseline trace and actual failed agent/simulator receipts. Large corpora remain outside Git.

The current UI is `/case-studies`. Its data is exported from executed run receipts,
not fixtures or simulated agent responses. A fresh checkout shows an explicit
missing-results state until the documented export command runs.
