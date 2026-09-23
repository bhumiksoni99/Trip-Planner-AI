"""Which chat belongs to whom.

The conversation itself stays where LangGraph already puts it: the checkpoints, keyed by thread_id.
These rows only record who owns a chat, what it's called and when it was last used, so a chat is
never stored twice. A chat with no row here belongs to nobody yet, which is how a guest's chats
look until they log in and claim them.
"""
import db


def owner_of(thread_id: str) -> str | None:
    rows = db.fetch("SELECT user_id::text AS user_id FROM chats WHERE thread_id = %s", (thread_id,))
    return rows[0]["user_id"] if rows else None


def readable_by(thread_id: str, user: dict | None) -> bool:
    """Its owner can read a chat. So can anyone holding the id of a chat nobody owns, which is how a
    guest reads their own: the id is a 32-character random string only their browser has."""
    owner = owner_of(thread_id)
    return owner is None or (user is not None and owner == user["id"])


def list_for(user_id: str) -> list[dict]:
    return db.fetch(
        """
        SELECT thread_id AS id, title, (extract(epoch FROM updated_at) * 1000)::bigint AS "updatedAt"
        FROM chats WHERE user_id = %s ORDER BY updated_at DESC LIMIT 200
        """,
        (user_id,),
    )


def remember(thread_id: str, user_id: str, title: str) -> None:
    """Record a new chat for this user, or mark an existing one as just used"""
    db.execute(
        """
        INSERT INTO chats (thread_id, user_id, title) VALUES (%s, %s, %s)
        ON CONFLICT (thread_id) DO UPDATE SET updated_at = now()
        WHERE chats.user_id = EXCLUDED.user_id
        """,
        (thread_id, user_id, title),
    )


def touch(thread_id: str, user_id: str) -> None:
    db.execute("UPDATE chats SET updated_at = now() WHERE thread_id = %s AND user_id = %s", (thread_id, user_id))


def title_of_chat(thread_id: str) -> str | None:
    rows = db.fetch("SELECT title FROM chats WHERE thread_id = %s", (thread_id,))
    return rows[0]["title"] if rows else None


def delete(thread_id: str, user_id: str) -> bool:
    """True when a chat of this user's was deleted, False when it isn't theirs or doesn't exist"""
    return db.execute("DELETE FROM chats WHERE thread_id = %s AND user_id = %s", (thread_id, user_id)) > 0


def claim(thread_ids: list[str], user_id: str, title_for) -> list[str]:
    """Hand a guest's chats to the account they just logged into.

    Chats someone already owns are left alone, so a stray id can't take another person's chat, and
    running this twice changes nothing."""
    claimed = []
    for thread_id in thread_ids:
        rows = db.fetch(
            """
            INSERT INTO chats (thread_id, user_id, title) VALUES (%s, %s, %s)
            ON CONFLICT (thread_id) DO NOTHING RETURNING thread_id
            """,
            (thread_id, user_id, title_for(thread_id)),
        )
        if rows:
            claimed.append(thread_id)
    return claimed
