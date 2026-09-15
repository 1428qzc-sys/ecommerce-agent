"""
Returns Service — 退货处理
"""
import uuid
from datetime import datetime


class ReturnInfo:
    def __init__(self, rma_number, order_id, status, reason, refund_amount, created_at):
        self.rma_number = rma_number
        self.order_id = order_id
        self.status = status
        self.reason = reason
        self.refund_amount = refund_amount
        self.created_at = created_at


class ReturnsService:
    def get_policy(self) -> str:
        return (
            "Our return policy allows returns within 14 days of delivery. "
            "Items must be in original condition with tags attached. "
            "Refunds are processed within 5-7 business days after we receive the returned item. "
            "Free return shipping is provided for defective items."
        )

    def create_return(self, order_id: str, reason: str, refund_amount: float) -> ReturnInfo:
        """创建退货申请，生成 RMA 编号"""
        rma = f"RMA-{uuid.uuid4().hex[:8].upper()}"
        return ReturnInfo(
            rma_number=rma,
            order_id=order_id,
            status="approved",
            reason=reason,
            refund_amount=refund_amount,
            created_at=datetime.utcnow(),
        )
