"""Durable subscriptions and delivery leases. Never log chat IDs or credentials."""

import os
import threading

_store = None
_lock = threading.Lock()


def enabled() -> bool:
    return bool(os.environ.get("YDB_ENDPOINT") and os.environ.get("YDB_DATABASE"))


def get_store():
    global _store
    with _lock:
        if _store is None:
            import ydb

            driver = ydb.Driver(endpoint=os.environ["YDB_ENDPOINT"],
                                database=os.environ["YDB_DATABASE"],
                                credentials=ydb.iam.MetadataUrlCredentials())
            driver.wait(timeout=5, fail_fast=True)
            _store = SubscriberStore(driver)
    return _store


class SubscriberStore:
    def __init__(self, driver):
        import ydb

        self.ydb = ydb
        self.pool = ydb.SessionPool(driver, size=4)

    def run(self, callee):
        return self.pool.retry_operation_sync(
            callee, self.ydb.RetrySettings(max_retries=2, max_session_acquire_timeout=3),
        )

    def execute(self, session, tx, query, params=None, commit=True):
        prepared = session.prepare(query)
        return tx.execute(prepared, params or {}, commit_tx=commit,
                          settings=self.ydb.BaseRequestSettings().with_timeout(4))

    def subscribe(self, chat_id: int, now: int):
        def operation(session):
            with session.transaction() as tx:
                rows = self.execute(session, tx,
                                    "DECLARE $id AS Int64; SELECT active FROM subscribers "
                                    "WHERE chat_id=$id;", {"$id": chat_id}, False)[0].rows
                if rows and rows[0].active:
                    tx.commit()
                    return
                query = (
                    "DECLARE $id AS Int64; DECLARE $now AS Int64; "
                    "UPSERT INTO subscribers (chat_id, active, subscribed_at) "
                    "VALUES ($id, true, $now);"
                ) if rows else (
                    "DECLARE $id AS Int64; DECLARE $now AS Int64; "
                    "UPSERT INTO subscribers "
                    "(chat_id, active, subscribed_at, sent_week, lease_until, owner, next_attempt) "
                    'VALUES ($id, true, $now, "", 0, "", 0);'
                )
                self.execute(session, tx, query, {"$id": chat_id, "$now": now})
        self.run(operation)

    def unsubscribe(self, chat_id: int):
        self.run(lambda session: self.execute(session, session.transaction(),
                 "DECLARE $id AS Int64; UPDATE subscribers SET active=false WHERE chat_id=$id;",
                 {"$id": chat_id}))

    def due(self, week: str, cutoff: int, now: int):
        return self.run(lambda session: [row.chat_id for row in self.execute(
            session, session.transaction(),
            "DECLARE $week AS Utf8; DECLARE $cutoff AS Int64; DECLARE $now AS Int64; "
            "SELECT chat_id FROM subscribers WHERE active=true AND subscribed_at <= $cutoff "
            "AND sent_week != $week AND lease_until <= $now AND next_attempt <= $now "
            "ORDER BY chat_id LIMIT 50;",
            {"$week": week, "$cutoff": cutoff, "$now": now},
        )[0].rows])

    def claim(self, chat_id: int, week: str, cutoff: int, now: int, owner: str):
        def operation(session):
            with session.transaction() as tx:
                rows = self.execute(session, tx,
                                    "DECLARE $id AS Int64; SELECT * FROM subscribers "
                                    "WHERE chat_id=$id;", {"$id": chat_id}, False)[0].rows
                if not rows or not rows[0].active or rows[0].subscribed_at > cutoff:
                    tx.commit()
                    return False
                row = rows[0]
                if row.sent_week == week or row.lease_until > now or row.next_attempt > now:
                    tx.commit()
                    return False
                self.execute(session, tx,
                             "DECLARE $id AS Int64; DECLARE $lease AS Int64; "
                             "DECLARE $owner AS Utf8; UPDATE subscribers SET lease_until=$lease, "
                             "owner=$owner WHERE chat_id=$id;",
                             {"$id": chat_id, "$lease": now + 120, "$owner": owner})
                return True
        return self.run(operation)

    def finish(self, chat_id: int, owner: str, week: str):
        self.run(lambda session: self.execute(session, session.transaction(),
                 "DECLARE $id AS Int64; DECLARE $owner AS Utf8; DECLARE $week AS Utf8; "
                 "UPDATE subscribers SET sent_week=$week, lease_until=0, next_attempt=0 "
                 "WHERE chat_id=$id AND owner=$owner;",
                 {"$id": chat_id, "$owner": owner, "$week": week}))

    def postpone(self, chat_id: int, owner: str, until: int):
        self.run(lambda session: self.execute(session, session.transaction(),
                 "DECLARE $id AS Int64; DECLARE $owner AS Utf8; DECLARE $until AS Int64; "
                 "UPDATE subscribers SET next_attempt=$until, lease_until=0 "
                 "WHERE chat_id=$id AND owner=$owner;",
                 {"$id": chat_id, "$owner": owner, "$until": until}))

    def health(self):
        self.run(lambda session: self.execute(session, session.transaction(),
                 "SELECT chat_id FROM subscribers LIMIT 1;"))
