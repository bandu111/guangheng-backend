from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.device_registry.models.device import Device


class DeviceRepository:

    def get_by_source_device_id(
        self,
        db: Session,
        source_device_id: str,
    ) -> Device | None:
        statement = select(Device).where(
            Device.source_device_id == source_device_id
        )

        return db.scalar(statement)

    def create(
        self,
        db: Session,
        device: Device,
    ) -> Device:
        db.add(device)
        db.commit()
        db.refresh(device)

        return device

    def update(
        self,
        db: Session,
        device: Device,
    ) -> Device:
        db.add(device)
        db.commit()
        db.refresh(device)

        return device

    def get_all(self,db:Session)-> list[Device]:
        statement = (
            select(Device)
            .order_by(Device.id.asc())
        )
        return list(
            db.scalars(statement).all()
        )

    def get_by_id(
            self,
            db: Session,
            device_id: int,
    ) -> Device | None:
        return db.get(
            Device,
            device_id,
        )



device_repository = DeviceRepository()