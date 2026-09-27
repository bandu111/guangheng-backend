from sqlalchemy.orm import Session

from app.modules.decision_context.services.decision_context_service import (
    decision_context_service,
)
from app.modules.device_registry.services.device_discovery_service import (
    device_discovery_service,
)
from app.modules.optimizer.schemas.optimizer_v2 import OptimizationDecisionV2Schema
from app.modules.optimizer.services.optimizer_v2_service import optimizer_v2_service


class OptimizerEvaluationService:
    async def evaluate(self, db: Session) -> OptimizationDecisionV2Schema:
        context = await decision_context_service.get_context(db=db)
        capability = None

        source = context.energy.source if context.energy else None
        if source is not None:
            try:
                discovery = await device_discovery_service.discover_devices()
            except Exception:
                discovery = None
            if discovery is not None:
                runtime = next(
                    (
                        item
                        for item in discovery.devices
                        if item.device_id == source.source_device_id
                    ),
                    None,
                )
                if runtime is not None:
                    capability = next(
                        (
                            item
                            for item in runtime.controls
                            if item.name == "backup_reserve"
                        ),
                        None,
                    )

        return optimizer_v2_service.optimize(
            context=context,
            capability=capability,
        )


optimizer_evaluation_service = OptimizerEvaluationService()
