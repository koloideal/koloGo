from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def new_session_maker(db_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        db_url,
        pool_size=10,
        max_overflow=10,
        connect_args={
            "timeout": 5,
        },
    )

    @event.listens_for(engine.sync_engine, "connect")
    def on_connect(dbapi_conn, connection_record):
        dbapi_conn.run_async(
            lambda conn: conn.set_type_codec(
                "numeric",
                encoder=str,
                decoder=float,
                schema="pg_catalog",
                format="text",
            )
        )

    return async_sessionmaker(engine, class_=AsyncSession, autoflush=False, expire_on_commit=False)
