from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import src.lifesci.collab as collab
from src.lifesci.identity import AuthorizationError, IdentityService
from src.lifesci.store import RecordStore

T = "tenant-a"
T0 = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)


def at(minutes: float = 0, days: int = 0) -> datetime:
    return T0 + timedelta(minutes=minutes, days=days)


@pytest.fixture
def env():
    s = RecordStore()
    idn = IdentityService(s)
    for actor, role, site in [("admin1", "admin", None), ("sup1", "supervisor", "S1"), ("op1", "operator", "S1"),
                              ("op2", "operator", "S1"), ("opX", "operator", "S2"), ("qa1", "qa", None)]:
        idn.assign_role(T, actor, role, site_id=site)
    idn.assign_role(T, "agent1", "agent", actor_kind="agent")
    with s.transaction("seed") as tx:
        tx.put(T, "case", "case1", {"site_id": "S1", "known_facts": {"event": "temperature excursion", "equipment": "bio-1"},
                                    "open_questions": ["root cause"], "missing_evidence": ["historian export"]},
               expected_revision=None, action="create")
        tx.put(T, "case", "case2", {"site_id": "S1"}, expected_revision=None, action="create")
    media = collab.FakeMediaProvider()
    return SimpleNamespace(
        s=s, idn=idn, media=media, sessions=collab.RemoteSessionService(s, idn, {"external": media}),
        admin=idn.context_for(T, "admin1"), sup=idn.context_for(T, "sup1"), op1=idn.context_for(T, "op1"),
        op2=idn.context_for(T, "op2"), opx=idn.context_for(T, "opX"), qa=idn.context_for(T, "qa1"),
        agent=idn.context_for(T, "agent1", actor_kind="agent"),
        expert=idn.context_for(T, "ext1", actor_kind="partner", partner_org_id="orgX"))


def emit(env, event_type: str, site: str = "S1", thing: str = "t1") -> None:
    with env.s.transaction("src") as tx:
        cur = tx.get(T, "thing", thing)
        tx.put(T, "thing", thing, {"site_id": site, "n": (cur.state["n"] + 1) if cur else 1},
               expected_revision=cur.revision if cur else None, action="touch", event_type=event_type,
               event_payload={"site_id": site, "value": 41})


# --- LS-022 triggers --------------------------------------------------------------------------------


def test_LS022_event_trigger_matches_type_and_predicate_and_creates_a_task(env):
    svc = collab.TriggerService(env.s, env.idn)
    svc.register(env.admin, "tr-evt", "event", {"event_type": "deviation.*", "where": [
        {"field": "payload.site_id", "op": "eq", "value": "S1"}, {"field": "payload.value", "op": "gt", "value": 40}]},
                 {"type": "create_task", "title": "Review deviation", "owner": "sup1"})
    emit(env, "deviation.opened", site="S2")
    emit(env, "deviation.opened", site="S1")
    emit(env, "batch.released", site="S1", thing="t2")
    fired = svc.process_events(env.admin)
    assert len(fired) == 1 and fired[0]["status"] == "completed" and fired[0]["kind"] == "event"
    tasks = env.s.read().list(T, "task")
    assert len(tasks) == 1 and tasks[0].state["title"] == "Review deviation" and tasks[0].state["owner"] == "sup1"
    assert svc.process_events(env.admin) == []


def test_LS022_event_firing_is_deduplicated_when_events_are_redelivered(env):
    svc = collab.TriggerService(env.s, env.idn)
    svc.register(env.admin, "tr-dup", "event", {"event_type": "deviation.opened"}, {"type": "create_task"})
    emit(env, "deviation.opened")
    assert len(svc.process_events(env.admin)) == 1
    with env.s.transaction("test") as tx:
        cur = tx.require(T, "trigger_cursor", "events")
        tx.put(T, "trigger_cursor", "events", {"seq": 0}, expected_revision=cur.revision, action="rewind")
    assert svc.process_events(env.admin) == []
    assert len(env.s.read().list(T, "task")) == 1 and len(svc.firings(env.admin, "tr-dup")) == 1


def test_LS022_schedule_trigger_every_n_minutes_fires_once_per_slot(env):
    svc = collab.TriggerService(env.s, env.idn)
    svc.register(env.admin, "tr-sched", "schedule", {"every_minutes": 15}, {"type": "create_task"}, now=at(1))
    assert svc.tick(env.admin, at(7)) == []
    assert len(svc.tick(env.admin, at(16))) == 1
    assert svc.tick(env.admin, at(20)) == [] and svc.tick(env.admin, at(16)) == []
    assert len(svc.tick(env.admin, at(31))) == 1
    assert len(svc.tick(env.admin, at(600))) == 1
    assert len(svc.firings(env.admin, "tr-sched")) == 3


def test_LS022_schedule_trigger_daily_at(env):
    svc = collab.TriggerService(env.s, env.idn)
    svc.register(env.admin, "tr-daily", "schedule", {"daily_at": "06:30"}, {"type": "create_task"}, now=at(0))
    assert svc.tick(env.admin, at(60)) == []
    assert len(svc.tick(env.admin, at(0, days=1) - timedelta(minutes=30))) == 1
    assert svc.tick(env.admin, at(0, days=1) - timedelta(minutes=10)) == []
    assert len(svc.tick(env.admin, at(0, days=2))) == 1


def test_LS022_alarm_trigger_latches_per_excursion_and_calls_handlers(env):
    calls = []
    svc = collab.TriggerService(env.s, env.idn, {"notify": lambda ctx, action, firing: calls.append(firing["context"]) or {"sent": True},
                                                 "start_mission": lambda ctx, action, firing: {"mission": "m1"}})
    svc.register(env.admin, "tr-alarm", "alarm", {"signal": "bio1.temp", "op": "gt", "threshold": 40},
                 {"type": "notify", "to": "sup1"})
    svc.register(env.admin, "tr-mission", "alarm", {"signal": "bio1.temp", "op": "gt", "threshold": 40}, {"type": "start_mission"})
    assert svc.observe(env.admin, "bio1.temp", 39.0) == []
    assert len(svc.observe(env.admin, "bio1.temp", 41.0)) == 2
    assert svc.observe(env.admin, "bio1.temp", 43.0) == []
    assert svc.observe(env.admin, "other", 99.0) == []
    svc.observe(env.admin, "bio1.temp", 38.0)
    assert len(svc.observe(env.admin, "bio1.temp", 44.0)) == 2
    assert [c["value"] for c in calls] == [41.0, 44.0]
    assert {f["result"].get("mission") for f in svc.firings(env.admin, "tr-mission")} == {"m1"}


def test_LS022_file_change_trigger_fires_on_digest_change_only(env, tmp_path):
    f = tmp_path / "setpoints.csv"
    f.write_text("a,1\n")
    svc = collab.TriggerService(env.s, env.idn)
    svc.register(env.admin, "tr-file", "file_change", {"path": str(f)}, {"type": "create_task", "title": "Setpoint file changed"})
    assert svc.check_files(env.admin) == []
    f.write_text("a,2\n")
    out = svc.check_files(env.admin)
    assert len(out) == 1 and out[0]["context"]["previous"] != out[0]["context"]["digest"]
    assert svc.check_files(env.admin) == []
    f.write_text("a,1\n")
    assert len(svc.check_files(env.admin)) == 1
    svc.register(env.admin, "tr-file2", "file_change", {"path": str(f), "fire_on_first": True}, {"type": "create_task"})
    assert len(svc.check_files(env.admin)) == 1


def test_LS022_missing_handler_is_recorded_as_failed_and_config_is_validated(env):
    svc = collab.TriggerService(env.s, env.idn)
    svc.register(env.admin, "tr-n", "event", {"event_type": "x.*"}, {"type": "notify"})
    emit(env, "x.y")
    out = svc.process_events(env.admin)
    assert out[0]["status"] == "failed" and "no handler" in out[0]["result"]["error"]
    with pytest.raises(AuthorizationError):
        svc.register(env.op1, "bad", "event", {"event_type": "x"}, {"type": "create_task"})
    with pytest.raises(ValueError):
        svc.register(env.admin, "bad", "schedule", {"every_minutes": 5, "daily_at": "01:00"}, {"type": "create_task"})
    with pytest.raises(ValueError):
        svc.register(env.admin, "bad", "alarm", {"signal": "s", "op": "approx", "threshold": 1}, {"type": "create_task"})
    with pytest.raises(ValueError):
        svc.register(env.admin, "bad", "event", {"event_type": "x"}, {"type": "release_batch"})


# --- LS-022 channels ----------------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status: int, doc: dict | None = None) -> None:
        self.status_code, self.doc = status, doc or {}

    def json(self):
        return self.doc


def recording_transport(response=None, error: Exception | None = None):
    calls = []

    def transport(method, url, **kw):
        calls.append({"method": method, "url": url, **kw})
        if error:
            raise error
        return response or FakeResponse(200)

    transport.calls = calls
    return transport


MSG = collab.ChannelMessage("+15550100", "Excursion", "Temp above limit", "key-1")


def test_LS022_adapters_are_enabled_only_with_organization_config():
    assert not any(a.enabled() for a in (collab.SlackWebhookAdapter(), collab.TeamsWebhookAdapter(), collab.TwilioSmsAdapter(),
                                         collab.WhatsAppAdapter(), collab.EmailSMTPAdapter()))
    assert collab.SlackWebhookAdapter({"webhook_url": "https://hooks.example/x"}).enabled()
    assert not collab.TwilioSmsAdapter({"account_sid": "AC1", "auth_token": "t"}).enabled()
    with pytest.raises(collab.ChannelDisabled):
        collab.WhatsAppAdapter(transport=recording_transport()).send(MSG)


def test_LS022_http_adapters_build_provider_requests_and_parse_receipts():
    slack_t = recording_transport()
    slack = collab.SlackWebhookAdapter({"webhook_url": "https://hooks.example/s"}, slack_t)
    assert slack.send(MSG)["http_status"] == 200
    assert slack_t.calls[0]["url"] == "https://hooks.example/s" and "Temp above limit" in slack_t.calls[0]["json"]["text"]
    teams_t = recording_transport()
    collab.TeamsWebhookAdapter({"webhook_url": "https://teams.example/t"}, teams_t).send(MSG)
    assert teams_t.calls[0]["json"]["@type"] == "MessageCard"
    sms_t = recording_transport(FakeResponse(201, {"sid": "SM123"}))
    sms = collab.TwilioSmsAdapter({"account_sid": "AC1", "auth_token": "tok", "from_number": "+15550000"}, sms_t)
    assert sms.send(MSG)["provider_message_id"] == "SM123"
    call = sms_t.calls[0]
    assert call["url"].endswith("/Accounts/AC1/Messages.json") and call["data"]["To"] == "+15550100" and call["auth"] == ("AC1", "tok")
    wa_t = recording_transport(FakeResponse(200, {"messages": [{"id": "wamid.9"}]}))
    wa = collab.WhatsAppAdapter({"phone_number_id": "123", "access_token": "tkn"}, wa_t)
    assert wa.send(MSG)["provider_message_id"] == "wamid.9"
    assert wa_t.calls[0]["url"].endswith("/123/messages") and wa_t.calls[0]["headers"]["Authorization"] == "Bearer tkn"
    assert wa_t.calls[0]["json"]["to"] == "+15550100"


def test_LS022_http_adapter_error_semantics_distinguish_failed_from_unknown():
    cfg = {"webhook_url": "https://hooks.example/s"}
    with pytest.raises(collab.ChannelError):
        collab.SlackWebhookAdapter(cfg, recording_transport(FakeResponse(400))).send(MSG)
    with pytest.raises(collab.ChannelUnknown):
        collab.SlackWebhookAdapter(cfg, recording_transport(FakeResponse(503))).send(MSG)
    with pytest.raises(collab.ChannelUnknown):
        collab.SlackWebhookAdapter(cfg, recording_transport(error=TimeoutError("read timeout"))).send(MSG)


def test_LS022_email_adapter_builds_message_and_sends_through_injected_smtp():
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            self.host, self.port = host, port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            sent.append("starttls")

        def login(self, u, p):
            sent.append(("login", u))

        def send_message(self, msg):
            sent.append(msg)

    email = collab.EmailSMTPAdapter({"host": "smtp.example", "port": 587, "from_addr": "lims@example", "starttls": True,
                                    "username": "u", "password": "p"}, FakeSMTP)
    msg = email.build_message(MSG)
    assert msg["To"] == "+15550100" and msg["Subject"] == "Excursion" and msg["Message-ID"].endswith("@smtp.example>")
    receipt = email.send(MSG)
    assert sent[0] == "starttls" and sent[1] == ("login", "u") and receipt["provider_message_id"] == msg["Message-ID"]


# --- LS-061 notifications ------------------------------------------------------------------------------


@pytest.fixture
def notif(env):
    chan = collab.InMemoryChannel("email")
    return SimpleNamespace(chan=chan, svc=collab.NotificationService(env.s, env.idn, [chan, collab.InMemoryChannel("sms", enabled=False)]))


PAYLOAD = {"subject": "Deviation DV-1", "body": "Please review", "revision": 3}


def test_LS061_notification_records_owner_payload_revision_attempts_and_receipt(env, notif):
    n = notif.svc.send(env.sup, "qa@example", "email", PAYLOAD, "sup1", "dv1-notice", case_id="case1")
    assert n["status"] == "sent" and n["owner"] == "sup1" and n["payload_revision"] == 3 and len(n["payload_hash"]) == 64
    assert n["attempts"][0]["outcome"] == "sent" and n["receipt"]["provider_message_id"] == "msg-1"
    assert notif.svc.get(env.sup, n["notification_id"])["recipient"] == "qa@example"


def test_LS061_lost_provider_response_is_unknown_then_reconciled_without_duplicate(env, notif):
    notif.chan.lose_response_next = 1
    n = notif.svc.send(env.sup, "qa@example", "email", PAYLOAD, "sup1", "dv1-notice")
    assert n["status"] == "unknown" and n["receipt"] is None and len(notif.chan.sent) == 1
    with pytest.raises(ValueError, match="reconcile"):
        notif.svc.retry(env.sup, n["notification_id"])
    again = notif.svc.send(env.sup, "qa@example", "email", PAYLOAD, "sup1", "dv1-notice")
    assert again["duplicate"] and again["status"] == "unknown" and len(notif.chan.sent) == 1
    done = notif.svc.reconcile(env.sup, n["notification_id"], notif.chan.lookup)
    assert done["status"] == "sent" and done["receipt"]["provider_message_id"] == "msg-1"
    assert done["attempts"][-1]["outcome"] == "reconciled_sent" and len(notif.chan.sent) == 1


def test_LS061_retry_never_duplicates_a_known_sent_message(env, notif):
    n = notif.svc.send(env.sup, "qa@example", "email", PAYLOAD, "sup1", "k1")
    assert notif.svc.retry(env.sup, n["notification_id"])["duplicate"] is True
    assert notif.svc.send(env.sup, "qa@example", "email", PAYLOAD, "sup1", "k1")["duplicate"] is True
    assert len(notif.chan.sent) == 1


def test_LS061_known_failure_can_be_retried_once_and_then_stays_sent(env, notif):
    notif.chan.fail_next = 1
    n = notif.svc.send(env.sup, "qa@example", "email", PAYLOAD, "sup1", "k2")
    assert n["status"] == "failed" and notif.chan.sent == []
    ok = notif.svc.retry(env.sup, n["notification_id"])
    assert ok["status"] == "sent" and [a["outcome"] for a in ok["attempts"]] == ["failed", "sent"]
    notif.svc.retry(env.sup, n["notification_id"])
    assert len(notif.chan.sent) == 1


def test_LS061_inconclusive_lookup_keeps_unknown_and_authoritative_absence_allows_resend(env, notif):
    notif.chan.drop_next = 1
    n = notif.svc.send(env.sup, "qa@example", "email", PAYLOAD, "sup1", "k3")
    assert n["status"] == "unknown" and notif.chan.sent == []
    still = notif.svc.reconcile(env.sup, n["notification_id"], notif.chan.lookup)
    assert still["status"] == "unknown"
    absent = notif.svc.reconcile(env.sup, n["notification_id"], notif.chan.lookup, authoritative_absence=True)
    assert absent["status"] == "failed"
    assert notif.svc.retry(env.sup, n["notification_id"])["status"] == "sent" and len(notif.chan.sent) == 1


def test_LS061_disabled_channel_records_failure_and_key_reuse_with_other_payload_is_rejected(env, notif):
    n = notif.svc.send(env.sup, "+1555", "sms", PAYLOAD, "sup1", "k4")
    assert n["status"] == "failed" and "disabled" in n["attempts"][0]["detail"]
    with pytest.raises(ValueError, match="different notification"):
        notif.svc.send(env.sup, "+1555", "sms", {**PAYLOAD, "body": "changed"}, "sup1", "k4")
    with pytest.raises(ValueError, match="unknown channel"):
        notif.svc.send(env.sup, "x", "pager", PAYLOAD, "sup1", "k5")


def test_LS061_agents_cannot_send_directly(env, notif):
    with pytest.raises(PermissionError, match="ActionService"):
        notif.svc.send(env.agent, "qa@example", "email", PAYLOAD, "sup1", "k6")
    assert notif.chan.sent == []


def test_LS022_each_adapter_records_delivery_outcomes_through_the_service(env):
    transports = {
        "slack": recording_transport(), "teams": recording_transport(FakeResponse(503)),
        "sms": recording_transport(FakeResponse(400)), "whatsapp": recording_transport(FakeResponse(200, {"messages": [{"id": "w1"}]}))}
    adapters = [collab.SlackWebhookAdapter({"webhook_url": "https://s"}, transports["slack"]),
                collab.TeamsWebhookAdapter({"webhook_url": "https://t"}, transports["teams"]),
                collab.TwilioSmsAdapter({"account_sid": "A", "auth_token": "t", "from_number": "+1"}, transports["sms"]),
                collab.WhatsAppAdapter({"phone_number_id": "1", "access_token": "x"}, transports["whatsapp"]),
                collab.EmailSMTPAdapter()]
    svc = collab.NotificationService(env.s, env.idn, adapters)
    got = {a.name: svc.send(env.sup, "r", a.name, PAYLOAD, "sup1", f"key-{a.name}")["status"] for a in adapters}
    assert got == {"slack": "sent", "teams": "unknown", "sms": "failed", "whatsapp": "sent", "email": "failed"}


# --- LS-072 procedure-timed notices -----------------------------------------------------------------------


@pytest.fixture
def sched(env, notif):
    return SimpleNamespace(chan=notif.chan, notif=notif.svc, svc=collab.NoticeScheduler(env.s, env.idn, notif.svc),
                           policy=collab.NotificationPolicy("p1", 24, "email", ("regulatory@example", "qa@example"), grace_minutes=30))


def test_LS072_initial_notice_is_sent_at_deadline_even_with_missing_evidence(env, sched):
    row = sched.svc.schedule_initial(env.sup, "case1", at(0), sched.policy, owner="sup1")
    assert row["due_at"] == at(24 * 60).isoformat()
    assert sched.svc.run_due(env.sup, at(23 * 60)) == [] and sched.chan.sent == []
    out = sched.svc.run_due(env.sup, at(24 * 60 + 1))
    assert out[0]["status"] == "sent" and out[0]["evidence_complete_at_send"] is False and out[0]["sent_late"] is False
    assert len(sched.chan.sent) == 2
    body = sched.chan.sent[0].body
    assert "temperature excursion" in body and "evidence not yet available: historian export" in body and "root cause" in body
    note = sched.notif.get(env.sup, out[0]["notification_ids"][0])
    assert note["payload"]["evidence_complete"] is False and note["notice_type"] == "initial"
    assert sched.svc.run_due(env.sup, at(25 * 60)) == [] and len(sched.chan.sent) == 2


def test_LS072_initial_notice_without_a_readable_case_still_goes_out(env, sched):
    sched.svc.schedule_initial(env.sup, "ghost", at(0), sched.policy, owner="sup1")
    sched.svc.run_due(env.sup, at(25 * 60))
    assert "case record not found" in sched.chan.sent[0].body


def test_LS072_failed_initial_delivery_is_overdue_visible_and_retried_without_duplicates(env, sched):
    sched.svc.schedule_initial(env.sup, "case1", at(0), sched.policy, owner="sup1")
    sched.chan.fail_next = 1
    first = sched.svc.run_due(env.sup, at(24 * 60 + 1))
    assert first[0]["status"] == "attention" and len(sched.chan.sent) == 1
    assert len(sched.svc.overdue(env.sup, at(24 * 60 + 5))) == 0 and len(sched.svc.overdue(env.sup, at(24 * 60 + 45))) == 1
    second = sched.svc.run_due(env.sup, at(24 * 60 + 50))
    assert second[0]["status"] == "sent" and second[0]["sent_late"] is True
    assert sorted(m.recipient for m in sched.chan.sent) == ["qa@example", "regulatory@example"]


def test_LS072_follow_up_findings_and_review_package_have_separate_delivery_states(env, sched):
    sched.svc.schedule_initial(env.sup, "case1", at(0), sched.policy, owner="sup1")
    sched.svc.run_due(env.sup, at(24 * 60 + 1))
    sched.chan.fail_next = 2
    findings = sched.svc.send_findings(env.sup, "case1", {"root_cause": "failed probe"}, sched.policy, owner="sup1")
    package = sched.svc.send_review_package(env.sup, "case1", {"package_id": "PKG-1"}, sched.policy, owner="sup1")
    assert [n["status"] for n in findings] == ["failed", "failed"] and [n["status"] for n in package] == ["sent", "sent"]
    states = sched.svc.delivery_states(env.sup, "case1")
    assert states["initial"] == {"regulatory@example": "sent", "qa@example": "sent"}
    assert set(states["findings"].values()) == {"failed"} and set(states["review_package"].values()) == {"sent"}
    ids = {n["notification_id"] for n in [*findings, *package]}
    assert len(ids) == 4
    revised = sched.svc.send_findings(env.sup, "case1", {"root_cause": "failed probe; confirmed"}, sched.policy, owner="sup1", revision=2)
    assert [n["status"] for n in revised] == ["sent", "sent"] and revised[0]["payload_revision"] == 2


# --- LS-037 / LS-038 / LS-039 -----------------------------------------------------------------------------


def test_LS037_session_checks_participant_access_and_links_to_case(env):
    with pytest.raises(PermissionError, match="opX"):
        env.sessions.create(env.sup, "case1", ["op1", "opX"], site_id="S1")
    with pytest.raises(PermissionError, match="ext1"):
        env.sessions.create(env.sup, "case1", ["op1", {"actor_id": "ext1", "kind": "partner", "partner_org_id": "orgX"}], site_id="S1")
    assert env.s.read().list(T, "remote_session") == [] and env.media.rooms == {}
    session = env.sessions.create(env.sup, "case1", ["op1", "op2"], site_id="S1")
    assert session["case_id"] == "case1" and session["room_id"] in env.media.rooms and session["status"] == "active"
    assert [p["actor_id"] for p in session["participants"]] == ["sup1", "op1", "op2"]
    assert env.s.read().edges_from(T, "case", "case1") == [("remote_session", session["session_id"], "assistance_session")]
    assert [s["session_id"] for s in env.sessions.sessions_for_case(env.sup, "case1")] == [session["session_id"]]
    with pytest.raises(ValueError, match="media provider"):
        env.sessions.create(env.sup, "case1", ["op1"], media_provider="zoomish", site_id="S1")


def test_LS037_access_is_rechecked_at_join_and_revoked_roles_are_denied(env):
    session = env.sessions.create(env.sup, "case1", ["op1"], site_id="S1")
    sid = session["session_id"]
    joined = env.sessions.join(env.op1, sid)
    assert joined["token"].startswith("tok:") and env.media.tokens[-1][1] == "op1"
    env.idn.revoke_role(T, "op1", "operator", site_id="S1")
    with pytest.raises(AuthorizationError):
        env.sessions.join(env.idn.context_for(T, "op1"), sid)
    with pytest.raises(PermissionError, match="not a participant"):
        env.sessions.join(env.op2, sid)
    env.sessions.end(env.sup, sid)
    with pytest.raises(PermissionError, match="ended"):
        env.sessions.join(env.sup, sid)
    assert env.media.closed == [session["room_id"]]


def test_LS037_recording_requires_every_participants_consent(env):
    sid = env.sessions.create(env.sup, "case1", ["op1", "op2"], site_id="S1")["session_id"]
    with pytest.raises(PermissionError, match="missing"):
        env.sessions.set_recording(env.sup, sid, True)
    for ctx in (env.sup, env.op1):
        env.sessions.record_consent(ctx, sid, True)
    with pytest.raises(PermissionError, match="op2"):
        env.sessions.set_recording(env.sup, sid, True)
    env.sessions.record_consent(env.op2, sid, True)
    assert env.sessions.set_recording(env.sup, sid, True)["recording"]["enabled"] is True
    assert env.sessions.join(env.op1, sid)["recording"] is True
    state = env.sessions.record_consent(env.op2, sid, False)
    assert state["recording"]["enabled"] is False and "withdrawn" in state["recording"]["reason"]
    with pytest.raises(PermissionError):
        env.sessions.set_recording(env.op1, sid, True)
    with pytest.raises(PermissionError):
        env.sessions.record_consent(env.opx, sid, True)


def expert_session(env):
    sid = env.sessions.create(env.sup, "case1", ["op1"], site_id="S1")["session_id"]
    for mid, case in [("m1", "case1"), ("m2", "case1"), ("m3", "case2")]:
        env.sessions.register_media(env.sup, case, mid, media_type="video/mp4", site_id="S1")
    env.sessions.invite_external_expert(env.qa, sid, expert_id="ext1", partner_org_id="orgX", media_ids=["m1"])
    return sid


def test_LS039_external_expert_sees_only_authorized_case_and_permitted_media(env):
    sid = expert_session(env)
    joined = env.sessions.join(env.expert, sid)
    assert joined["permissions"]["media_ids"] == ["m1"] and joined["permissions"]["record"] is False
    assert env.sessions.open_case(env.expert, sid)["case_id"] == "case1"
    assert env.sessions.read_media(env.expert, sid, "m1")["media_id"] == "m1"
    for other in ("m2", "m3"):
        with pytest.raises(PermissionError):
            env.sessions.read_media(env.expert, sid, other)
    with pytest.raises(PermissionError, match="limited to case"):
        env.sessions.open_case(env.expert, sid, "case2")
    assert not env.idn.check(env.expert, "read", "case", "case2") and not env.idn.check(env.expert, "read", "tenant_memory")
    assert env.sessions.read_media(env.op1, sid, "m2")["media_id"] == "m2"


def test_LS039_expert_cannot_be_invited_to_other_case_media_and_revocation_removes_access(env):
    sid = expert_session(env)
    with pytest.raises(PermissionError, match="does not belong"):
        env.sessions.invite_external_expert(env.qa, sid, expert_id="ext2", partner_org_id="orgX", media_ids=["m3"])
    with pytest.raises(AuthorizationError):
        env.sessions.invite_external_expert(env.op1, sid, expert_id="ext2", partner_org_id="orgX", media_ids=["m1"])
    env.sessions.revoke_external_expert(env.qa, sid, "ext1")
    with pytest.raises(PermissionError):
        env.sessions.join(env.expert, sid)
    assert not env.idn.check(env.expert, "read", "case", "case1")


def test_LS039_expired_grant_blocks_expert(env):
    sid = env.sessions.create(env.sup, "case1", ["op1"], site_id="S1")["session_id"]
    env.sessions.register_media(env.sup, "case1", "m1", media_type="video/mp4", site_id="S1")
    env.sessions.invite_external_expert(env.qa, sid, expert_id="ext1", partner_org_id="orgX", media_ids=["m1"],
                                        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    with pytest.raises(PermissionError):
        env.sessions.join(env.expert, sid)


def test_LS038_annotations_are_stored_with_author_time_and_declared_device_support(env):
    sid = expert_session(env)
    env.sessions.annotate(env.op1, sid, "chat", {"text": "Seal looks seated"}, device="phone")
    env.sessions.annotate(env.expert, sid, "pointer", {"x": 0.4, "y": 0.2}, device="browser", media_id="m1")
    env.sessions.annotate(env.op1, sid, "drawing", {"strokes": [[0, 0, 1, 1]]}, device="tablet")
    rows = env.sessions.annotations(env.sup, sid)
    assert [(a["tool"], a["author"], a["device"]) for a in rows] == [("chat", "op1", "phone"), ("pointer", "ext1", "browser"),
                                                                    ("drawing", "op1", "tablet")]
    assert all(a["at"] and a["device_tested"] is False and a["session_id"] == sid for a in rows)
    assert env.s.read().edges_from(T, "remote_session", sid)[0][0] == "session_annotation"
    with pytest.raises(collab.ToolUnavailable, match="not declared"):
        env.sessions.annotate(env.op1, sid, "drawing", {}, device="phone")
    with pytest.raises(PermissionError):
        env.sessions.annotate(env.expert, sid, "pointer", {}, media_id="m2")
    with pytest.raises(PermissionError):
        env.sessions.annotate(env.op2, sid, "chat", {"text": "x"})
    assert collab.supported_tools("browser") == ["chat", "drawing", "pointer", "transcript"]
    assert collab.supported_tools("ar_headset") == []


def test_LS038_ar_and_walkie_talkie_are_declared_device_dependent_and_refused(env):
    sid = env.sessions.create(env.sup, "case1", ["op1"], site_id="S1")["session_id"]
    for tool, device in [("ar_pointer", "ar_headset"), ("walkie_talkie", "ptt_handset")]:
        assert collab.TOOL_DECLARATIONS[tool]["status"] == "device_dependent" and collab.TOOL_DECLARATIONS[tool]["device_tested"] is False
        with pytest.raises(collab.ToolUnavailable, match="not device-tested"):
            env.sessions.annotate(env.op1, sid, tool, {}, device=device)
    assert all(not v["device_tested"] for v in collab.TOOL_DECLARATIONS.values())
    with pytest.raises(ValueError):
        env.sessions.annotate(env.op1, sid, "hologram", {})


def test_LS038_transcript_needs_recording_consent_and_is_reviewed_before_use(env):
    sid = env.sessions.create(env.sup, "case1", ["op1"], site_id="S1")["session_id"]
    with pytest.raises(PermissionError, match="recording"):
        env.sessions.annotate(env.op1, sid, "transcript", {"text": "hello"})
    for ctx in (env.sup, env.op1):
        env.sessions.record_consent(ctx, sid, True)
    env.sessions.set_recording(env.sup, sid, True)
    seg = env.sessions.annotate(env.op1, sid, "transcript", {"text": "seal swapped", "start": 12.0, "end": 14.5})
    assert seg["review_status"] == "unreviewed"
    with pytest.raises(AuthorizationError):
        env.sessions.review_transcript(env.op1, seg["annotation_id"], "accepted")
    assert env.sessions.review_transcript(env.sup, seg["annotation_id"], "accepted")["review_status"] == "accepted"
    chat = env.sessions.annotate(env.op1, sid, "chat", {"text": "x"})
    with pytest.raises(ValueError):
        env.sessions.review_transcript(env.sup, chat["annotation_id"], "accepted")
    env.sessions.end(env.sup, sid)
    with pytest.raises(PermissionError):
        env.sessions.annotate(env.op1, sid, "chat", {"text": "late"})
