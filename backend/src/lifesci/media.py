"""LiveKit SFU adapter. Only server environment owns administrative credentials."""
import hashlib
import json
import os
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from urllib.error import HTTPError

from .connectors import NoRedirect


class MediaUnavailable(OSError):
    pass


class LiveKitProvider:
    def __init__(self, url: str, key: str, secret: str, api_url: str | None = None):
        parsed = urlsplit(url)
        if parsed.scheme not in ("wss", "ws") or parsed.username or parsed.query or parsed.fragment:
            raise ValueError("LIVEKIT_URL must be a ws/wss server URL")
        if parsed.scheme == "ws" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("remote LiveKit connections require wss")
        self.url, self.key, self.secret = url.rstrip("/"), key, secret
        self.api_url = api_url or self.url.replace("wss://", "https://", 1).replace("ws://", "http://", 1)
        control = urlsplit(self.api_url)
        if control.scheme not in ("http", "https") or control.username or control.query or control.fragment:
            raise ValueError("invalid LiveKit administrative origin")

    def _token(self, identity: str, grants: dict) -> str:
        import jwt
        now = int(time.time())
        return jwt.encode({"iss": self.key, "sub": identity, "nbf": now - 5, "exp": now + 120,
                           "video": grants}, self.secret, algorithm="HS256")

    @staticmethod
    def identity(actor: str) -> str:
        return hashlib.sha256(actor.encode()).hexdigest()[:32]

    def _call(self, method: str, payload: dict, grants: dict) -> dict:
        token = self._token("platform-control", grants)
        req = Request(f"{self.api_url}/twirp/livekit.RoomService/{method}", data=json.dumps(payload).encode(),
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with build_opener(NoRedirect()).open(req, timeout=10) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            if exc.code == 404 and method in ("DeleteRoom", "RemoveParticipant"):
                return {}  # desired absent state; safe after a lost acknowledgement
            raise MediaUnavailable("Media server did not confirm the operation; retry or reconcile the room") from exc
        except (OSError, ValueError) as exc:
            raise MediaUnavailable("Media server did not confirm the operation; retry or reconcile the room") from exc

    def create_room(self, session_id: str) -> dict:
        room = f"bd-{session_id}"
        self._call("CreateRoom", {"name": room, "empty_timeout": 300, "max_participants": 20}, {"roomCreate": True})
        return {"room_id": room}

    def join_token(self, room_id: str, participant_id: str, permissions: dict) -> str:
        return self._token(self.identity(participant_id), {"roomJoin": True, "room": room_id,
            "canPublish": bool(permissions.get("publish")), "canSubscribe": bool(permissions.get("subscribe")),
            "canPublishData": False, "canUpdateOwnMetadata": False})

    def close_room(self, room_id: str) -> None:
        self._call("DeleteRoom", {"room": room_id}, {"roomCreate": True})

    def remove_participant(self, room_id: str, actor_id: str) -> None:
        self._call("RemoveParticipant", {"room": room_id, "identity": self.identity(actor_id)}, {"roomAdmin": True, "room": room_id})


def configured_media() -> dict:
    values = [os.environ.get(k) for k in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")]
    if not any(values):
        return {}
    if not all(values):
        raise ValueError("LiveKit requires URL, API key and API secret together")
    return {"livekit": LiveKitProvider(*values, api_url=os.environ.get("LIVEKIT_API_URL"))}
