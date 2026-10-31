from fastapi import Depends, Header

from .schemas import AdapterProposalIn, AgentPlanIn, PipelineSpec, ReviewIn


def install_analysis_api(p, app, ctx_dep, idempotent):
    service = p.process_models.analysis
    @app.get("/v1/process-model/catalog")
    def catalog(simulation_id: str | None = None, candidate_index: int = 0, ctx=Depends(ctx_dep)):
        return service.models(ctx, simulation_id, candidate_index)

    @app.post("/v1/process-model/adapter-proposals")
    def adapter_proposal(body: AdapterProposalIn, ctx=Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        return idempotent(ctx, key, "physical-adapter-proposal", body.model_dump(), lambda: service.propose_adapter(ctx, body))

    @app.post("/v1/process-model/pipelines/agent-plan")
    def agent_plan(body: AgentPlanIn, ctx=Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        return idempotent(ctx, key, "physical-agent-plan", body.model_dump(), lambda: service.agent_plan(ctx, body))

    @app.post("/v1/process-model/pipelines")
    def prepare(body: PipelineSpec, ctx=Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        return idempotent(ctx, key, "physical-plan", body.model_dump(), lambda: service.prepare(ctx, body))

    @app.get("/v1/process-model/pipelines/{plan_id}")
    def get_plan(plan_id: str, ctx=Depends(ctx_dep)):
        return service.get_plan(ctx, plan_id)

    @app.post("/v1/process-model/pipelines/{plan_id}/execute")
    def run(plan_id: str, ctx=Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        return idempotent(ctx, key, f"physical-execute:{plan_id}", {}, lambda: service.execute(ctx, plan_id))

    @app.get("/v1/process-model/analyses/{result_id}")
    def get_result(result_id: str, ctx=Depends(ctx_dep)):
        return service.get_result(ctx, result_id)

    @app.post("/v1/process-model/analyses/{result_id}/review")
    def review(result_id: str, body: ReviewIn, ctx=Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        return idempotent(ctx, key, f"physical-review:{result_id}", body.model_dump(), lambda: service.propose_review(ctx, result_id, body.owner_id))

    @app.post("/v1/process-model/analyses/{result_id}/agent-assessment")
    def assess(result_id: str, ctx=Depends(ctx_dep), key: str | None = Header(None, alias="Idempotency-Key")):
        return idempotent(ctx, key, f"physical-agent-assessment:{result_id}", {}, lambda: service.interpret(ctx, result_id))

    from .conversation_schemas import ConversationIn, MessageIn
    conversations = p.engineering_conversations
    tasks = app.state.tasks

    def turn_task(payload):
        # Rebuilt from stored role assignments, so revoked access also stops queued work.
        ctx = p.identity.context_for(payload['tenant'], payload['actor'], actor_kind=payload['actor_kind'],
                                     partner_org_id=payload.get('partner_org_id'))
        return conversations.run_turn(ctx, payload['thread_id'], payload['turn_id'])

    tasks.register('engineering_turn', turn_task)

    def queue_turn(ctx, thread_id, turn_id):
        tasks.submit('engineering_turn', {'tenant': ctx.tenant_id, 'actor': ctx.actor_id, 'actor_kind': ctx.actor_kind,
                                          'partner_org_id': ctx.partner_org_id, 'thread_id': thread_id, 'turn_id': turn_id})

    @app.get('/v1/process-model/conversations')
    def list_conversations(ctx=Depends(ctx_dep)):
        return {'conversations': conversations.list_for(ctx)}

    @app.post('/v1/process-model/conversations')
    def new_conversation(body: ConversationIn, ctx=Depends(ctx_dep), key: str | None = Header(None, alias='Idempotency-Key')):
        return idempotent(ctx, key, 'engineering-conversation', body.model_dump(), lambda: conversations.create(ctx, body))

    @app.get('/v1/process-model/conversation-sources')
    def conversation_sources(site_id: str = 'NF1', ctx=Depends(ctx_dep)):
        return {'sources': conversations.available_sources(ctx, site_id)}

    @app.get('/v1/process-model/conversations/{thread_id}')
    def get_conversation(thread_id: str, ctx=Depends(ctx_dep)):
        return conversations.get(ctx, thread_id)

    @app.post('/v1/process-model/conversations/{thread_id}/messages')
    def send_message(thread_id: str, body: MessageIn, ctx=Depends(ctx_dep), key: str | None = Header(None, alias='Idempotency-Key')):
        thread = idempotent(ctx, key, f'engineering-message:{thread_id}', body.model_dump(), lambda: conversations.enqueue(ctx, thread_id, body))
        current = conversations.get(ctx, thread_id)
        if current['turn_ids'][-1] == thread['turn_ids'][-1] and current['turns'][-1]['status'] == 'queued':
            queue_turn(ctx, thread_id, thread['turn_ids'][-1])
        return thread

    @app.post('/v1/process-model/conversations/{thread_id}/retry')
    def retry_turn(thread_id: str, ctx=Depends(ctx_dep)):
        thread = conversations.queue_retry(ctx, thread_id)
        if thread['turns'][-1]['status'] == 'queued':
            queue_turn(ctx, thread_id, thread['turn_ids'][-1])
        return thread

    @app.get('/v1/process-model/comparisons/{comparison_id}')
    def comparison(comparison_id: str, ctx=Depends(ctx_dep)):
        return p.evidence.read_derived(ctx, 'physical_analysis_comparison', comparison_id)

    @app.get('/v1/process-model/conversations/{thread_id}/artifacts/{kind}/{artifact_id}')
    def conversation_artifact(thread_id: str, kind: str, artifact_id: str, ctx=Depends(ctx_dep)):
        return conversations.artifact(ctx, thread_id, kind, artifact_id)

    @app.get('/v1/process-model/bioprocess/catalog')
    def bioprocess_catalog(ctx=Depends(ctx_dep)):
        p.identity.require(ctx, 'read', 'scientific_model_catalog')
        return p.bioprocess.catalog()

    @app.get('/v1/process-model/llm-connection')
    def llm_connection(ctx=Depends(ctx_dep)):
        from ..gateway.configuration import ENGINEERING_TASKS
        from ..gateway.router import RoutingError
        p.identity.require(ctx, 'read', 'scientific_model_catalog')
        tasks = {}
        for task, role in ENGINEERING_TASKS.items():
            try:
                route = p.gateway.router.route(task)
                details = route.to_dict()
                configured = route.profile.provider in p.gateway.providers
                tasks[role] = {'task_kind': task, 'status': 'configured_not_connectivity_tested' if configured else 'missing_provider_credentials',
                    'route': details, 'provider_configured': configured}
            except RoutingError as exc:
                profile_id = p.gateway.router.task_profile_bindings.get(task)
                profile = p.gateway.registry.profiles.get(profile_id) if profile_id else None
                tasks[role] = {'task_kind': task, 'status': 'route_blocked', 'issue': str(exc),
                    'configured_model': profile.model if profile else None, 'provider': profile.provider if profile else None}
        return {'development_unqualified_routes': p.allow_unqualified, 'tasks': tasks,
            'note': 'Configuration status only; send a chat message to test actual model access. Keys and endpoint URLs are not returned.'}
