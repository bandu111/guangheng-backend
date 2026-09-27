from sqlalchemy.orm import Session

from app.modules.autonomy.models.autonomy_config import (
    AutonomyConfig,
    AutonomyLevel,
)
from app.modules.autonomy.repositories.autonomy_config_repository import (
    autonomy_config_repository,
)
from app.modules.autonomy.schemas.autonomy_level import (
    AutonomyLevelOptionSchema,
    AutonomyLevelResponseSchema,
    AutonomyPermissionsSchema,
)
from app.modules.autonomy.services.autonomy_policy_service import autonomy_policy


class AutonomyLevelService:
    _options = (
        (AutonomyLevel.OBSERVE, "观察模式", "只读取和记录能源状态，不运行优化器。", True),
        (AutonomyLevel.SHADOW, "影子模式", "运行优化器并记录建议，但不创建执行方案。", True),
        (AutonomyLevel.CONFIRM, "确认模式", "允许创建待确认方案，用户批准后才能执行。", True),
        (
            AutonomyLevel.AUTO,
            "完全访问",
            "允许完整分析与主动提案；设备写入仍受 Safety 与批准流程保护。",
            True,
        ),
    )

    @staticmethod
    def permissions(level: AutonomyLevel) -> AutonomyPermissionsSchema:
        return AutonomyPermissionsSchema(
            observe=True,
            optimize=level in {
                AutonomyLevel.SHADOW,
                AutonomyLevel.CONFIRM,
                AutonomyLevel.AUTO,
            },
            propose=level in {AutonomyLevel.CONFIRM, AutonomyLevel.AUTO},
            # V1 Safety always requires explicit approval. No level bypasses it.
            execute_without_approval=False,
        )

    def get_current_model(self, db: Session) -> AutonomyConfig:
        config = autonomy_config_repository.get_current(db)
        if config is not None:
            return config
        try:
            default_level = AutonomyLevel(autonomy_policy.default_level)
        except ValueError:
            default_level = AutonomyLevel.CONFIRM
        return autonomy_config_repository.save(
            db, AutonomyConfig(level=default_level)
        )

    def get_level(self, db: Session) -> AutonomyLevel:
        return self.get_current_model(db).level

    def get(self, db: Session) -> AutonomyLevelResponseSchema:
        config = self.get_current_model(db)
        return self._response(config)

    def update(
        self, db: Session, level: AutonomyLevel
    ) -> AutonomyLevelResponseSchema:
        config = self.get_current_model(db)
        config.level = level
        return self._response(autonomy_config_repository.save(db, config))

    def _response(self, config: AutonomyConfig) -> AutonomyLevelResponseSchema:
        return AutonomyLevelResponseSchema(
            level=config.level,
            permissions=self.permissions(config.level),
            options=[
                AutonomyLevelOptionSchema(
                    level=level,
                    label=label,
                    description=description,
                    available=available,
                    permissions=self.permissions(level),
                )
                for level, label, description, available in self._options
            ],
            updated_at=config.updated_at,
        )


autonomy_level_service = AutonomyLevelService()
