"""
Returns Service — 退货处理
"""
import uuid
from datetime import datetime

# 退货单状态：数据库存编码，对外展示用中文
RETURN_STATUS_LABELS = {
    "pending": "待审核",
    "approved": "已通过",
    "rejected": "已驳回",
    "completed": "已完成",
}


class ReturnInfo:
    def __init__(self, rma_number, order_id, status, reason, refund_amount, created_at):
        self.rma_number = rma_number
        self.order_id = order_id
        self.status = status
        self.reason = reason
        self.refund_amount = refund_amount
        self.created_at = created_at


def return_status_text(status: str) -> str:
    """把退货单状态编码转成中文文案；未知编码原样返回，避免把空值吞掉"""
    return RETURN_STATUS_LABELS.get(status, status)


class ReturnsService:
    def get_policy(self) -> str:
        return (
            "本店支持签收后14天内退货。商品需保持原样，吊牌未拆。"
            "退款将在收到退货后5-7个工作日内处理。"
            "质量问题商品提供免费退货物流。"
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
