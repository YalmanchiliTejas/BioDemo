"""Execute notebook Python cells sequentially; explicitly not a Jupyter-kernel run."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import os
import time


def verify(output):
    root=Path(__file__).resolve().parents[2];out=Path(output);out.mkdir(parents=True,exist_ok=False)
    os.environ.setdefault('MPLCONFIGDIR','/private/tmp/sievance-pharma-mpl');os.environ['MPLBACKEND']='Agg'
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    manifest={'execution_method':'Sequential compile/exec of each notebook Python cell in one namespace per notebook, not a Jupyter kernel',
        'classification':'synthetic_development_and_numerical_verification_not_customer_validation','notebooks':[]}
    for path in sorted((root/'docs/model-library').glob('*.ipynb')):
        namespace={'__name__':'__main__'};nb=json.loads(path.read_text());cells=[]
        for i,cell in enumerate(nb['cells']):
            if cell['cell_type']!='code':continue
            code=''.join(cell['source']);stream=io.StringIO();start=time.monotonic()
            with contextlib.redirect_stdout(stream):exec(compile(code,str(path)+':cell'+str(i),'exec'),namespace)
            text=stream.getvalue();cell['execution_count']=len(cells)+1
            cell['outputs']=[{'output_type':'stream','name':'stdout','text':text.splitlines(keepends=True)}] if text else []
            cells.append({'cell_index':i,'sha256':hashlib.sha256(code.encode()).hexdigest(),'status':'completed','seconds':time.monotonic()-start,'stdout':text})
        figures=[]
        for number in plt.get_fignums():
            dest=out/(path.stem+'-'+str(number)+'.png');plt.figure(number).savefig(dest,dpi=120,bbox_inches='tight');figures.append(dest.name)
        plt.close('all')
        # Preserve evaluated notebook separately; source notebooks stay portable.
        (out/path.name).write_text(json.dumps(nb,indent=1)+'\n')
        manifest['notebooks'].append({'path':str(path.relative_to(root)),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'code_cells':cells,'figures':figures})
    (out/'verification.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return {'notebooks':len(manifest['notebooks']),'executed_code_cells':sum(len(n['code_cells']) for n in manifest['notebooks']),'output':str(out)}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);a=parser.parse_args();print(json.dumps(verify(a.output)))
