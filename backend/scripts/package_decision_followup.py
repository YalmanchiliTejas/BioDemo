"""Prepare factual local sharing artifacts after the frozen evaluation finishes."""
import argparse
from pathlib import Path
import json
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle

REPO = Path(__file__).resolve().parents[2]


def build(directory):
    data = json.loads((directory/'analysis.json').read_text())
    a,b = data['summaries']['A'],data['summaries']['B']
    n = len(data['cases'])
    effect = data['paired_contrasts']['correct']
    delta,lo,hi = effect['mean']*100,*[v*100 for v in effect['interval95']]
    supported = data['verdict'] == 'supports_the_prespecified_simulated_decision_hypothesis'
    verdict = ('Model access improved constrained decisions in this simulated cohort.' if supported else
               'This cohort did not establish the prespecified constrained-decision benefit.')
    counts = f"{a['correct']}/{n} correct decisions with GLM alone versus {b['correct']}/{n} with GLM plus the mechanistic model"
    model_count = data['summaries']['model_only']['correct']
    boundary = (f'The conventional model-only selector also scored {model_count}/{n}; added agent value over that selector was not demonstrated. '
                'These are synthetic process outcomes using a shared mechanistic equation family, including deliberately mismatched receiving conditions. '
                'They do not establish real manufacturing performance, product quality, or avoided losses. '
                'The earlier real CHO forecast comparison did not show benefit from the selected model.')
    linkedin = f'''# LinkedIn draft - based on completed measurements

Does giving a manufacturing agent a mechanistic model actually improve its decisions?

We tested the same Modal GLM-5.3 agent with and without an imperfect process model, using identical evidence and a feasibility-first decision policy.

In {n} prespecified simulated receiving-process scenarios, we recorded {counts}.

Constraint-violating operating decisions: {a['violating_operation']} without the model, {b['violating_operation']} with it. The paired difference in correct-decision rate was {delta:+.1f} percentage points (descriptive 95% interval: {lo:+.1f} to {hi:+.1f}).

{verdict}

{boundary}

We're reporting the mixed evidence and retained failures because predictive accuracy and better engineering decisions need to be demonstrated separately.

Attach decision-results.png. This is a local draft, not a published post. Do not describe the inventory metric as released yield or generalize this cohort to industrial safety.
'''
    (directory/'linkedin-draft.md').write_text(linkedin)
    email = f'''Subject: Sievance - measured GLM-5.3 and mechanistic-model decision results

Hello [Name],

I'm sharing the latest evaluation of Sievance's hypothesis that adding mechanistic tools can improve an agent's manufacturing decisions.

We ran the same Modal GLM-5.3 agent with and without the tool on {n} prespecified simulated receiving-process scenarios. Both arms received identical evidence and the same constraint-first decision policy. The endpoint responses identify GLM-5.3; model requests, submissions, failures and outcome replays are retained.

We measured {counts}. Constraint-violating operating decisions were {a['violating_operation']} and {b['violating_operation']}, respectively. The paired correct-decision difference was {delta:+.1f} percentage points (descriptive 95% interval {lo:+.1f} to {hi:+.1f}). {verdict}

{boundary}

Attached is a short results summary. The complete protocol, model-only comparator, case-level results and audit receipts are available locally with the evaluation package.

Best,
Tejas

Attachment: sievance-evaluation-20261101.pdf
Status: draft only; no message sent. Replace [Name] before sending.
'''
    (directory/'email-draft.txt').write_text(email)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleCompact',fontName='Helvetica-Bold',fontSize=18,leading=21,spaceAfter=7,textColor=colors.HexColor('#0f172a')))
    styles.add(ParagraphStyle(name='SmallBody',fontName='Helvetica',fontSize=9,leading=12,spaceAfter=6,textColor=colors.HexColor('#334155')))
    styles.add(ParagraphStyle(name='Result',fontName='Helvetica-Bold',fontSize=11,leading=14,spaceAfter=7,textColor=colors.HexColor('#0369a1')))
    story=[Paragraph('Sievance | Agents + mechanistic models',styles['TitleCompact']),
           Paragraph('Exploratory evaluation | November 1, 2026 | Actual Modal GLM-5.3 endpoint',styles['SmallBody']),
           Paragraph(escape(verdict),styles['Result']),
           Paragraph(f'{n} independent simulated scenarios; {n*2} planned agent sessions. '
                     f'{a["completed"]+b["completed"]} completed submissions. The same evidence and decision policy were used in both arms.',styles['SmallBody']),
           Image(str(directory/'decision-results.png'),width=528,height=225.28),Spacer(1,5)]
    rows=[['Measure','Agent alone','Agent + model'],
          ['Correct constrained decisions',f'{a["correct"]}/{n}',f'{b["correct"]}/{n}'],
          ['Constraint-violating operations',str(a['violating_operation']),str(b['violating_operation'])],
          ['Correct / unnecessary stops',f'{a["correct_stop"]} / {a["unnecessary_stop"]}',f'{b["correct_stop"]} / {b["unnecessary_stop"]}'],
          ['Mean simulated inventory (kg)',f'{a["mean_mass_kg"]:.2f}',f'{b["mean_mass_kg"]:.2f}'],
          ['Mean constraint-feasible inventory (kg)',f'{a["mean_feasible_mass_kg"]:.2f}',f'{b["mean_feasible_mass_kg"]:.2f}']]
    table=Table(rows,colWidths=[304,112,112],hAlign='LEFT')
    table.setStyle(TableStyle([('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e0f2fe')),
                              ('FONTNAME',(0,1),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),9),
                              ('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),
                              ('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#94a3b8')),
                              ('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#e2e8f0'))]))
    story += [table,Spacer(1,10),
              Paragraph(f'Paired correct-decision difference: <b>{delta:+.1f} percentage points</b>; '
                        f'descriptive 95% interval [{lo:+.1f}, {hi:+.1f}]. Scenarios, not model calls, are the independent units.',styles['SmallBody']),
              Paragraph('<b>Interpretation:</b> '+escape(boundary),styles['SmallBody']),
              Paragraph('Correct means feasible operation when a permitted plan is feasible, or stopping otherwise. '
                        'Failed submissions count incorrect. Constraint-feasible inventory is zero for violations/stops; '
                        'it is not measured product quality or released yield.',styles['SmallBody']),
              Paragraph('A prior cost pilot was stopped before comparative analysis and is excluded. New scenario seeds and analysis '
                        'were frozen before inference. A conventional model-only comparator and every case are in the full report.',styles['SmallBody']),
              Paragraph('Protocol SHA-256: '+escape(data['integrity']['protocol_sha256'][:24])+'... | '
                        f'{data["budget"]["admitted_requests"]} forwarded model requests. '
                        'Costs are token-rate estimates/reservations, not a verified invoice.',styles['SmallBody'])]
    pdf=REPO/'output/pdf/sievance-evaluation-20261101.pdf'
    pdf.parent.mkdir(parents=True,exist_ok=True)
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8)
        canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.drawString(42,23,'Research-stage evidence. No Purdue affiliation, endorsement, or manufacturing validation claimed.')
        canvas.drawRightString(570,23,str(doc.page))
    SimpleDocTemplate(str(pdf),pagesize=letter,rightMargin=42,leftMargin=42,topMargin=35,bottomMargin=35).build(story,onFirstPage=footer,onLaterPages=footer)
    print(json.dumps({'pdf':str(pdf),'linkedin_draft':str(directory/'linkedin-draft.md'),'email_draft':str(directory/'email-draft.txt')}))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    build(a.report.resolve())
