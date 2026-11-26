"""Research-only connector on the actual workspace assistant's ToolLoop path.

No production operator or physical model is replaced. The inherited conversation,
gateway, tools/observe loop, evidence checks and checkpoints execute normally.
"""
from copy import deepcopy
import json
from typing import Literal

from pydantic import BaseModel,ConfigDict,Field
from src.lifesci.evidence import EvidenceRef
from src.lifesci.process_engineering.conversation import EngineeringConversationService
from src.lifesci.process_engineering.tool_loop import ToolLoop
from .solver import configuration,native_rows,tool_summary


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)


class Simulate(Strict):
    """Execute unmodified LyoPRONTO knownRp in native units from authorized source evidence. Outputs are simulated front/bottom temperatures, flux, elapsed time and drying percent; no feasibility or optimum is supplied. Interpret pressure inputs in Torr; output pressure is mTorr. Fields not supplied by the source must not be invented."""
    source_id:str=Field(min_length=1,max_length=200)
    pressure_torr:float|None=Field(default=None,ge=.02,le=.30,description='Optional schedule pressure in Torr; needed when converting a reported non-native pressure. For recipe tasks choose an allowed candidate.')
    shelf_temperature_c:float|None=Field(default=None,ge=-50,le=25,description='Optional allowed recipe shelf setpoint, preserving source initial temperature and ramp.')


class Recipe(Strict):
    pressure_torr:float=Field(ge=.02,le=.30)
    shelf_temperature_c:float=Field(ge=-50,le=25)


class Assessment(Strict):
    """Save the requested reviewable LyoPRONTO assessment as a draft. Report native simulated values, not measured outcomes. For missing data or unsupported questions, record the reason and missing_inputs without inventing a recipe or completion. Include result_ids from the simulation tools you used. This does not grade or approve the answer."""
    source_id:str=Field(min_length=1,max_length=200)
    answer_status:Literal['completed','incomplete','needs_information','no_feasible_recipe','out_of_scope']
    completion_h:float|None=Field(default=None,ge=0)
    maximum_bottom_temperature_c:float|None=None
    peak_batch_sublimation_kg_h:float|None=Field(default=None,ge=0)
    thermal_margin_c:float|None=None
    capacity_margin_kg_h:float|None=None
    selected_recipe:Recipe|None=None
    missing_inputs:list[str]=Field(default_factory=list,max_length=20)
    result_ids:list[str]=Field(default_factory=list,max_length=12)
    rationale:str=Field(min_length=10,max_length=2500)


SCHEMAS={'lyopronto_simulate':Simulate,'lyopronto_record_result':Assessment}


class NativeConversation(EngineeringConversationService):
    @classmethod
    def attach(cls,existing):
        # Preserve the existing composition and registered operators. Only the
        # connector's two typed tools and prompt capability description are new.
        service=object.__new__(cls);service.__dict__.update(existing.__dict__)
        service.tool_loop=ToolLoop(service);service.solver_calls=0;service.assessment=None;service.native_results={}
        existing.p.engineering_conversations=service
        return service

    def _prompt(self,ctx,thread,sources):
        prompt=super()._prompt(ctx,thread,sources)
        prompt['operator_payload_schemas']={k:v for k,v in prompt['operator_payload_schemas'].items() if k.startswith('workspace_')}
        prompt['operator_payload_schemas'].update({k:v.model_json_schema() for k,v in SCHEMAS.items()})
        prompt['registered_models']={'status':'This research workspace exposes only the LyoPRONTO native connector; internal physical tools are not enabled.'}
        prompt['bioprocess_models_and_demo_cases']={'status':'Not enabled in this evaluation workspace.'}
        return prompt

    def _operator(self,name):
        if name not in SCHEMAS:return super()._operator(name)
        def run(ctx,raw):
            args=dict(raw);tid=args.pop('_turn_id');payload=SCHEMAS[name].model_validate(args)
            turn=self.p.store.read().require(ctx.tenant_id,'engineering_chat_turn',tid).state
            thread=self._thread(ctx,turn['conversation_id']).state
            self._active_turn(ctx,turn,self.p.store.read())
            if self.assessment is not None:raise ValueError('Assessment is already recorded; summarize it rather than revising the frozen draft')
            record=self.p.store.read().require(ctx.tenant_id,'evidence',payload.source_id)
            ref=EvidenceRef('evidence',record.id,record.revision,record.state['site_id'])
            self.p.identity.validate_refs(ctx,[ref.to_dict()])
            if record.state['site_id']!=thread['site_id']:raise PermissionError('Source is outside this conversation site')
            source=json.loads(self.p.evidence.original(ctx,record.id,revision=record.revision))
            if source.get('provenance',{}).get('commit') is None:raise ValueError('Not a versioned native LyoPRONTO source')
            if name=='lyopronto_simulate':
                if self.solver_calls>=12:raise ValueError('12-simulation episode limit reached')
                config=configuration(source,payload.pressure_torr,payload.shelf_temperature_c)
                self.solver_calls+=1
                result=native_rows(config)
                data={'type':'lyopronto_simulation','case_id':source['case_id'],
                    'native_configuration':config,'summary':tool_summary(result,config)}
                title='LyoPRONTO native primary-drying calculation'
            else:
                for rid in payload.result_ids:
                    if rid not in self.native_results:raise PermissionError('Result must belong to this episode and its current source')
                data={'type':'lyopronto_assessment','case_id':source['case_id'],
                      'assessment':payload.model_dump(exclude={'source_id'}),'review_state':'draft_requires_review'}
                title='LyoPRONTO assessment · draft, not manufacturing approval'
            with self.p.store.transaction(ctx.actor_id) as tx:
                self._active_turn(ctx,turn,tx)
                saved=self.workspace.save_result(ctx,thread,turn,{'data':data,'source_refs':[ref.to_dict()]},title)
                self._remember(ctx,turn,'assistant_workspace_result',saved,title)
            if name=='lyopronto_simulate':self.native_results[saved['id']]=deepcopy(data)
            else:self.assessment=deepcopy(data['assessment'])
            return {'status':'completed','output':saved,'issues':[]}
        return run
