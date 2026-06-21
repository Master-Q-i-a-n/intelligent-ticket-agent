import json
import re
import uuid
from datetime import datetime, timedelta

from workOrderAI.app.model.database import get_db_connection
from workOrderAI.utils.config import config
from workOrderAI.utils.logger_handler import logger


MEMORY_KEY_TYPES = {
    "device_model": "DEVICE",
    "floor_type": "ENVIRONMENT",
    "home_size": "ENVIRONMENT",
    "pet": "ENVIRONMENT",
    "cleaning_preference": "PREFERENCE",
    "recurring_issue": "RECURRING_ISSUE",
}
SOURCE_PRIORITY = {"EXPLICIT_USER": 4, "USER_RECORD": 3, "TICKET": 2, "INFERENCE": 1}


class UserMemoryService:
    """Stores small, auditable user facts in MySQL with expiry and conflict handling."""

    def list_active(self, owner_username: str, limit: int | None = None) -> list[dict]:
        owner_username = str(owner_username or "").strip()
        if not owner_username:
            return []
        self._ensure_table()
        selected_limit = int(limit or config.get("memory", {}).get("profile_limit", 5))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select id, memory_type, memory_key, memory_value, source_type, source_id,
                           confidence, importance, expires_at, last_confirmed_at
                    from wo_user_memory_item
                    where owner_username=%s and status='ACTIVE'
                      and (expires_at is null or expires_at='' or expires_at>%s)
                    order by importance desc, confidence desc, last_confirmed_at desc
                    limit %s
                    """,
                    (owner_username, now, selected_limit),
                )
                return list(cursor.fetchall() or [])
        finally:
            conn.close()

    def upsert_candidates(
        self,
        owner_username: str,
        candidates: list[dict],
        source_type: str,
        source_id: str,
        source_reply_id: str,
        extraction_batch_id: str,
    ) -> int:
        owner_username = str(owner_username or "").strip()
        source_type = str(source_type or "INFERENCE").strip().upper()
        threshold = float(config.get("memory", {}).get("extraction_confidence_threshold", 0.8))
        if not owner_username or source_type not in SOURCE_PRIORITY:
            return 0

        self._ensure_table()
        stored = 0
        for candidate in candidates or []:
            key = str(candidate.get("memory_key") or "").strip()
            value = str(candidate.get("memory_value") or "").strip()
            confidence = self._as_float(candidate.get("confidence"), 0.0)
            importance = self._as_float(candidate.get("importance"), confidence)
            if key not in MEMORY_KEY_TYPES or not value or confidence < threshold:
                continue
            if self._upsert_one(
                owner_username,
                MEMORY_KEY_TYPES[key],
                key,
                value,
                source_type,
                source_id,
                source_reply_id,
                extraction_batch_id,
                confidence,
                importance,
            ):
                stored += 1
        return stored

    def rebuild_from_user_records(self) -> int:
        self._ensure_table()
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "select owner_username, feature, record_month from user_records order by owner_username, record_month"
                )
                rows = list(cursor.fetchall() or [])
                # 导入数据是完整快照，先替换旧的派生画像，避免相同批次键与历史撤销记录冲突。
                cursor.execute("delete from wo_user_memory_item where source_type='USER_RECORD'")
            conn.commit()
        finally:
            conn.close()

        stored = 0
        for row in rows:
            candidates = self._profile_candidates_from_feature(row.get("feature"))
            stored += self.upsert_candidates(
                str(row.get("owner_username") or ""),
                candidates,
                "USER_RECORD",
                str(row.get("record_month") or ""),
                "",
                f"records-{row.get('owner_username')}-{row.get('record_month')}",
            )
        logger.info("[user-memory] rebuilt profiles rows=%s stored=%s", len(rows), stored)
        return stored

    def expire_due(self) -> int:
        self._ensure_table()
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    update wo_user_memory_item set status='EXPIRED', updated_at=%s
                    where status='ACTIVE' and expires_at is not null and expires_at<>'' and expires_at<=%s
                    """,
                    (self._now(), self._now()),
                )
                count = cursor.rowcount
            conn.commit()
            return count
        finally:
            conn.close()

    def revoke_all(self, owner_username: str) -> int:
        self._ensure_table()
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "update wo_user_memory_item set status='REVOKED', updated_at=%s where owner_username=%s and status='ACTIVE'",
                    (self._now(), owner_username),
                )
                count = cursor.rowcount
            conn.commit()
            return count
        finally:
            conn.close()

    def _upsert_one(
        self,
        owner_username: str,
        memory_type: str,
        key: str,
        value: str,
        source_type: str,
        source_id: str,
        source_reply_id: str,
        extraction_batch_id: str,
        confidence: float,
        importance: float,
    ) -> bool:
        now = self._now()
        expires_at = (datetime.now() + timedelta(days=self._ttl_days(memory_type))).strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select id from wo_user_memory_item
                    where owner_username=%s and memory_key=%s and source_reply_id=%s and extraction_batch_id=%s
                    """,
                    (owner_username, key, source_reply_id or "", extraction_batch_id),
                )
                if cursor.fetchone():
                    return False

                cursor.execute(
                    """
                    select id, memory_value, source_type, version from wo_user_memory_item
                    where owner_username=%s and memory_key=%s and status='ACTIVE'
                    order by updated_at desc limit 1
                    """,
                    (owner_username, key),
                )
                existing = cursor.fetchone()
                if existing and str(existing.get("memory_value") or "") == value:
                    cursor.execute(
                        """
                        update wo_user_memory_item
                        set confidence=greatest(confidence,%s), importance=greatest(importance,%s),
                            last_confirmed_at=%s, expires_at=%s, updated_at=%s, version=version+1
                        where id=%s
                        """,
                        (confidence, importance, now, expires_at, now, existing["id"]),
                    )
                    conn.commit()
                    return True

                if existing and SOURCE_PRIORITY.get(source_type, 0) < SOURCE_PRIORITY.get(str(existing.get("source_type") or ""), 0):
                    return False

                memory_id = "um-" + uuid.uuid4().hex[:16]
                cursor.execute(
                    """
                    insert into wo_user_memory_item
                    (id, owner_username, memory_type, memory_key, memory_value, source_type, source_id,
                     source_reply_id, extraction_batch_id, confidence, importance, status, valid_from,
                     expires_at, last_confirmed_at, superseded_by, version, created_at, updated_at)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'ACTIVE',%s,%s,%s,'',1,%s,%s)
                    """,
                    (
                        memory_id,
                        owner_username,
                        memory_type,
                        key,
                        value,
                        source_type,
                        source_id,
                        source_reply_id or "",
                        extraction_batch_id,
                        confidence,
                        importance,
                        now,
                        expires_at,
                        now,
                        now,
                        now,
                    ),
                )
                if existing:
                    cursor.execute(
                        "update wo_user_memory_item set status='SUPERSEDED', superseded_by=%s, updated_at=%s where id=%s",
                        (memory_id, now, existing["id"]),
                    )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _profile_candidates_from_feature(self, feature: object) -> list[dict]:
        text = str(feature or "").strip()
        candidates = []
        size_match = re.search(r"(\d+)\s*㎡", text)
        if size_match:
            candidates.append(self._candidate("home_size", size_match.group(1) + "㎡"))
        floor_terms = ["木地板", "复合地板", "仿实木", "瓷砖", "防滑砖", "通体砖", "大理石", "短毛地毯", "混合地面"]
        floors = [term for term in floor_terms if term in text]
        if floors:
            candidates.append(self._candidate("floor_type", "、".join(floors)))
        pet_match = re.search(r"(\d+\s*只?\s*[猫狗]|养宠|宠物)", text)
        if pet_match:
            candidates.append(self._candidate("pet", pet_match.group(1)))
        return candidates

    def _candidate(self, key: str, value: str) -> dict:
        return {"memory_key": key, "memory_value": value, "confidence": 0.95, "importance": 0.8}

    def _ttl_days(self, memory_type: str) -> int:
        memory_config = config.get("memory", {})
        if memory_type in {"DEVICE", "ENVIRONMENT"}:
            return int(memory_config.get("device_environment_ttl_days", 365))
        if memory_type == "PREFERENCE":
            return int(memory_config.get("preference_ttl_days", 180))
        return int(memory_config.get("recurring_issue_ttl_days", 90))

    def _ensure_table(self) -> None:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    create table if not exists wo_user_memory_item (
                      id varchar(36) primary key,
                      owner_username varchar(64) not null,
                      memory_type varchar(32) not null,
                      memory_key varchar(64) not null,
                      memory_value text not null,
                      source_type varchar(32) not null,
                      source_id varchar(128) not null default '',
                      source_reply_id varchar(36) not null default '',
                      extraction_batch_id varchar(128) not null,
                      confidence double not null,
                      importance double not null,
                      status varchar(32) not null,
                      valid_from varchar(19) not null,
                      expires_at varchar(19),
                      last_confirmed_at varchar(19) not null,
                      superseded_by varchar(36) not null default '',
                      version int not null default 1,
                      created_at varchar(19) not null,
                      updated_at varchar(19) not null,
                      unique key uk_user_memory_source (owner_username, memory_key, source_reply_id, extraction_batch_id),
                      key idx_user_memory_active (owner_username, status, memory_key)
                    )
                    """
                )
            conn.commit()
        finally:
            conn.close()

    def _as_float(self, value: object, fallback: float) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return fallback

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def format_user_profile(items: list[dict]) -> str:
    return "\n".join(
        f"- {item.get('memory_key')}：{item.get('memory_value')}（来源：{item.get('source_type')}）"
        for item in items or []
        if item.get("memory_key") and item.get("memory_value")
    )
