"""Optional DeepEval judges over actual conversations and observed tools/context."""
import os
from . import unavailable


def conversations(snapshot,observations):
    from deepeval.test_case import ConversationalTestCase, Turn, ToolCall
    cases=[]
    for session in snapshot['sessions']:
        turns=[]
        for row in snapshot['turns']:
            if row['conversation_id']!=session['id']:continue
            # Background envelopes are events, not simulated user utterances.
            if row.get('origin')!='background':
                turns.append(Turn(role='user',content=row['user_text']))
            if row.get('reply'):
                seen=[o for o in observations if o.get('turn_id')==row['id']]
                called=[ToolCall(name=o['tool_name'],input_parameters=o.get('input'),output=o.get('output'))
                        for o in seen if o['name']=='tool.call']
                contexts=[str(o['output']) for o in seen if o['name']=='workspace.read' and o.get('output')]
                turns.append(Turn(role='assistant',content=row['reply'],tools_called=called,retrieval_context=contexts))
        if any(t.role=='user' for t in turns) and any(t.role=='assistant' for t in turns):
            cases.append(ConversationalTestCase(turns=turns,name=session['id'],scenario=snapshot['mission']['objective']))
    return cases


def evaluate(snapshot,observations,model=None):
    os.environ.setdefault('DEEPEVAL_TELEMETRY_OPT_OUT','YES')
    model=model or os.environ.get('SIEVANCE_EVAL_JUDGE_MODEL')
    if not model:
        return [unavailable('deepeval_judge','Set SIEVANCE_EVAL_JUDGE_MODEL and its provider credentials. Advisory scores are uncalibrated until reviewed.')]
    try:
        from deepeval.metrics import (KnowledgeRetentionMetric,ConversationalGEval,
                                      GoalAccuracyMetric,ToolUseMetric,ConversationCompletenessMetric)
        from deepeval.test_case import MultiTurnParams,ToolCall
        from src.lifesci.process_engineering.conversation import OPERATIONS
        cases=conversations(snapshot,observations)
        out=[]
        for case in cases:
            metrics=[KnowledgeRetentionMetric(model=model,async_mode=False),
                     GoalAccuracyMetric(model=model,async_mode=False),
                     ConversationCompletenessMetric(model=model,async_mode=False),
                     ToolUseMetric(available_tools=[ToolCall(name=k,description=str(v.model_json_schema()))
                                                  for k,v in OPERATIONS.items()],model=model,async_mode=False),
                     ConversationalGEval(name='Useful evidence-grounded guidance',model=model,async_mode=False,
                        evaluation_params=[MultiTurnParams.CONTENT,MultiTurnParams.ROLE],
                        evaluation_steps=['Check guidance against retrieved context in the actual assistant turns.',
                            'Assess whether it distinguishes observation, hypothesis and uncertainty.',
                            'Assess whether it gives one useful next action without unnecessary repetition or charts.'])]
            for metric in metrics:
                try:
                    metric.measure(case)
                    out.append({'name':metric.__name__,'session_id':case.name,
                                'status':'PASS' if metric.is_successful() else 'FAIL',
                                'score':metric.score,'reason':metric.reason,'advisory':True,
                                'calibration_status':'NOT_TESTABLE: awaiting domain review'})
                except Exception as exc:
                    out.append(unavailable(type(metric).__name__,f'judge failed: {type(exc).__name__}'))
        from deepeval.metrics import FaithfulnessMetric, ContextualRelevancyMetric
        from deepeval.test_case import LLMTestCase
        for case in cases:
            question=''
            for turn in case.turns:
                if turn.role=='user':
                    question=turn.content
                elif turn.retrieval_context and question:
                    tc=LLMTestCase(input=question,actual_output=turn.content,retrieval_context=turn.retrieval_context)
                    for metric in (FaithfulnessMetric(model=model,async_mode=False), ContextualRelevancyMetric(model=model,async_mode=False)):
                        try:
                            metric.measure(tc)
                            out.append({'name':metric.__name__,'session_id':case.name,'score':metric.score,
                                        'reason':metric.reason,'status':'PASS' if metric.is_successful() else 'FAIL','advisory':True})
                        except Exception as exc:
                            out.append(unavailable(type(metric).__name__,f'judge failed: {type(exc).__name__}'))
        return out or [unavailable('deepeval_transcript','No completed real assistant conversation.')]
    except (ImportError,ValueError) as exc:
        return [unavailable('deepeval_setup',f'{type(exc).__name__}: {exc}')]


def simulate(adapter,session_id,scenario,*,model,max_user_simulations=3):
    """Optional adaptive user messages; callbacks enter the same real message service."""
    os.environ.setdefault('DEEPEVAL_TELEMETRY_OPT_OUT','YES')
    from deepeval.simulator import ConversationSimulator
    from deepeval.dataset import ConversationalGolden
    from deepeval.test_case import Turn
    def callback(input,**kwargs):
        text=input if isinstance(input,str) else input[-1].content
        result=adapter.send_user_message(session_id,text)
        turn=result['turns'][-1]
        return Turn(role='assistant',content=turn.get('reply') or turn.get('system_message') or turn['status'])
    simulator=ConversationSimulator(model_callback=callback,simulator_model=model,async_mode=False,max_concurrent=1)
    return simulator.simulate([ConversationalGolden(scenario=scenario,
        user_description='Manufacturing engineer working only with the authorized synthetic workspace.',
        expected_outcome='Obtain a useful evidence-grounded next step; never approve manufacturing actions.')],
        max_user_simulations=max_user_simulations)
