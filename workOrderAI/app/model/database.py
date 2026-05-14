"""
MySQL数据库连接模块
提供数据库连接工厂函数，用于AI服务访问MySQL数据库
"""
import pymysql
from workOrderAI.utils.config import config

def get_db_connection():
    """
    获取数据库连接
    """
    return pymysql.connect(
        host=config['MySQL']['host'],
        port=config['MySQL']['port'],
        user=config['MySQL']['user'],
        password=config['MySQL']['password'],
        database=config['MySQL']['database'],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
    )
