import asyncio
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.modules.action_set.models.action_set import (
    ActionSet,
    ActionSetItem,
    ActionSetItemStatus,
    ActionSetStatus,
    ActionSetVerificationStatus,
)
from app.modules.action_set.repositories.action_set_repository import action_set_repository
from app.modules.action_set.schemas.action_set import ActionSetItemSchema, ActionSetSchema
from app.modules.device_registry.repositories.device_repository import device_repository
from app.modules.execution.models.execution import ExecutionStatus
from app.modules.household_graph.services.household_graph_service import household_graph_service
from app.modules.proposal.models.proposal import ProposalStatus
from app.modules.proposal.services.proposal_service import proposal_service


class ActionSetNotFoundError(Exception):
    pass


class InvalidActionSetStateError(Exception):
    pass


class ActionSetOpportunityUnavailableError(Exception):
    pass


class ActionSetService:
    def response(self, db: Session, value: ActionSet) -> ActionSetSchema:
        result = ActionSetSchema.model_validate(value)
        return result.model_copy(
            update={
                "items": [
                    ActionSetItemSchema.model_validate(item)
                    for item in action_set_repository.items(db, value.id)
                ]
            }
        )

    def get(self, db: Session, action_set_id: int) -> ActionSetSchema:
        value = action_set_repository.get(db, action_set_id)
        if value is None:
            raise ActionSetNotFoundError(f"Action set not found: {action_set_id}")
        return self.response(db, value)

    def list(self, db: Session) -> list[ActionSetSchema]:
        return [self.response(db, item) for item in action_set_repository.list(db)]

    def pending(self, db: Session) -> ActionSetSchema | None:
        value = action_set_repository.get_pending(db)
        return self.response(db, value) if value else None

    async def generate(
        self,
        db: Session,
        opportunity_code: str = "SOLAR_SURPLUS_SELF_CONSUMPTION",
    ) -> ActionSetSchema:
        existing = action_set_repository.get_pending(db)
        if existing is not None:
            return self.response(db, existing)

        graph = await household_graph_service.get_current()
        opportunity = next(
            (item for item in graph.opportunities if item.code == opportunity_code), None
        )
        if opportunity is None:
            raise ActionSetOpportunityUnavailableError(
                "当前实时家庭能源状态中没有可执行的跨设备机会。"
            )
        if not graph.meter_ground_truth or graph.grid_power_w is None:
            raise ActionSetOpportunityUnavailableError(
                "Smart Meter 实时总表数据不可用，不能创建需要统一验证的协同方案。"
            )

        value = action_set_repository.save(
            db,
            ActionSet(
                opportunity_code=opportunity.code,
                title=opportunity.title,
                reason=opportunity.reason,
                status=ActionSetStatus.PENDING,
                expected_grid_delta_w=opportunity.expected_grid_delta_w,
                verification_status=ActionSetVerificationStatus.PENDING,
            ),
        )

        try:
            for sequence, action in enumerate(opportunity.actions, start=1):
                device = device_repository.get_by_source_device_id(db, action.device_id)
                if device is None:
                    raise ActionSetOpportunityUnavailableError(
                        f"协同动作设备尚未绑定：{action.device_id}"
                    )
                if action.capability == "power_switch":
                    proposal = await proposal_service.create_smart_plug_proposal(
                        db, device.id, action.target_value >= 0.5
                    )
                else:
                    proposal = await proposal_service.create_device_control_proposal(
                        db, device.id, action.capability, action.target_value
                    )
                proposal.reason_code = opportunity.code
                proposal.reason = (
                    f"协同方案 #{value.id}：{opportunity.reason}"
                )
                proposal_service.get(db, proposal.id)
                db.add(proposal)
                db.commit()
                db.refresh(proposal)
                action_set_repository.save(
                    db,
                    ActionSetItem(
                        action_set_id=value.id,
                        sequence=sequence,
                        device_id=device.id,
                        source_device_id=device.source_device_id,
                        device_name=device.display_name or device.model,
                        capability=action.capability,
                        current_value=proposal.current_value,
                        target_value=proposal.target_value,
                        expected_delta_w=action.expected_delta_w,
                        proposal_id=proposal.id,
                        status=ActionSetItemStatus.PENDING,
                    ),
                )
        except Exception as exc:
            value.status = ActionSetStatus.BLOCKED
            value.error_code = "ACTION_SET_GENERATION_FAILED"
            value.error_message = str(exc)
            value.completed_at = datetime.utcnow()
            action_set_repository.save(db, value)
            raise
        return self.response(db, value)

    def approve(self, db: Session, action_set_id: int) -> ActionSetSchema:
        value = action_set_repository.get(db, action_set_id)
        if value is None:
            raise ActionSetNotFoundError(f"Action set not found: {action_set_id}")
        if value.status != ActionSetStatus.PENDING:
            raise InvalidActionSetStateError("只有等待确认的协同方案可以批准。")
        value.status = ActionSetStatus.APPROVED
        value.approved_at = datetime.utcnow()
        action_set_repository.save(db, value)
        return self.response(db, value)

    def reject(self, db: Session, action_set_id: int) -> ActionSetSchema:
        value = action_set_repository.get(db, action_set_id)
        if value is None:
            raise ActionSetNotFoundError(f"Action set not found: {action_set_id}")
        if value.status != ActionSetStatus.PENDING:
            raise InvalidActionSetStateError("只有等待确认的协同方案可以暂不执行。")
        for item in action_set_repository.items(db, value.id):
            proposal = proposal_service.get(db, item.proposal_id)
            if proposal.status == ProposalStatus.PENDING:
                proposal_service.reject(db, proposal.id)
            item.status = ActionSetItemStatus.REJECTED
            item.result_code = "USER_REJECTED"
            item.result_message = "用户暂不执行本次协同方案。"
            action_set_repository.save(db, item)
        value.status = ActionSetStatus.REJECTED
        value.rejected_at = datetime.utcnow()
        value.completed_at = datetime.utcnow()
        return self.response(db, action_set_repository.save(db, value))

    async def execute_approved(self, action_set_id: int) -> None:
        """Execute child proposals in order after one user approval.

        Every item still enters the existing Proposal -> Safety -> Execution ->
        Readback chain. A failed item stops later items. Physical-device writes
        are not transactionally reversible, so no unverified automatic rollback
        is attempted.
        """
        db = SessionLocal()
        try:
            value = action_set_repository.get(db, action_set_id)
            if value is None or value.status != ActionSetStatus.APPROVED:
                return
            try:
                before = await household_graph_service.get_current()
            except Exception as exc:
                value.status = ActionSetStatus.BLOCKED
                value.verification_status = ActionSetVerificationStatus.UNAVAILABLE
                value.error_code = "METER_OBSERVATION_FAILED"
                value.error_message = str(exc)
                value.completed_at = datetime.utcnow()
                action_set_repository.save(db, value)
                return
            if not before.meter_ground_truth or before.grid_power_w is None:
                value.status = ActionSetStatus.BLOCKED
                value.verification_status = ActionSetVerificationStatus.UNAVAILABLE
                value.error_code = "METER_GROUND_TRUTH_UNAVAILABLE"
                value.error_message = "执行前 Smart Meter 总表数据不可用。"
                value.completed_at = datetime.utcnow()
                action_set_repository.save(db, value)
                return

            value.before_grid_power_w = before.grid_power_w
            value.status = ActionSetStatus.EXECUTING
            value.started_at = datetime.utcnow()
            action_set_repository.save(db, value)

            succeeded = 0
            failed = False
            items = action_set_repository.items(db, value.id)
            for item in items:
                if failed:
                    proposal = proposal_service.get(db, item.proposal_id)
                    if proposal.status == ProposalStatus.PENDING:
                        proposal_service.reject(db, proposal.id)
                    item.status = ActionSetItemStatus.SKIPPED
                    item.result_code = "PREVIOUS_ACTION_FAILED"
                    item.result_message = "前序动作未通过，已停止后续设备写入。"
                    action_set_repository.save(db, item)
                    continue

                item.status = ActionSetItemStatus.EXECUTING
                action_set_repository.save(db, item)
                try:
                    result = await proposal_service.approve(db, item.proposal_id)
                except Exception as exc:
                    item.status = ActionSetItemStatus.FAILED
                    item.result_code = "ACTION_EXECUTION_EXCEPTION"
                    item.result_message = str(exc)
                    failed = True
                else:
                    item.execution_id = result.execution.id if result.execution else None
                    if result.proposal.status == ProposalStatus.SUCCEEDED and (
                        result.execution is not None
                        and result.execution.status == ExecutionStatus.SUCCEEDED
                    ):
                        item.status = ActionSetItemStatus.SUCCEEDED
                        item.result_code = "READBACK_VERIFIED"
                        item.result_message = "设备写入与状态回读一致。"
                        succeeded += 1
                    else:
                        item.status = (
                            ActionSetItemStatus.BLOCKED
                            if result.proposal.status == ProposalStatus.BLOCKED
                            else ActionSetItemStatus.FAILED
                        )
                        item.result_code = (
                            result.proposal.error_code
                            or (result.execution.error_code if result.execution else None)
                            or "ACTION_NOT_VERIFIED"
                        )
                        item.result_message = (
                            result.proposal.error_message
                            or (result.execution.error_message if result.execution else None)
                            or "设备动作未完成回读验证。"
                        )
                        failed = True
                action_set_repository.save(db, item)

            value = action_set_repository.get(db, value.id)
            threshold = max(
                50.0,
                min(200.0, float(value.expected_grid_delta_w or 0) * 0.25),
            )
            after = None
            observation_error = None
            # Device control readback may update before the Smart Meter entity's
            # next integration poll. Re-observe for a bounded window instead of
            # declaring a false verification failure from the first stale meter
            # sample. Every attempt is a fresh HA REST discovery.
            for attempt in range(7):
                if attempt:
                    await asyncio.sleep(2)
                try:
                    candidate = await household_graph_service.get_current()
                except Exception as exc:
                    observation_error = exc
                    continue
                if candidate.meter_ground_truth and candidate.grid_power_w is not None:
                    after = candidate
                    delta = candidate.grid_power_w - value.before_grid_power_w
                    if delta >= threshold or failed:
                        break
            if after is None:
                value.verification_status = ActionSetVerificationStatus.UNAVAILABLE
                value.verification_message = (
                    "设备动作已完成，但验证时窗内未取得 Smart Meter 总表数据。"
                    + (f" {observation_error}" if observation_error else "")
                )
            else:
                value.after_grid_power_w = after.grid_power_w
                value.actual_grid_delta_w = after.grid_power_w - value.before_grid_power_w
                if not failed and value.actual_grid_delta_w >= threshold:
                    value.verification_status = ActionSetVerificationStatus.VERIFIED
                    value.verification_message = (
                        f"Smart Meter 已验证电网反送减少约 "
                        f"{value.actual_grid_delta_w:.0f} W。"
                    )
                else:
                    value.verification_status = ActionSetVerificationStatus.NOT_VERIFIED
                    value.verification_message = (
                        "设备动作未全部成功，或 Smart Meter 前后变化未达到验证阈值。"
                    )

            if failed:
                value.status = ActionSetStatus.PARTIAL if succeeded else ActionSetStatus.BLOCKED
                value.error_code = "ACTION_SET_PARTIALLY_EXECUTED" if succeeded else "ACTION_SET_BLOCKED"
                value.error_message = "协同方案未全部完成，后续动作已停止。"
            elif value.verification_status == ActionSetVerificationStatus.VERIFIED:
                value.status = ActionSetStatus.SUCCEEDED
            else:
                value.status = ActionSetStatus.PARTIAL
                value.error_code = "UNIFIED_VERIFICATION_FAILED"
                value.error_message = "子动作已完成，但统一总表验证未通过。"
            value.completed_at = datetime.utcnow()
            action_set_repository.save(db, value)
        finally:
            db.close()


action_set_service = ActionSetService()
