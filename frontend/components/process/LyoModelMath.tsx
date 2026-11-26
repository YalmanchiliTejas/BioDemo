import type { ReactNode } from 'react';
import { ChevronDown, Download } from 'lucide-react';
import { eyebrow } from './LyoCharts';

const base='/case-study-results/freeze-drying/';
function Equation({label,children}:{label:string;children:ReactNode}) {
  return <div role="math" aria-label={label} className="my-4 overflow-x-auto rounded-lg border border-border-hairline bg-canvas px-4 py-5 font-serif text-lg leading-9 text-text-primary sm:text-xl"><div className="min-w-fit whitespace-nowrap">{children}</div></div>;
}
function Expand({title,children}:{title:string;children:ReactNode}) {
  return <details className="group rounded-xl border border-border-hairline bg-surface"><summary className="flex cursor-pointer list-none items-center justify-between gap-4 p-5 text-sm font-semibold [&::-webkit-details-marker]:hidden">{title}<ChevronDown size={18} className="shrink-0 transition-transform group-open:rotate-180"/></summary><div className="border-t border-border-hairline p-5 text-sm leading-7 text-text-secondary sm:p-7">{children}</div></details>;
}

export function LyoModelMath() {
  return <section id="model-math" aria-labelledby="math-heading" className="mt-14 scroll-mt-6">
    <p className={eyebrow}>Inside the mechanistic model</p>
    <h2 id="math-heading" className="mt-3 font-display text-3xl font-medium tracking-tight">Heat in. Ice out. Every population counts.</h2>
    <p className="mt-3 max-w-2xl text-sm leading-6 text-text-secondary">Each vial population has its own temperature and remaining ice. They share a prescribed chamber pressure. This is a transient, lumped model of primary drying.</p>
    <div className="my-7 grid gap-3 sm:grid-cols-3" aria-label="Model structure">
      {[
        ['01 · Characterization','Vial geometry, heat transfer, product resistance, thermal storage and equipment limits.'],
        ['02 · Population balances','Integrate temperature and ice mass for each weighted vial population.'],
        ['03 · Reviewable outputs','Last-to-dry time, hottest active vial, capacity margins and applicability cutoff.'],
      ].map(([title,text])=><div key={title} className="border-l-2 border-brand-teal/40 bg-surface py-4 pl-4 pr-3"><h3 className="text-xs font-semibold text-brand-teal">{title}</h3><p className="mt-2 text-xs leading-5 text-text-secondary">{text}</p></div>)}
    </div>
    <div className="space-y-3">
      <Expand title="01 — The coupled heat and mass balances">
        <p>For population <i>i</i>, let <i>mᵢ</i> be ice mass per vial and <i>Tᵢ</i> its lumped thermal-node temperature. The population weight <i>wᵢ</i> is the fraction of vials it represents, with ∑wᵢ = 1.</p>
        <Equation label="Ice balance: d m i over d t equals minus sublimation mass rate i">dmᵢ/dt = −ṁᵢ</Equation>
        <Equation label="Heat balance: effective heat capacity times temperature derivative equals heat input minus sublimation latent heat">(Cᵥ + mᵢ cₚ,ice) dTᵢ/dt = Gᵢ (Tₛ − Tᵢ) − ṁᵢ ΔHₛᵤᵦ</Equation>
        <Equation label="Forward sublimation mass flow equals product area times positive vapor pressure difference divided by resistance">ṁᵢ = Aₚ max[pᵢ꜀ₑ(Tᵢ) − P꜀, 0] / Rₚ,ᵢ</Equation>
        <p>Heat entering the vial either warms the thermal node or supplies latent heat for sublimation. Forward sublimation is allowed; deposition is not modeled. The declared constants are cₚ,ice = 2,100 J/(kg·K), ΔHₛᵤᵦ = 2.84 × 10⁶ J/kg and ice conductivity kᵢ꜀ₑ = 2.4 W/(m·K).</p>
        <Equation label="Effective thermal conductance includes vial transfer and remaining frozen layer conduction">Gᵢ = Aᵥ Kᵥ,ᵢ / [1 + Aᵥ Kᵥ,ᵢ (H − Lᵈ,ᵢ) / (Aₚ kᵢ꜀ₑ)]</Equation>
        <p><i>Cᵥ</i> is declared vial heat capacity; <i>Aₚ</i> and <i>Aᵥ</i> are product and outer-vial areas; <i>H</i> is fill height; <i>Lᵈ</i> is dried-layer thickness. Temperatures may be reported in °C because the balance uses temperature differences. Vapor pressure uses absolute temperature.</p>
        <div className="mt-5 border-l-2 border-amber-600 pl-4 text-xs leading-6">The thermal node is not a resolved spatial temperature field or a bottom-vial sensor. Dry-cake heat storage, secondary drying, desorption, potency and residual moisture are outside this model.</div>
      </Expand>
      <Expand title="02 — Heat transfer, resistance and vapor pressure">
        <Equation label="Heat transfer coefficient is a pressure-dependent relation times a fitted global scale and fixed population factor">Kᵥ,ᵢ(P꜀) = sᵏᵥ αᵢ [a + bP꜀ / (1 + cP꜀)]</Equation>
        <Equation label="Dried layer resistance is a thickness-dependent relation times a fitted global scale and fixed population factor">Rₚ,ᵢ(Lᵈ,ᵢ) = sʳᵖ βᵢ [R₀ + R₁ Lᵈ,ᵢ / (1 + R₂ Lᵈ,ᵢ)]</Equation>
        <Equation label="Dried layer thickness from remaining ice mass">Lᵈ,ᵢ = H − mᵢ / (ρᵢ꜀ₑ ε Aₚ)</Equation>
        <p>The fixed population factors αᵢ and βᵢ represent differing heat transfer and product resistance. The fitted global scales sᵏᵥ and sʳᵖ multiply every population. Population weights and factors are supplied characterization assumptions; this experiment does not learn a validated population distribution. The pressure-dependent coefficient Kᵥ has units W/(m²·K); Rₚ uses the implementation’s SI form m/s, equivalent to Pa·m²·s/kg. Ice density is 918 kg/m³ and ε is porosity.</p>
        <Equation label="Murphy and Koop ice vapor-pressure correlation, natural logarithm of pressure in pascals">ln pᵢ꜀ₑ = 9.550426 − 5723.265/Tᴷ + 3.53068 ln Tᴷ − 0.00728332 Tᴷ</Equation>
        <p>Tᴷ = T + 273.15. The implementation restricts the correlation to 110 &lt; Tᴷ ≤ 273.16 K and stops an active population at melting. This correlation does not make the rest of the model experimentally validated.</p>
      </Expand>
      <Expand title="03 — Drying events, equipment limits and when to stop trusting the forecast">
        <p>A BDF integrator advances the balances, restarting at shelf-schedule changes and individual ice-exhaustion events. After mᵢ reaches zero, that population stops sublimating but can continue warming. It is excluded from the primary-drying temperature-risk calculation.</p>
        <Equation label="Batch completion is the last population drying time; critical margin uses only active populations">tₑₙd = maxᵢ t(mᵢ = 0) &nbsp;;&nbsp; ΔTₘₐᵣgᵢₙ = T꜀ᵣᵢₜ − max<sub>i: mᵢ &gt; 0</sub> Tᵢ</Equation>
        <Equation label="Batch sublimation rate in kilograms per hour">ṁᵦₐₜ꜀ₕ = 3600 N ∑ᵢ wᵢ ṁᵢ</Equation>
        <Equation label="Accumulated condenser ice mass">M꜀ₒₙd = N ∑ᵢ wᵢ (mᵢ,₀ − mᵢ)</Equation>
        <p><i>N</i> is the vial count. The model checks vapor-flow capacity and accumulated condenser ice capacity. Once either limit is exceeded, the prescribed chamber pressure is no longer assured. Continued curves are diagnostic extrapolations; completion is withheld as a valid forecast. The tool also gates predictions on measured pressure mismatch greater than 0.5 Pa.</p>
        <p className="mt-3">The solver uses relative tolerance 10⁻⁶, mass absolute tolerance 10⁻¹² kg, temperature tolerance 10⁻⁷°C and maximum step 300 s. Capacity crossings use solver events; temperature extrema use solver/output samples, not certified continuous extrema. Numerical precision is not physical accuracy.</p>
      </Expand>
      <Expand title="04 — Calibration, what the agent receives and what stays hidden">
        <p><strong className="text-text-primary">Forecast task:</strong> early receiving observations from 0–6 h. The model tool fits effective Kᵥ and Rₚ multipliers against weighted thermal-node temperature and remaining-ice measurements. <strong className="text-text-primary">Pretransfer task:</strong> characterization only, without receiving observations or fitting.</p>
        <Equation label="Standardized temperature and mass residuals">rᵀⱼ = (T̂ⱼ − Tⱼ) / 0.12°C &nbsp;;&nbsp; rᵐⱼ = (m̂ⱼ − mⱼ) / 10⁻⁵ kg</Equation>
        <Equation label="Robust least squares objective for the two scale parameters">min<sub>0.6 ≤ sᵏᵥ, sʳᵖ ≤ 1.8</sub> ∑ⱼ [√(1 + rⱼ²) − 1]</Equation>
        <p>Both fitted parameters start at 1; the fitting routine permits 16 function evaluations. This soft-L1 objective reduces sensitivity to large residuals. Its normalized RMS is dimensionless and combines both channels; it must not be interpreted as a temperature uncertainty or a validated confidence interval.</p>
        <div className="mt-5 grid gap-5 sm:grid-cols-2"><div><h4 className="font-semibold text-text-primary">Shared by both agents</h4><p className="mt-2 text-xs leading-6">Identical characterization, available observations, permitted actions, numerical Python, model identity and within-protocol budgets. Agent A can construct its own simulator. Agent C additionally gets the executable model and its calibration outputs.</p></div><div><h4 className="font-semibold text-text-primary">Held out from agent tools</h4><p className="mt-2 text-xs leading-6">Future observations, receiving-process perturbations, reference outcomes and evaluator files. Independent restricted sessions prevent cross-arm memory reuse. This is a controlled SDK/tool comparison, not an evaluation of every production-agent capability.</p></div></div>
        <p className="mt-5 text-xs leading-6">The half-hourly remaining-ice channel is synthetic instrumentation, not an assumption that ordinary manufacturing historians provide it. Identifiability, sensor bias and unmeasured receiving shifts remain limitations.</p>
      </Expand>
      <Expand title="05 — How recommendations and prediction errors are compared">
        <div className="grid gap-5 sm:grid-cols-2"><div><h4 className="font-semibold text-text-primary">Commit, then score</h4><p className="mt-2">Agents submit a KEEP completion forecast, thermal/capacity warnings, one action, rationale and uncertainty before seeing hidden outcomes. Permitted actions are KEEP, shelf −30°C, −26°C, −22°C, or request characterization. Forecast-task changes begin at 6 h; pretransfer changes begin at zero.</p></div><div><h4 className="font-semibold text-text-primary">Keep every outcome</h4><p className="mt-2">A feasible operating choice completes without a reference constraint violation. Prior excursions cannot be erased by a later action. Unsafe choices, characterization, timeouts, malformed submissions and other failures remain separate. Characterization is not automatically a bad decision.</p></div></div>
        <Equation label="Mean absolute completion-time error on the intersection of valid numerical predictions">MAE = (1 / |S|) ∑<sub>j ∈ S</sub> |t̂ⱼ − tⱼ|</Equation>
        <p>Here, <i>S</i> contains only cases with a valid reference completion and a numerical prediction from both agents. The chart uses the same cases for both error values and reports prediction coverage separately. Every planned session remains in the operating-choice denominator. Tasks stay separate for accuracy because pretransfer has less information.</p>
        <p className="mt-3">Reference completion and subsequent thermal outcomes are censored after capacity overload. The primary KEEP schedules have zero reference capacity violations, so this cohort cannot estimate capacity-warning sensitivity. The separate capacity challenge is documented in the research archive; it is not pooled into these agent graphs.</p>
        <p className="mt-3">There is one session per case/task/arm. The six follow-up cases were selected by the smallest opaque ID in each family, then reused under a prospectively frozen change to budget, wall time and final-turn submission policy. This is a post-hoc motivated sensitivity analysis, not independent confirmation.</p>
        <a className="mt-5 inline-flex items-center gap-2 text-xs font-semibold text-brand-teal hover:underline" href={base+'study.py'} download><Download size={14}/>Inspect the exact study and scoring code</a>
      </Expand>
    </div>
  </section>;
}
