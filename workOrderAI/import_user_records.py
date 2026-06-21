import csv
import sys
import uuid
from pathlib import Path

import pymysql

from workOrderAI.utils.config import config


BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "external" / "records.csv"

FIELD_MAPPING = {
    "用户ID": "owner_username",
    "特征": "feature",
    "清洁效率": "clean_efficiency",
    "耗材": "consumable",
    "对比": "comparison",
    "时间": "record_month",
}


def load_mysql_config():
    mysql_config = config.get("MySQL")
    if not mysql_config:
        raise ValueError("config.yaml missing MySQL config")
    return mysql_config


def connect_database(mysql_config):
    return pymysql.connect(
        host=mysql_config.get("host", "localhost"),
        port=int(mysql_config.get("port", 3306)),
        user=mysql_config.get("user", "root"),
        password=str(mysql_config.get("password", "")),
        database=mysql_config.get("database", "work_order"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def read_records():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV 文件不存在: {CSV_PATH}")

    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []
        missing_fields = [field for field in FIELD_MAPPING if field not in fieldnames]
        if missing_fields:
            raise ValueError(f"CSV 缺少字段: {', '.join(missing_fields)}")

        records = []
        for row in reader:
            records.append({
                db_field: (row.get(csv_field) or "").strip()
                for csv_field, db_field in FIELD_MAPPING.items()
            })
        return records


def ensure_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_records (
            id varchar(36) primary key,
            owner_username varchar(64) not null,
            feature text,
            clean_efficiency text,
            consumable text,
            comparison text,
            record_month varchar(32)
        )
    """)


def import_records(records):
    mysql_config = load_mysql_config()
    conn = connect_database(mysql_config)
    try:
        with conn.cursor() as cursor:
            ensure_table(cursor)
            cursor.execute("DELETE FROM user_records")
            if records:
                cursor.executemany(
                    """
                    INSERT INTO user_records (
                        id,
                        owner_username,
                        feature,
                        clean_efficiency,
                        consumable,
                        comparison,
                        record_month
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            str(uuid.uuid4()),
                            record["owner_username"],
                            record["feature"],
                            record["clean_efficiency"],
                            record["consumable"],
                            record["comparison"],
                            record["record_month"],
                        )
                        for record in records
                    ],
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    try:
        records = read_records()
        import_records(records)
        from workOrderAI.app.service.user_memory_service import UserMemoryService

        profile_count = UserMemoryService().rebuild_from_user_records()
    except Exception as exc:
        print(f"导入失败: {exc}", file=sys.stderr)
        return 1

    print(f"导入完成，共导入 {len(records)} 条记录，生成/刷新 {profile_count} 条用户画像。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
