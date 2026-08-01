"""Alembic 迁移环境配置。"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ⭐⭐ 最关键的一行:导入所有模型
#    这一句让 app/models/__init__.py 里的所有模型被加载,
#    从而注册到 Base.metadata。缺了它,autogenerate 检测不到任何表,生成【空迁移】!
#    # noqa: F401 = 告诉代码检查工具"我知道这个 import 没直接使用,别报警告"
#    (它的作用是"触发导入的副作用",不是拿来调用的)
from app import models  # noqa: F401
from app.core.config import settings      # 复用应用配置单例
from app.core.database import Base         # 你那个 DeclarativeBase


# Alembic 的配置对象(读取 alembic.ini)
config = context.config

# ⭐ 动态设置数据库连接串:用【同步】URL,不是异步的
#    .replace("%", "%%") 是转义:alembic.ini 底层用 ConfigParser 解析,
#    % 是它的特殊字符。如果你密码里含 %,不转义会解析报错。
#    写成 %% 才能被正确还原成一个 %
config.set_main_option(
    "sqlalchemy.url",
    settings.DATABASE_URL_SYNC.replace("%", "%%"),
)

# 如果 alembic.ini 里配了日志,就加载日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ⭐ 目标结构:告诉 Alembic "数据库应该长成 Base.metadata 描述的样子"
#    autogenerate 就是拿它和数据库现状做对比
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式:只生成 SQL 脚本,不连接数据库。"""

    # ⭐ 离线模式的用途:alembic upgrade head --sql
    #    生成纯 SQL 文本给 DBA 审核 / 手动在生产执行,而不直接连库
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,                       # ⭐ 把参数值直接【写死】进 SQL
                                                  #    (在线模式用占位符 ?,离线模式没有连接,必须写实际值)
        dialect_opts={"paramstyle": "named"},
        compare_type=True,                        # ⭐ 检测列【类型】变化(如 VARCHAR(50)→VARCHAR(100))
        compare_server_default=True,              # ⭐ 检测【服务器默认值】变化
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式:真正连接数据库并执行迁移。"""

    # ⭐ 这是最常用的模式(alembic upgrade head 走的就是这里)
    #    创建一个数据库引擎
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,                  # ⭐ 用 NullPool = 【不用连接池】
                                                  #    迁移是一次性任务,建一条连接用完即关,
                                                  #    不需要连接池那套复用机制
    )

    # 建立连接并执行迁移
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,                    # 同上:检测类型变化
            compare_server_default=True,          # 同上:检测默认值变化
        )

        with context.begin_transaction():
            context.run_migrations()              # 真正执行 versions/ 里的迁移


# ⭐ 入口:根据运行模式二选一
#    context.is_offline_mode() 由命令行参数 --sql 决定
if context.is_offline_mode():
    run_migrations_offline()      # 带 --sql → 只生成 SQL
else:
    run_migrations_online()       # 默认 → 连库执行
