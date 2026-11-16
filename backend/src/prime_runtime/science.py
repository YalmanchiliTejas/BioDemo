"""Deterministic scientific tools over a sealed package, without Platform authority."""
from copy import deepcopy
import hashlib
import io
import json
import math
import zipfile

from src.lifesci.ids import content_hash
from src.lifesci.process_engineering.catalog import ModelCatalog
from src.lifesci.process_engineering.contracts import predict, contract, value_at

CONTRACTS = {
    'scientific_model_catalog': {'required': [], 'description': 'Registered models and source-supplied configurations; sufficiency is not qualification.'},
    'scientific_model_run': {'required': ['configuration_id'], 'properties': {'configuration_id': {'type':'string'}},
        'description': 'Execute one frozen source configuration; withhold absent inputs or incompatible observations.'},
}


def pin_package_availability(path, as_of):
    """Admitted snapshot existed at its host cutoff, before later executor transport."""
    from datetime import datetime
    import os
    at=datetime.fromisoformat(as_of.replace('Z','+00:00'))
    if at.tzinfo is None:
        raise ValueError('snapshot cutoff requires timezone')
    os.utime(path,(at.timestamp(),at.timestamp()))


class FrozenScience:
    def __init__(self, documents):
        self.models = ModelCatalog(None)
        self.configurations = {}
        self.results = {}
        for ref, document in documents:
            if not isinstance(document, dict):
                # Ordinary arrays/scalars remain general evidence, not scientific declarations.
                continue
            entries = document.get('scientific_models', [])
            if not isinstance(entries,list) or len(entries)>32:
                raise ValueError('scientific_models must be a list of at most 32 identified configurations')
            # Existing model-library context: use its immutable original configuration.
            if 'configuration_request' in document:
                request=document['configuration_request']
                if not isinstance(request,dict):
                    raise ValueError('Scientific configuration_request must be an object')
                entries=[*entries,dict(id=ref['id'],model_id=request.get('model_id'),config=request.get('config'),
                              assumptions=request.get('assumptions',[]),uncertainty=['No calibrated prediction interval'])]
            if not isinstance(entries,list) or len(entries)>32:
                raise ValueError('scientific_models must be a list of at most 32 identified configurations')
            for item in entries:
                if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not item['id'].strip():
                    raise ValueError('Each scientific_models configuration requires a nonempty string id')
                ident=item['id']
                if len(ident)>200:
                    raise ValueError('Scientific configuration id exceeds 200 characters')
                if ident in self.configurations:
                    raise ValueError('ambiguous scientific configuration ID: '+ident)
                self.configurations[ident]={**deepcopy(item),'source_refs':[deepcopy(ref)]}

    @classmethod
    def from_documents(cls, documents):
        return cls(documents)

    @classmethod
    def from_package(cls, package):
        stream = io.BytesIO(package) if isinstance(package, bytes) else package
        with zipfile.ZipFile(stream) as archive:
            if 'snapshot-manifest.json' not in archive.namelist():
                return cls([])  # legacy packages remain usable, but cannot invent configurations
            raw = archive.read('snapshot-manifest.json')
            if len(raw) > 2*1024*1024:
                raise ValueError('snapshot manifest exceeds bound')
            manifest = json.loads(raw)
            if manifest.get('version') != 1 or len(manifest['items']) > 2048:
                raise ValueError('invalid snapshot manifest')
            documents = []
            for item in manifest['items']:
                content = archive.read(item['path'])
                if hashlib.sha256(content).hexdigest() != item['sha256']:
                    raise ValueError('frozen source digest mismatch')
                if item['path'].endswith('.json') and item.get('revision'):
                    documents.append(({k:item[k] for k in ('kind','id','revision','site_id') if k in item}, json.loads(content)))
            return cls(documents)

    def tools(self):
        # Function attributes let the normal bridge advertise contracts without custom RPC.
        def catalog(as_of=None, scopes=None): return self.catalog()
        def run(configuration_id, as_of=None, scopes=None): return self.run(configuration_id)
        catalog.input_contract = CONTRACTS['scientific_model_catalog']
        run.input_contract = CONTRACTS['scientific_model_run']
        return {'scientific_model_catalog': catalog, 'scientific_model_run': run}

    def catalog(self):
        return {'models': self.models.snapshot(), 'configurations': [
            {'id':key, 'model_id':c.get('model_id'), 'source_refs':c['source_refs']} for key,c in self.configurations.items()],
            'advisory':True, 'evidence_ids':[]}

    def run(self, configuration_id):
        if configuration_id in self.results:
            return deepcopy(self.results[configuration_id])
        if configuration_id not in self.configurations:
            raise ValueError('configuration must name a supplied frozen source')
        c = self.configurations[configuration_id]
        result = {'configuration_id':configuration_id, 'source_refs':c['source_refs'], 'advisory':True,
                  'status':'withheld', 'missing_inputs':[], 'issues':[], 'evidence_ids':[],
                  'assumptions':[], 'uncertainty':[]}
        try:
            if not isinstance(c.get('model_id'),str) or not c['model_id'].strip():
                raise ValueError('Scientific configuration model_id must be a nonempty string')
            adapter = self.models.get(c['model_id'])
            result['model'] = {**adapter.describe(), 'analysis_contract':contract(adapter)}
            config = c.get('config')
            if not isinstance(config,dict):
                raise ValueError('Scientific configuration config must be an object')
            # A named frozen contract reuses registered solver code with every relevant
            # source input explicitly supplied. Other legacy scenario defaults stay closed.
            explicit_inputs=getattr(adapter,'frozen_required_inputs',None)
            if explicit_inputs:
                required=list(explicit_inputs)
                runner=adapter.run_frozen
            elif hasattr(adapter,'inputs'):
                required=[*adapter.inputs,'evidence_classification','source_refs']
                runner=adapter.run
            else:
                raise ValueError('This characterization adapter requires its dedicated source/configuration workflow; automatic scenario defaults are withheld')
            for path in required:
                try:
                    if value_at(config,path) is None:
                        result['missing_inputs'].append(path)
                except (KeyError,TypeError,IndexError):
                    result['missing_inputs'].append(path)
            for field in ('assumptions','uncertainty'):
                if field not in c or not isinstance(c[field],list) or any(not isinstance(v,str) for v in c[field]):
                    result['missing_inputs'].append(field)
                else:
                    result[field]=deepcopy(c[field])
            if result['missing_inputs']:
                raise ValueError('Explicit relevant parameters, assumptions and uncertainty required; scientific defaults are withheld')
            observations = c.get('observations', [])
            if not isinstance(observations,list) or len(observations)>500:
                raise ValueError('Observations must be a list of at most 500 source observation objects')
            for index,row in enumerate(observations):
                if not isinstance(row,dict):
                    raise ValueError(f'Observation {index} must be an object with observable, coordinate, value and unit')
                if not isinstance(row.get('observable'),str) or not isinstance(row.get('unit'),str):
                    raise ValueError(f'Observation {index} observable and unit must be strings')
                if any(isinstance(row.get(k),bool) or not isinstance(row.get(k),(int,float)) or not math.isfinite(row[k]) for k in ('value','coordinate')):
                    raise ValueError(f'Observation {index} value and coordinate require finite numbers')
            predictions, output = predict(adapter, config, observations,runner=runner)
            result.update(status='completed', output=output, config_hash=content_hash(config),
                comparison=[{**row, 'observed':row['value'], 'predicted':float(predicted),
                             'residual':row['value']-float(predicted), 'source_refs':c['source_refs']}
                            for row,predicted in zip(observations,predictions)],
                interpretation='Conditional calculation; does not establish causality or process qualification')
        except (ValueError, KeyError, TypeError, ArithmeticError, RuntimeError) as exc:
            result['issues'].append(str(exc))
        self.results[configuration_id] = result
        return deepcopy(result)

    def attach(self, report, store, scope, as_of):
        """Preserve the exact original file coordinate of each actually cited row."""
        from src.workflows.report_verification import collect_citations
        citations = collect_citations(report)
        mapping = {}
        # get_many handles ordinary and columnar evidence IDs and respects scope/time.
        for row in store.get_many(citations, as_of=as_of, scopes=(scope,)):
            source = row.get('source_ref') or {}
            if isinstance(source,str): source=json.loads(source)
            mapping[row['id']] = {'path':source.get('path'), 'source_ref':source}
        return {**report, 'snapshot_citation_map':mapping, 'scientific_model_runs':list(self.results.values())}
