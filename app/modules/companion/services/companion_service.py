import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.action_set.models.action_set import ActionSet, ActionSetStatus
from app.modules.action_set.services.action_set_service import action_set_service
from app.modules.companion.models.companion import (
    CompanionApprovalChallenge,
    CompanionDevice,
    CompanionPairingSession,
)
from app.modules.companion.schemas.companion import (
    CompanionApprovalChallengeSchema,
    CompanionDeviceCodeResponse,
    CompanionPairingPollResponse,
)


PAIRING_TTL = timedelta(minutes=5)
CHALLENGE_TTL = timedelta(seconds=90)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _action_set_version(value: ActionSet) -> str:
    return f"{value.id}:{value.updated_at.isoformat(timespec='microseconds')}"


class CompanionService:
    def create_device_code(
        self, db: Session, device_uid: str, display_name: str
    ) -> CompanionDeviceCodeResponse:
        now = datetime.utcnow()
        for old in db.scalars(
            select(CompanionPairingSession).where(
                CompanionPairingSession.device_uid == device_uid,
                CompanionPairingSession.consumed.is_(False),
            )
        ):
            old.consumed = True

        code = "".join(secrets.choice("23456789") for _ in range(6))
        while db.scalar(
            select(CompanionPairingSession).where(
                CompanionPairingSession.code == code
            )
        ):
            code = "".join(secrets.choice("23456789") for _ in range(6))
        poll_token = secrets.token_urlsafe(32)
        session = CompanionPairingSession(
            device_uid=device_uid,
            code=code,
            poll_token_hash=_digest(poll_token),
            expires_at=now + PAIRING_TTL,
        )
        device = db.scalar(
            select(CompanionDevice).where(CompanionDevice.device_uid == device_uid)
        )
        if device is None:
            device = CompanionDevice(device_uid=device_uid, display_name=display_name)
            db.add(device)
        else:
            device.display_name = display_name
        db.add(session)
        db.commit()
        return CompanionDeviceCodeResponse(
            code=code,
            poll_token=poll_token,
            expires_at=session.expires_at,
        )

    def confirm_pairing(self, db: Session, code: str) -> CompanionDevice:
        session = self._valid_pairing(db, code)
        session.confirmed = True
        device = db.scalar(
            select(CompanionDevice).where(
                CompanionDevice.device_uid == session.device_uid
            )
        )
        if device is None:
            raise HTTPException(status_code=404, detail="配对设备不存在。")
        db.commit()
        db.refresh(device)
        return device

    def poll_pairing(
        self, db: Session, code: str, poll_token: str
    ) -> CompanionPairingPollResponse:
        session = self._valid_pairing(db, code)
        if not hmac.compare_digest(session.poll_token_hash, _digest(poll_token)):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="配对凭据无效。")
        if not session.confirmed:
            return CompanionPairingPollResponse(status="PENDING")

        device = db.scalar(
            select(CompanionDevice).where(
                CompanionDevice.device_uid == session.device_uid
            )
        )
        if device is None:
            raise HTTPException(status_code=404, detail="配对设备不存在。")
        credential = secrets.token_urlsafe(48)
        device.credential_hash = _digest(credential)
        device.paired = True
        device.revoked = False
        device.paired_at = datetime.utcnow()
        session.consumed = True
        db.commit()
        return CompanionPairingPollResponse(
            status="PAIRED", device_id=device.device_uid, credential=credential
        )

    def authenticate(self, db: Session, device_uid: str, credential: str) -> CompanionDevice:
        device = db.scalar(
            select(CompanionDevice).where(CompanionDevice.device_uid == device_uid)
        )
        if (
            device is None
            or not device.paired
            or device.revoked
            or not device.credential_hash
            or not hmac.compare_digest(device.credential_hash, _digest(credential))
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="设备凭据无效或已撤销。",
            )
        device.last_seen_at = datetime.utcnow()
        db.commit()
        return device

    def challenge_for_pending(
        self, db: Session, device: CompanionDevice
    ) -> CompanionApprovalChallengeSchema | None:
        pending = action_set_service.pending(db)
        if pending is None:
            return None
        value = db.get(ActionSet, pending.id)
        if value is None or value.status != ActionSetStatus.PENDING:
            return None
        now = datetime.utcnow()
        version = _action_set_version(value)
        # Each snapshot gets a fresh challenge. Older unexpired challenges remain
        # valid so a display refresh cannot invalidate an in-progress long press.
        # The Action Set can still transition out of PENDING only once.
        nonce = secrets.token_urlsafe(32)
        challenge = CompanionApprovalChallenge(
            device_id=device.id,
            action_set_id=value.id,
            nonce_hash=_digest(nonce),
            action_set_version=version,
            expires_at=now + CHALLENGE_TTL,
        )
        db.add(challenge)
        db.commit()
        return CompanionApprovalChallengeSchema(
            action_set_id=value.id,
            nonce=nonce,
            action_set_version=version,
            expires_at=challenge.expires_at,
        )

    def consume_challenge(
        self,
        db: Session,
        device: CompanionDevice,
        action_set_id: int,
        nonce: str,
        action_set_version: str,
    ) -> None:
        now = datetime.utcnow()
        candidates = list(
            db.scalars(
                select(CompanionApprovalChallenge)
                .where(
                    CompanionApprovalChallenge.device_id == device.id,
                    CompanionApprovalChallenge.action_set_id == action_set_id,
                    CompanionApprovalChallenge.consumed.is_(False),
                    CompanionApprovalChallenge.expires_at > now,
                )
                .order_by(CompanionApprovalChallenge.id.desc())
            )
        )
        challenge = next(
            (
                item
                for item in candidates
                if hmac.compare_digest(item.nonce_hash, _digest(nonce))
            ),
            None,
        )
        value = db.get(ActionSet, action_set_id)
        if (
            challenge is None
            or value is None
            or value.status != ActionSetStatus.PENDING
            or challenge.action_set_version != action_set_version
            or _action_set_version(value) != action_set_version
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="确认已过期、已使用或方案内容已经变化，请刷新后重新确认。",
            )
        challenge.consumed = True
        challenge.consumed_at = now
        db.commit()

    @staticmethod
    def revoke(db: Session, device_uid: str) -> CompanionDevice:
        device = db.scalar(
            select(CompanionDevice).where(CompanionDevice.device_uid == device_uid)
        )
        if device is None:
            raise HTTPException(status_code=404, detail="设备不存在。")
        device.revoked = True
        device.credential_hash = None
        db.commit()
        db.refresh(device)
        return device

    @staticmethod
    def list_devices(db: Session) -> list[CompanionDevice]:
        return list(db.scalars(select(CompanionDevice).order_by(CompanionDevice.id.desc())))

    @staticmethod
    def _valid_pairing(db: Session, code: str) -> CompanionPairingSession:
        session = db.scalar(
            select(CompanionPairingSession).where(
                CompanionPairingSession.code == code,
                CompanionPairingSession.consumed.is_(False),
            )
        )
        if session is None or session.expires_at <= datetime.utcnow():
            raise HTTPException(status_code=410, detail="配对码不存在或已经过期。")
        return session


companion_service = CompanionService()
