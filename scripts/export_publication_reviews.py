"""Export review material without rewriting recorded attempts or inventing reviews."""
import json
from benchmarks.common.case_protocol import ROOT,stable_hash,save,digest
from benchmarks.common.case_runner import blinded_packet,review_template


def main():
    destination=ROOT/'results/publication/review-packets';destination.mkdir(parents=True,exist_ok=True)
    index=[]
    for path in sorted((ROOT/'results/evaluation').glob('*/run.json')):
        run=json.loads(path.read_text())
        if not run.get('output'):continue
        packet=blinded_packet(run)
        identifier=stable_hash({'output':run['output_sha256'],'policy':run['case']['quality_policy_sha256']})[:24]
        packet['packet_id']=identifier
        packet_path=save(destination/(identifier+'.json'),packet)
        index.append({'packet_id':identifier,'packet_sha256':digest(packet_path),'run_id':run['run_id'],
                      'output_sha256':run['output_sha256'],'policy_sha256':run['case']['quality_policy_sha256']})
        save(destination/(identifier+'-review-template.json'),review_template(run))
    save(destination/'EVALUATOR_ONLY_INDEX.json',{'bindings':index,
        'instructions':'Keep index and run/method labels from blinded reviewers. Collect independent reviews and disclosure of inferred method; obtain policy approval and adjudicate disagreements. No reviews have been filled by this exporter.'})
    print(json.dumps({'review_packets':len(index),'directory':str(destination)}))


if __name__=='__main__':main()
