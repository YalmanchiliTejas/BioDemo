"""Scoped visual review packets and immutable, hash-bound human receipts.

Receipts record attribution; they are not independent scientific qualification
and never turn OCR into an automatically verified source value.
"""
import hashlib
import io
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def review_packet(store, observation_id, *, as_of, scopes):
    rows=store.get_many([observation_id],as_of=as_of,scopes=scopes)
    if not rows:raise KeyError('Evidence is not visible at the requested scope and cutoff')
    row=rows[0]
    with store.connect() as con:
        source=dict(con.execute('SELECT * FROM sources WHERE id=?',(row['source_id'],)).fetchone())
    path=store.originals/source['sha256'][:2]/(source['sha256']+Path(source['path']).suffix.lower())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Original source hash changed')
    binding={'observation_id':row['id'],'source_sha256':source['sha256'],
             'source_ref':row['source_ref'],'extracted_value_sha256':fingerprint(row['value_text']),
             'access_scope':source['access_scope']}
    packet={**binding,'packet_sha256':fingerprint(binding),'extracted_text':row['value_text'],
            'extraction_method':row['extraction_method'],'source_format':source['format'],
            'review_status':'human_review_pending','scientific_qualification':'not_established',
            'instructions':'Compare the cited extracted text with the original page image or exact source line. OCR line numbers are extraction coordinates, not image bounding boxes.'}
    if source['format'] in {'.json','.txt','.md','.log'}:
        lines=path.read_text(encoding='utf-8',errors='replace').splitlines()
        match=re.fullmatch(r'line:([1-9][0-9]*)',str(row['source_ref'].get('span','')))
        if match and int(match[1])<=len(lines):packet['original_line']=lines[int(match[1])-1]
    directory=store.root/'source-reviews'/fingerprint(row['id'])
    receipts=[]
    for file in sorted(directory.glob('*.json')):
        receipt=json.loads(file.read_text())
        if receipt.get('packet_sha256')==packet['packet_sha256']:receipts.append(receipt)
    packet['human_reviews']=receipts
    if receipts:packet['review_status']='human_review_recorded'
    return packet


def page_image(store, observation_id, *, as_of, scopes):
    packet=review_packet(store,observation_id,as_of=as_of,scopes=scopes)
    if packet['source_format']!='.pdf':raise ValueError('Evidence is not a PDF citation')
    page=packet['source_ref'].get('page')
    if type(page) is not int or page<1:raise ValueError('Citation has no valid PDF page')
    # A visible citation does not authorize rendering future text on the same
    # physical page. Refuse the whole-page preview when any indexed page record
    # is unavailable at this cutoff, rather than inventing image redactions.
    with store.connect() as con:
        ids=[r[0] for r in con.execute("SELECT id FROM observations WHERE source_id=? AND json_extract(source_ref,'$.page')=?",(packet['source_ref']['source_id'],page))]
    if len(store.get_many(ids,as_of=as_of,scopes=scopes))!=len(ids):
        raise PermissionError('Page contains evidence unavailable at this scope or cutoff')
    digest=packet['source_sha256'];path=store.originals/digest[:2]/(digest+'.pdf')
    import pypdfium2
    document=pypdfium2.PdfDocument(str(path))
    try:
        if page>len(document):raise ValueError('Citation page is outside the document')
        selected=document[page-1]
        try:
            bitmap=selected.render(scale=2)
            try:
                output=io.BytesIO();bitmap.to_pil().save(output,format='PNG')
                return output.getvalue()
            finally:bitmap.close()
        finally:selected.close()
    finally:document.close()


def record_review(store, observation_id, *, as_of, scopes, packet_sha256, reviewer_id, decision, note):
    packet=review_packet(store,observation_id,as_of=as_of,scopes=scopes)
    if packet['packet_sha256']!=packet_sha256:raise ValueError('Review packet changed; inspect the current source before reviewing')
    if decision not in {'matches','does_not_match','unreadable'}:raise ValueError('Invalid source-review decision')
    if not isinstance(reviewer_id,str) or not reviewer_id.strip() or not isinstance(note,str) or not note.strip():
        raise ValueError('Reviewer identity and a review note are required')
    receipt={'review_id':uuid.uuid4().hex,'observation_id':observation_id,
             'packet_sha256':packet_sha256,'source_sha256':packet['source_sha256'],
             'source_ref':packet['source_ref'],'reviewer_id':reviewer_id,'decision':decision,'note':note,
             'recorded_at':datetime.now(timezone.utc).isoformat(),
             'review_type':'human_source_comparison','independent_scientific_qualification':False}
    target=store.root/'source-reviews'/fingerprint(observation_id)
    target.mkdir(parents=True,exist_ok=True)
    with (target/(receipt['review_id']+'.json')).open('x') as stream:json.dump(receipt,stream,indent=2)
    return receipt


def main():
    import argparse
    from .store import ManufacturingStore
    parser=argparse.ArgumentParser(description='Export exact source review material or record a human comparison')
    parser.add_argument('--store',type=Path,required=True);parser.add_argument('--scope',required=True)
    parser.add_argument('--as-of',required=True);parser.add_argument('--observation-id',required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--decision',choices=['matches','does_not_match','unreadable'])
    parser.add_argument('--packet-sha256');parser.add_argument('--reviewer-id');parser.add_argument('--note')
    args=parser.parse_args();store=ManufacturingStore(args.store)
    common={'as_of':args.as_of,'scopes':(args.scope,)}
    if args.decision:
        if not all((args.packet_sha256,args.reviewer_id,args.note)):parser.error('A decision requires packet-sha256, reviewer-id and note')
        result=record_review(store,args.observation_id,**common,packet_sha256=args.packet_sha256,
                             reviewer_id=args.reviewer_id,decision=args.decision,note=args.note)
    else:
        result=review_packet(store,args.observation_id,**common)
        if args.output:
            args.output.mkdir(parents=True,exist_ok=True)
            (args.output/'review-packet.json').write_text(json.dumps(result,indent=2)+'\n')
            if result['source_format']=='.pdf':(args.output/'original-page.png').write_bytes(page_image(store,args.observation_id,**common))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
