"""Standalone vector figures from measured artifacts using ReportLab charts."""
import hashlib
import json
from pathlib import Path
from reportlab.graphics.shapes import Drawing,String
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics import renderSVG,renderPDF
from reportlab.lib import colors

ROOT=Path(__file__).resolve().parents[1]


def export(drawing,name,destination):
    renderSVG.drawToFile(drawing,str(destination/(name+'.svg')))
    renderPDF.drawToFile(drawing,str(destination/(name+'.pdf')))


def main():
    source=ROOT/'BENCHMARK_RESULTS.json';results=json.loads(source.read_text())
    destination=ROOT/'results/publication';destination.mkdir(parents=True,exist_ok=True)
    example=results.get('investigation_example')
    if example and example.get('current_source_sha256_matches_frozen') and example.get('trajectories'):
        drawing=Drawing(850,510)
        drawing.add(String(55,475,'CHO reactor divergence: an observation to investigate',fontName='Helvetica-Bold',fontSize=22,fillColor=colors.HexColor('#193e33')))
        plot=LinePlot();plot.x=65;plot.y=150;plot.width=720;plot.height=265
        plot.data=[[(p['time_hours'],p['value']) for p in c['points']] for c in example['trajectories']]
        plot.xValueAxis.valueMin=0;plot.yValueAxis.valueMin=0;plot.yValueAxis.valueMax=100
        palette=['#238267','#ba8d4b']
        for i,c in enumerate(example['trajectories']):
            plot.lines[i].strokeColor=colors.HexColor(palette[i]);plot.lines[i].strokeWidth=2
            drawing.add(String(70+230*i,435,c['sheet'].split('_',1)[0],fontSize=12,fillColor=colors.HexColor(palette[i])))
        drawing.add(plot)
        drawing.add(String(360,115,'Source time (h)',fontSize=11))
        drawing.add(String(65,420,'Viability mean (%)',fontSize=10))
        for i,v in enumerate(example['values']):
            ref=v['source'];drawing.add(String(65,85-i*17,f"{v['value']:.2f}%: {ref['path']} / {ref['sheet']} / {ref['cell']}",fontSize=10))
        drawing.add(String(65,34,'Authentic laboratory data. Lines connect sampled points; event onset and cause are not established.',fontSize=9))
        drawing.add(String(65,19,'Recorded example; full report remains incomplete under the newer audit. Independent scientific review pending.',fontSize=9))
        export(drawing,'cho-investigation-example',destination)
    drawing=Drawing(850,510)
    drawing.add(String(55,475,'Manufacturing OS: every recorded execution counts',fontName='Helvetica-Bold',fontSize=22,fillColor=colors.HexColor('#193e33')))
    chart=HorizontalBarChart();chart.x=160;chart.y=165;chart.width=620;chart.height=250
    selected=[[r for r in results['runs'] if r['benchmark_id']==bid and r['mode']=='full_rlm' and r['attempted']] for bid in ('cho','fresenius')]
    chart.data=[[sum(r['recorded_execution_status']==status for r in cohort) for cohort in selected] for status in ('completed','incomplete','failed')]
    chart.categoryAxis.categoryNames=['CHO','Fresenius synthetic'];chart.valueAxis.valueMin=0;chart.valueAxis.valueStep=1
    for i,(label,color) in enumerate(zip(['Completed','Incomplete','Failed'],['#238267','#ba8d4b','#b4675b'])):
        chart.bars[i].fillColor=colors.HexColor(color)
        drawing.add(String(160+i*195,435,label,fontSize=12,fillColor=colors.HexColor(color)))
    drawing.add(chart)
    drawing.add(String(365,130,'Recorded attempts (count)',fontSize=11))
    drawing.add(String(60,90,'Historical versions and infrastructure failures included. Completion is not scientific qualification.',fontSize=10))
    drawing.add(String(60,70,f"{len(results['unfinalized_records'])} trace-only record(s): method/execution unknown; excluded from known-method denominators.",fontSize=10))
    drawing.add(String(60,45,'Fresenius: synthetic manufacturing reconstruction informed by publicly available FDA-related materials.',fontSize=9))
    drawing.add(String(60,28,'No internal company data, endorsement or production improvement demonstrated. All publication gates pending.',fontSize=9))
    export(drawing,'execution-reliability',destination)
    (destination/'figure-provenance.json').write_text(json.dumps({'results_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'source':'BENCHMARK_RESULTS.json','figure_data':'Exact source trajectories and all recorded full_rlm statuses; no interpolated or invented benchmark values.'},indent=2)+'\n')
    print(json.dumps({'figures':sorted(p.name for p in destination.glob('*.svg'))}))


if __name__=='__main__':main()
