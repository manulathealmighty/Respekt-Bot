from models import User, User_in_chat, Telegram_chat, Telegram_message
from typing import Optional, Tuple, List, Dict
import logging


class UserNotFound(Exception):
    pass


class NoUserReactsFound(Exception):
    pass


def get_user_by_user_id(user_id: int, conn) -> User:
    with conn:
        with conn.cursor() as crs:  # I would love type hints here but psycopg2.cursor isn't a defined class
            selectcmd = "SELECT user_id, username, first_name, last_name from telegram_user tu where tu.user_id=%s"
            crs.execute(selectcmd, [user_id])
            res = crs.fetchone()
            return User(res[0], res[1], res[2], res[3])


def get_user_by_username(username: str, conn) -> User:
    with conn:
        with conn.cursor() as crs:  # I would love type hints here but psycopg2.cursor isn't a defined class
            selectcmd = "SELECT user_id, username, first_name, last_name from telegram_user tu where tu.username=%s"
            crs.execute(selectcmd, [username])
            res = crs.fetchone()
            return User(res[0], res[1], res[2], res[3])

# TODO: pass in user_id
# TODO: implement this as a stored procedure instead since there is a number of round trips
# TODO: return some structure and then parse it


def get_user_stats(username: str, chat_id: str, conn) -> Dict:
    user = get_user_by_username(username, conn)
    if user is None:
        raise UserNotFound()
    user_has_reacts = did_user_react_to_messages(username, conn)
    respekt = get_respekt_for_user_in_chat(username, chat_id, conn)
    if respekt is None:
        respekt = 0

    output_dict = None
    if not user_has_reacts:
        output_dict = {
            'username': username,
            'Respekt': respekt,
            'upvotes_given': 0,
            'downvotes_given': 0,
            'total_votes_given': 0,
            'net_respekt_given': 0}
    else:
        # how many reacts given out by user
        how_many_user_reacted_to_stats = """select react_score, count(react_score)from
            (select username, message_id, react_score, react_message_id  from telegram_user tu
            left join user_reacted_to_message urtm on urtm.user_id=tu.user_id
            where tu.username = %s) as sub left join telegram_message tm on  tm.message_id= sub.message_id
            where tm.chat_id=%s group by react_score;"""
        # TODO: implement how many reacts recieved by user
        how_many_reacted_to_user_stats = """"""
        negative_respekt_given = 0
        positive_respekt_given = 0
        result = None
        with conn:
            with conn.cursor() as crs:
                crs.execute(
                    how_many_user_reacted_to_stats, [
                        username, chat_id])
                rows = crs.fetchall()
                # there are only two rows
                for row in rows:
                    if row[0] == -1:
                        negative_karma_given = int(row[1])
                    if row[0] == 1:
                        positive_karma_given = int(row[1])
                result = crs.fetchone()

        # TODO: make this output type a class instead to bundle this info
        output_dict = {
            'username': username,
            'Respekt': respekt,
            'upvotes_given': positive_respekt_given,
            'downvotes_given': negative_respekt_given,
            'total_votes_given': positive_respekt_given + negative_respekt_given,
            'net_respekt_given': positive_respekt_given - negative_respekt_given}
    return output_dict


def get_chat_info(chat_id: str, conn) -> Dict:
    count_reacts_cmd = """select count(tm.message_id) from user_reacted_to_message urtm
left join telegram_message tm ON tm.message_id = urtm.message_id
where tm.chat_id=%s"""
    select_user_with_respekt_count = """
    select count(*) from telegram_chat tc
    left join user_in_chat uic on uic.chat_id = tc.chat_id
    where tc.chat_id=%s
    """
    with conn:
        with conn.cursor() as crs:
            reply_count = None
            user_with_karma_count = None
            message = ""
            crs.execute(count_reacts_cmd, [chat_id])
            result = crs.fetchone()
            if result is not None:
                reply_count = result[0]
            else:
                reply_count = 0

            crs.execute(select_user_with_respekt_count, [chat_id])
            result = crs.fetchone()
            if result is not None:
                user_with_respekt_count = result[0]
            else:
                user_with_respekt_count = 0
            return {'reply_count': reply_count,
                    'user_with_respekt_count': user_with_respekt_count}


# TODO: use user_id instead of username
def did_user_react_to_messages(username: str, conn) -> bool:
    select_user_replies = """select username, message_id, react_score, react_message_id  from telegram_user tu
            left join user_reacted_to_message urtm on urtm.user_id=tu.user_id
            where tu.username = %s"""
    reacted_messages_result = None
    with conn:
        with conn.cursor() as crs:
            crs.execute(select_user_replies, [username])
            reacted_messages_result = crs.fetchone()
            return reacted_messages_result is not None
# TODO: user user_id


def get_user_react_stats(username: str, conn) -> bool:
    print()


def save_or_create_user(user: User, conn) -> User:
    with conn:
        with conn.cursor() as crs:  # I would love type hints here but psycopg2.cursor isn't a defined class
            selectcmd = "SELECT user_id, username, first_name, last_name from telegram_user tu where tu.user_id=%s"
            # TODO: upsert to update values otherwise username, firstname, lastname wont ever change
            #print("user with id: " + str(user_id) + "  not found: creating user")
            insertcmd = """INSERT into telegram_user
            (user_id, username, first_name, last_name) VALUES (%s,%s,%s,%s)
            ON CONFLICT (user_id) DO UPDATE
            SET username = EXCLUDED.username,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name
            """
            crs.execute(insertcmd,
                        [user.get_user_id(),
                         user.get_username(),
                            user.get_first_name(),
                            user.get_last_name()])
            conn.commit()
            crs.execute(selectcmd, [user.get_user_id()])
            (user_id, username, first_name, last_name) = crs.fetchone()
            return User(user_id, username, first_name, last_name)


def does_chat_exist(chat_id: str, conn):
    with conn:
        with conn.cursor() as crs:  # I would love type hints here but psycopg2.cursor isn't a defined class
            selectcmd = "SELECT chat_id, chat_name FROM telegram_chat tc where tc.chat_id=%s"
            crs.execute(selectcmd, [chat_id])
            return crs.fetchone() is not None


def save_or_create_chat(chat: Telegram_chat, conn):
    with conn:
        with conn.cursor() as crs:  # I would love type hints here but psycopg2.cursor isn't a defined class
            insertcmd = """INSERT into telegram_chat
            (chat_id, chat_name) VALUES (%s,%s)
            ON CONFLICT (chat_id) DO UPDATE
            SET chat_name = EXCLUDED.chat_name"""
            crs.execute(insertcmd, [chat.chat_id, chat.chat_name])
            conn.commit()


def create_chat_if_not_exists(chat_id: int, conn):
    with conn:
        with conn.cursor() as crs:  # I would love type hints here but psycopg2.cursor isn't a defined class
            insertcmd = """INSERT into telegram_chat
            (chat_id) VALUES (%s)
            ON CONFLICT (chat_id) DO NOTHING"""
            crs.execute(insertcmd, [chat_id])
            conn.commit()

# if user did not have a karma before, karma will be set to change_karma


def save_or_create_user_in_chat(
        user: User,
        chat_id: str,
        conn,
        change_respekt=0) -> User_in_chat:
    with conn:
        with conn.cursor() as crs:  # I would love type hints here but psycopg2.cursor isn't a defined class
            # TODO: instead of select first, do insert and then trap exception
            # if primary key exists
            selectcmd = "SELECT user_id, chat_id, karma FROM user_in_chat uic where uic.user_id=%s AND uic.chat_id=%s"
            crs.execute(selectcmd, [user.id, chat_id, ])

            result = crs.fetchone()

            insertcmd_respekt = """INSERT into user_in_chat
                (user_id, chat_id, respekt) VALUES (%s,%s,%s)
                ON CONFLICT (user_id,chat_id) DO UPDATE SET respekt = user_in_chat.karma + %s
                RETURNING respekt
                """

            # TODO: used named parameters instead of %s to not have to repeat
            # these params
            crs.execute(
                insertcmd_respekt, [
                    user.get_user_id(), chat_id, change_respekt, change_respekt])

            row = crs.fetchone()
            conn.commit()
            respekt = row[0]
            return User_in_chat(user.id, chat_id, respekt)

# message tg.Message
# reply_message comes after and is the reply


def user_reply_to_message(
        user: User,
        reply_to_user: User,
        chat: Telegram_chat,
        original_message: Telegram_message,
        reply_message: Telegram_message,
        respekt: int,
        conn):
    user: User = save_or_create_user(user, conn)
    reply_to_user: User = save_or_create_user(reply_to_user, conn)
    if not does_chat_exist(chat.chat_id, conn):
        save_or_create_chat(chat, conn)

    uic: User_in_chat = save_or_create_user_in_chat(user, chat.chat_id, conn)
    reply_to_uic: User_in_chat = save_or_create_user_in_chat(
        reply_to_user, chat.chat_id, conn)

    insert_message = """INSERT INTO telegram_message
    (message_id,chat_id, author_user_id, message_text)
    VALUES (%s,%s,%s,%s)
    ON CONFLICT (message_id) DO UPDATE
    SET message_text = EXCLUDED.message_text;
    """
    selecturtm = """SELECT * from user_reacted_to_message urtm where urtm.user_id=%s and urtm.message_id=%s and urtm.react_message_id=%s"""
    inserturtm = """INSERT INTO user_reacted_to_message
    (user_id,message_id,react_score,react_message_id)
    VALUES (%s,%s,%s,%s)"""

    # TODO: manage this with a constraint rather than having to select
    selecturtmunique = """SELECT react_score from user_reacted_to_message urtm where urtm.user_id=%s and urtm.message_id=%s"""
    # none if user hasn't reacted yet
    user_previous_react = None
    with conn:
        with conn.cursor() as crs:
            args_select_urtm = [uic.user_id, original_message.message_id]
            crs.execute(selecturtmunique, args_select_urtm)
            result = crs.fetchone()
            if result is not None:
                user_previous_react = result[0]

    # TODO: add gaurd for karma == 1 or == -1 up higher
    if user_previous_react is None or user_previous_react != respekt:
        if(respekt == 1 or respekt == -1):
            save_or_create_user_in_chat(
                reply_to_user, chat.chat_id, conn, change_respekt=respekt)
        else:
            logging.info(
                f"invalid respekt: {karma} passed to user_reply_to_message")
        with conn:
            with conn.cursor() as crs:
                args_reply_message = [
                    reply_message.message_id,
                    chat.chat_id,
                    uic.user_id,
                    reply_message.message_text]
                args_original_message = [
                    original_message.message_id,
                    chat.chat_id,
                    original_message.author_user_id,
                    original_message.message_text]
                crs.execute(insert_message, args_reply_message)
                crs.execute(insert_message, args_original_message)
                argsurtm = [
                    uic.user_id,
                    original_message.message_id,
                    karma,
                    reply_message.message_id]
                crs.execute(inserturtm, argsurtm)


def get_respekt_for_user_in_chat(
        username: str,
        chat_id: str,
        conn) -> Optional[int]:
    cmd = """select respekt from telegram_user tu
        LEFT JOIN user_in_chat uic ON uic.user_id=tu.user_id
        where tu.username=%s AND uic.chat_id=%s"""
    with conn:
        with conn.cursor() as crs:
            # TODO: handle | psycopg2.ProgrammingError: relation "user_in_chat"
            # does not exist
            crs.execute(cmd, [username, chat_id])
            result = crs.fetchone()
            if result is not None:
                return result[0]
            return result


def get_respekt_for_users_in_chat(
        chat_id: str, conn) -> List[Tuple[str, str, int]]:
    cmd = """select username, first_name, respekt from telegram_user tu
        LEFT JOIN user_in_chat uic ON uic.user_id=tu.user_id
        where uic.chat_id=%s;"""
    with conn:
        with conn.cursor() as crs:
            # TODO: handle | psycopg2.ProgrammingError: relation "user_in_chat"
            # does not exist
            crs.execute(cmd, [chat_id])
            return crs.fetchall()


def get_message_responses_for_user_in_chat(user_id: int, chat_id: int, conn):
    cmd = """    SELECT sub3.user_id, sub3.message_id, sub3.response_text AS message_text, urtm.react_score,
        urtm.react_message_id, sub3.username AS responder_username, sub3.first_name AS responder_first_name,
         sub3.last_name AS responder_last_name  FROM (
        SELECT  sub2.user_id, tm.message_id, tm.message_text AS response_text,  uic_id ,
            sub2.username, sub2.first_name, sub2.last_name FROM (
            SELECT uic_id, sub.user_id, sub.karma, tu.username, tu.first_name, tu.last_name FROM (
                SELECT id AS uic_id, a.user_id, chat_id, karma FROM (
                    select * from user_in_chat uic where uic.user_id = %s AND uic.chat_id=%s
                    ) as a
            ) AS sub
            LEFT JOIN telegram_user tu ON tu.user_id=sub.user_id) AS sub2
        LEFT JOIN telegram_message tm ON uic_id=tm.author_user_in_chat_id) AS sub3
    LEFT JOIN user_reacted_to_message urtm ON urtm.message_id = sub3.message_id;"""
    with conn:
        with conn.cursor() as crs:
            crs.execute(cmd, [user_id, chat_id])
            return crs.fetchall()
