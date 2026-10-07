"""
Session Service — 后端会话记忆

职责：把多轮对话历史放在后端维护，前端只需要传 session_id 和当轮消息。

为什么不让前端传 history：
    多轮上下文的组装权应该放在后端。工具调用过程中会产生 tool 角色的中间消息，
    这类消息必须紧跟在发起调用的 assistant 消息之后，顺序不能被打乱。
    如果由前端整包回传历史，一旦这类中间消息被混进来或顺序被打散，
    后端拼出来的上下文就无法满足这个约束。

    放到后端以后，工具结果统一合并进 AI 回复的 content，不再单独保留工具消息，
    只持久化 human / ai 两种角色，消息顺序完全由后端控制，从根上避免这个问题。

存储选型：独立的 SQLite 库（sessions.db），与业务库 ecommerce.db 分开。
    - 业务库 init_db() 每次启动会 drop_all 重建，会话历史不能跟着被清空
    - 后续要换 Redis 只需要替换本模块的实现，上层无感知
"""
import logging
import os
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

# ── 独立的会话库，不参与业务库的 drop_all ────────────────────
SESSION_DB_PATH = os.path.join(os.path.dirname(__file__), "sessions.db")
engine = create_engine(f"sqlite:///{SESSION_DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)
SessionBase = declarative_base()


class ChatMessage(SessionBase):
    """一条对话消息（只存 human / ai 两种角色）"""
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True)
    session_id = Column(String, index=True, nullable=False)
    # 会话内自增序号：同一轮的两条消息时间戳可能完全相同，
    # 靠时间戳排序会乱序，所以用序号保证"先说的在前"
    seq = Column(Integer, nullable=False, index=True)
    role = Column(String, nullable=False)        # human / ai
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# 建表（幂等，已存在则跳过）
SessionBase.metadata.create_all(engine)


# ── 对外接口 ────────────────────────────────────────────────
def load_history(session_id: str, max_turns: int = 10) -> list[dict]:
    """
    读取某个会话最近 max_turns 轮对话，按时间正序返回。

    只返回 human / ai 消息，且已经是正确的时间顺序 ——
    这样调用方按顺序拼进 messages 就一定符合接口要求。
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.seq.desc())
            .limit(max_turns * 2)
            .all()
        )
        # 上面是按序号倒序取（拿到最近几条），这里翻转成正序（先说的在前）
        return [{"role": r.role, "content": r.content} for r in reversed(rows)]
    except Exception as e:
        logger.warning("Load session history failed: %s", e)
        return []
    finally:
        db.close()


def save_turn(session_id: str, user_message: str, assistant_message: str) -> None:
    """
    把一轮完整对话（用户一句 + 助手一句）写入存储。

    注意：只存这两个角色。工具调用产生的中间消息不落库，
    因为下一轮重新拼装时它们既没用又会破坏消息顺序约束。
    """
    db = SessionLocal()
    try:
        # 接在当前会话最后一条消息后面编号
        last_seq = db.query(func.max(ChatMessage.seq)).filter(
            ChatMessage.session_id == session_id
        ).scalar() or 0
        now = datetime.utcnow()
        db.add_all([
            ChatMessage(
                id=uuid.uuid4().hex,
                session_id=session_id,
                seq=last_seq + 1,
                role="human",
                content=user_message,
                created_at=now,
            ),
            ChatMessage(
                id=uuid.uuid4().hex,
                session_id=session_id,
                seq=last_seq + 2,
                role="ai",
                content=assistant_message,
                created_at=now,
            ),
        ])
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("Save session turn failed: %s", e)
    finally:
        db.close()


def clear_session(session_id: str) -> int:
    """清空某个会话的历史，返回被删除的条数"""
    db = SessionLocal()
    try:
        deleted = db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).delete()
        db.commit()
        return deleted
    except Exception as e:
        db.rollback()
        logger.warning("Clear session failed: %s", e)
        return 0
    finally:
        db.close()
