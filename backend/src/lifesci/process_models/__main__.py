"""python -m src.lifesci.process_models list|run|examples|fit|compare|sensitivity"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import platform

import numpy as np
import scipy

from .registry import models, get, existing_model_inventory
from .examples import examples
from .analysis import fit_parameter, compare, parameter_scenarios


def load(path):
    return json.loads(Path(path).read_text())


def example_campaign(directory):
    out=Path(directory)
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()): raise ValueError("choose an empty output directory to preserve prior receipts")
    cases=examples()
    (out/"inputs").mkdir()
    results={}
    for model_id,config in cases.items():
        result=get(model_id).run(config)
        results[model_id]=result
        (out/"inputs"/(model_id+".json")).write_text(json.dumps(config,indent=2)+"\n")
        (out/(model_id+".json")).write_text(json.dumps({"inputs":config,"result":result},indent=2,allow_nan=False)+"\n")
    # Check the same legacy calculation code, not a duplicate fermentation/lyo model.
    from ..chemical_reactor.demo import example as batch_example
    from ..chemical_reactor.model import simulate
    from ..fermentation.model import calculate
    from ..fermentation.data import project
    from ..lyophilization.model import simulate as dry
    from ..lyophilization.case import source_config
    legacy={"chemical_batch":simulate(batch_example()),"fermentation_sulfolobus":calculate(project("sulfolobus")),
            "fermentation_pichia":calculate(project("pichia")),"primary_drying":dry(source_config())}
    (out/"existing-model-smoke.json").write_text(json.dumps(legacy,indent=2,allow_nan=False)+"\n")
    # Executed shared-calibration and transfer examples, not mocked API shapes.
    mid="powder.two_bin_mill"
    observations=[{"coordinate":float(t),"value":float(.8*np.exp(-.002*t)),"source_ref":"synthetic-analytic-milling"}
                  for t in np.arange(0.,1801.,90.)]
    guess=deepcopy(cases[mid]); guess["breakage_rate_s_inv"]=.001
    request={"model_id":mid,"config":guess,"parameter":"breakage_rate_s_inv","bounds":[.0001,.005],
             "observable":"coarse_mass_fraction","observations":observations,"training_until":900.}
    (out/"calibration-request.json").write_text(json.dumps(request,indent=2)+"\n")
    fitted=fit_parameter(**request)
    receiver=deepcopy(cases["isolation.cake_filter"]); receiver["filter_area_m2"]*=.8
    comparison_request={"model_id":"isolation.cake_filter","donor":cases["isolation.cake_filter"],
                        "receiver":receiver,"metrics":["completion_time_s"]}
    (out/"comparison-request.json").write_text(json.dumps(comparison_request,indent=2)+"\n")
    comparison=compare(**comparison_request)
    from .flowsheets import purification_train
    train=purification_train(crystal=cases["crystal.cooling_moments"],filtration=cases["isolation.cake_filter"],
                            wash=cases["isolation.cake_wash"],dryer=cases["isolation.cake_dryer"],
                            retained_liquid_m3=.00005,liquid_density_kg_m3=800.)
    analyses={"calibration":fitted,"site_comparison":comparison,"purification_train":train}
    (out/"shared-analysis-examples.json").write_text(json.dumps(analyses,indent=2,allow_nan=False)+"\n")
    lines=["# Pharmaceutical model library baseline run","","All new example parameters are authored synthetic assumptions. No customer validation.","",
           "| Model | Type | Execution |","|---|---|---|"]
    for model_id,result in results.items():
        lines.append(f"| {model_id} | {result['model_kind']} | {result['status']} |")
    lines += ["", "Shared analyses executed: synthetic milling calibration, filter area comparison and crystallisation–filtration–washing–drying handoffs.",
              "", f"Purification-train status: {train['status']}; API accounting error: {train['api_inventory_accounting_error_kg']:.3g} kg.",
              "No cross-unit compaction-to-dissolution relation or chromatography breakthrough is claimed."]
    (out/"report.md").write_text("\n".join(lines)+"\n")
    manifest={"classification":"numerical_examples_not_experimental_validation","new_models_executed":len(results),
              "model_ids":list(results),"existing_local_smokes_executed":list(legacy),
              "external_bioprocess_workers":"not_executed_environment_not_provisioned",
              "environment":{"python":platform.python_version(),"numpy":np.__version__,"scipy":scipy.__version__},
              "existing_models":existing_model_inventory(),"catalogue":[m.describe() for m in models().values()]}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2,allow_nan=False)+"\n")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(4,4,figsize=(16,12))
    for ax,(model_id,result) in zip(axes.flat,results.items()):
        model=get(model_id)
        curve=result.get("trajectory")
        if curve:
            key=next(k for k in model.outputs if k in curve[0])
            ax.plot([r[model.axis] for r in curve],[r[key] for r in curve])
            ax.set_xlabel(model.axis)
            ax.set_ylabel(f"{key}\n({model.outputs[key]})",fontsize=7)
        else:
            ax.text(.5,.5,"Scalar equipment/equilibrium screen",ha="center",va="center",wrap=True,fontsize=8)
            ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(model_id,fontsize=9)
        ax.grid(alpha=.2)
    fig.suptitle("16 reduced models · synthetic learning inputs · no customer validation")
    fig.tight_layout(rect=(0,0,1,.97))
    fig.savefig(out/"library_overview.png",dpi=130)
    plt.close(fig)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest="command",required=True)
    subs.add_parser("list")
    run=subs.add_parser("run"); run.add_argument("model_id"); run.add_argument("config"); run.add_argument("--output",required=True)
    ex=subs.add_parser("examples"); ex.add_argument("--output",required=True)
    for name in ("fit","compare","sensitivity"):
        sub=subs.add_parser(name); sub.add_argument("request"); sub.add_argument("--output",required=True)
    args=parser.parse_args()
    if args.command=="list":
        from ..process_engineering.catalog import ModelCatalog
        print(json.dumps({"models":ModelCatalog(None).snapshot(),"existing":existing_model_inventory()},indent=2))
        return
    if args.command=="examples":
        manifest=example_campaign(args.output)
        print(json.dumps({"models_executed":manifest["new_models_executed"],"output":args.output}))
        return
    if Path(args.output).exists(): raise ValueError("output exists; select a new result path")
    if args.command=="run": result=get(args.model_id).run(load(args.config))
    else:
        request=load(args.request)
        result={"fit":fit_parameter,"compare":compare,"sensitivity":parameter_scenarios}[args.command](**request)
    Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(args.output)


if __name__=="__main__":
    main()
