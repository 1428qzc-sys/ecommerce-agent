"""
Shipping Service — 物流追踪
"""
from src.services.database import get_session, Shipment

# 物流状态：数据库存编码，对外展示用中文
SHIPMENT_STATUS_LABELS = {
    "in_transit": "运输中",
    "delivered": "已签收",
    "returned": "已退回",
}


def shipment_status_text(status: str) -> str:
    """把物流状态编码转成中文文案；未知编码原样返回，避免把空值吞掉"""
    return SHIPMENT_STATUS_LABELS.get(status, status)


class ShipmentInfo:
    def __init__(self, tracking_number, order_id, carrier, status, estimated_delivery, location):
        self.tracking_number = tracking_number
        self.order_id = order_id
        self.carrier = carrier
        self.status = status
        self.estimated_delivery = estimated_delivery
        self.location = location


class ShippingService:
    @staticmethod
    def _to_info(record) -> ShipmentInfo:
        """把数据库中的一条 Shipment 记录转成对外返回的结构"""
        return ShipmentInfo(
            tracking_number=record.tracking_number,
            order_id=record.order_id,
            carrier=record.carrier,
            status=record.status,
            estimated_delivery=record.estimated_delivery,
            location=record.location,
        )

    def track(self, tracking_number: str) -> ShipmentInfo | None:
        """根据物流单号查询物流信息"""
        session = get_session()
        record = session.query(Shipment).filter(Shipment.tracking_number == tracking_number).first()
        session.close()
        return self._to_info(record) if record else None

    def track_by_order(self, order_id: str) -> ShipmentInfo | None:
        """根据订单号查询物流信息（订单与物流是一对一关联）"""
        session = get_session()
        record = session.query(Shipment).filter(Shipment.order_id == order_id).first()
        session.close()
        return self._to_info(record) if record else None

    def get_readable_status(self, tracking_number: str) -> str:
        """获取可读的物流状态描述"""
        shipment = self.track(tracking_number)
        if not shipment:
            return "未找到该物流单号"
        status_map = {
            "in_transit": f"运输中，承运商：{shipment.carrier}。{shipment.location}",
            "delivered": f"已签收，承运商：{shipment.carrier}。{shipment.location}",
            "returned": f"已退回，承运商：{shipment.carrier}。",
        }
        result = status_map.get(shipment.status, f"状态：{shipment_status_text(shipment.status)}")
        if shipment.estimated_delivery and shipment.status == "in_transit":
            result += f" 预计送达：{shipment.estimated_delivery.strftime('%Y-%m-%d')}"
        return result
