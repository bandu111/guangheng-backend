from sqlalchemy.orm import Session

from app.modules.voice.models.voice_session import VoiceSession


class VoiceRepository:
    @staticmethod
    def save(db: Session, value: VoiceSession) -> VoiceSession:
        db.add(value)
        db.commit()
        db.refresh(value)
        return value


voice_repository = VoiceRepository()
