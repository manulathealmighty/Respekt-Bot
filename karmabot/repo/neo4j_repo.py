"""Module used to encapsulate database query logic"""
from py2neo import Graph
from karmabot.models.neo4j_models import User, Chat, Message
from typing import List, Tuple, Dict, Optional

# ------------- Database helpers ---------------

def get_model_user_from_graph_user(user: Dict) -> User:
    """ Converts neo4j database user into application logic user"""
    return User(user["id"], user["username"])


def get_model_chat_from_graph_chat(chat: Dict) -> Chat:
    """ Converts neo4j database user into application logic user"""
    return Chat(chat["id"], chat["name"])


def convert_vote_types_from_dict_to_tuple(data: List, type_key, count_key) -> Tuple[int, int]:
    """Requires order by type_key asc otherwise not guaranteed correct
    Data is a list.
    If list has 0 things then 0 positive and 0 negative votes were given.
    If list has 1 things then type_key might be 1 for positive or -1 for negative vote.
    If list has 2 things then the first one should be positive due to vote by asc

    :return: (positive votes, negative votes)
    """
    if len(data) == 0:
        return 0, 0
    if len(data) == 1:
        row = data[0]
        if row[type_key] == 1:
            return row[count_key], 0
        else:
            return 0, row[count_key]
    if len(data) == 2:
        # query uses order by asc so [0] is positive
        return data[1][count_key], data[0][count_key]

    return 0, 0


# ------------- Database calls ---------------

def get_all_users(g: Graph) -> List[User]:
    """
    :param g:
    :return: Returns all users in the database
    """
    data = g.run("MATCH (n:User) return collect(n) as users").data()
    if len(data) == 0:
        return []

    users = [get_model_user_from_graph_user(user) for user in data[0]["users"]]
    return users

def get_user(g: Graph, user_id: str)-> Optional[User]:
    data = g.run("MATCH (n:User) where n.id = {user_id} return n as user", {"user_id": user_id}).data()
    if data == []:
        return None
    #TODO: consider raising exception here
    if len(data) > 1:
        return None
    else:
        return get_model_user_from_graph_user(data[0]["user"])


def get_users_in_chat(g: Graph, chat_id: str) -> Optional[Tuple[List[User], Chat]]:
    """ Returns all the users in a given chat. If chat does not exist returns none
    TODO: throw exception if chat not found?
    :param g:
    :param chat_id:
    :return: Tuple of list of users and chat they are a member of. None if chat does not exist.
    """

    command = "MATCH (n:User)-[:USER_IN_CHAT]-> (chat:Chat) where chat.id={chat_id} return collect(n) as users, chat"
    data = g.run(command, {"chat_id": chat_id}).data()
    if len(data) == 0:
        return None

    users = [get_model_user_from_graph_user(user) for user in data[0]["users"]]
    chat = get_model_chat_from_graph_chat(data[0]["chat"])

    return users, chat


def get_message(g: Graph, message_id: str) -> Message:
    command = """MATCH (user:User)-[:AUTHORED_MESSAGE]->(m:Message)-[:WRITTEN_IN_CHAT]->(chat:Chat) 
    where m.id = {message_id} 
    return m.id as id, m.text as message_text, chat.id as chat_id, user.id as author_user_id"""
    data = g.run(command, {"message_id": message_id}).data()
    if data == []:
        return None
    if len(data) > 1:
        return None #raise exception but should be handled by constraint
    else:
        result = data[0]
        return Message(result["id"], result["chat_id"], result["author_user_id"], result["message_text"])


def get_karma_given_by_user_in_chat(g: Graph, user_id: str, chat_id: str) -> Tuple[int, int]:
    """Given a user and a chat, returns how much karma that user has given in that chat; seperated by positive and negative

    :param g: The graph
    :param user_id:
    :param chat_id:
    :return: (positive votes, negative votes)
    """
    command = """MATCH (user:User)-[:AUTHORED_MESSAGE]->(message:Message)-[r:REPLIED_TO]->(message_replied_to:Message)
    MATCH (message:Message)-[:WRITTEN_IN_CHAT]->(chat:Chat)
    where user.id= {user_id}
    and chat.id= {chat_id}
    return distinct(r.vote) as vote_type, count(r.vote) as vote_count
    order by vote_type asc;"""

    data = g.run(command, {"user_id": user_id, "chat_id": chat_id}).data()
    return convert_vote_types_from_dict_to_tuple(data, "vote_type", "vote_count")


def get_karma_received_by_user_in_chat(g: Graph, user_id: str, chat_id: str) -> Tuple[int,int]:
    """Get number of positive and negative votes received by a user in a chat.

    :param g:
    :param user_id:
    :param chat_id:
    :return: tuple of [positive vote count, negative vote count]: default to 0
    """
    command = """MATCH (user:User)-[:AUTHORED_MESSAGE]->(message_replied_to:Message)<-[r:REPLIED_TO]-(message:Message)
    MATCH (message:Message)-[:WRITTEN_IN_CHAT]->(chat:Chat)
    where user.id= {user_id}
    and chat.id= {chat_id}
    return distinct(r.vote) as vote_type, count(r.vote) as vote_count
    order by vote_type asc;"""
    data = g.run(command, {"user_id": user_id, "chat_id": chat_id}).data()
    return convert_vote_types_from_dict_to_tuple(data, "vote_type", "vote_count")


def get_message(g: Graph, message_id: str) -> Optional[Message]:
    """
    Get message for message_id and construct message object that includes user_id and chat_id
    #TODO: handle case where message lacks relationship to user and chat
    :param g:
    :param message_id:
    :return: message if exists, otherwise none.
    """
    commmand = """
    MATCH (user:User)-[:AUTHORED_MESSAGE]->(message:Message)-[:WRITTEN_IN_CHAT]->(chat:Chat)
    WHERE message.id = {id}
    return user, message, chat
    """
    data = g.run(commmand, {"id": message_id}).data()
    if data == []:
        return None
    result = data[0]
    user = get_model_user_from_graph_user(result['user'])
    chat = get_model_chat_from_graph_chat(result['chat'])
    m = result['message']
    message = Message(m['id'], chat.chat_id, user.user_id, m['text'])
    return message


def create_or_update_message(g: Graph, message: Message):
    """
    Store message with relationship to user and chat in database.
    :param g:
    :param message:
    :return:
    """
    command = """
    MATCH (user:User), (chat:Chat)
    where user.id = {user_id} AND chat.id = {chat_id}
    MERGE (user)-[:AUTHORED_MESSAGE]->(message:Message {id: {message_id}})-[:WRITTEN_IN_CHAT]
    ->(chat)
    ON CREATE SET message.created = timestamp(), message.text = {text}
    ON MATCH SET
    message.accessTime = timestamp(), message.text = {text}
    """
    #TODO: handle failure cases (what if user or chat doesn't exist?)
    data = g.run(command, {"user_id": message.author_user_id,
                           "chat_id": message.chat_id,
                           "message_id": message.message_id,
                           "text": message.message_text
                           }).data()
    return data


def get_karma_for_user_in_chat(g: Graph, user_id: str, chat_id: str) -> Optional[int]:
    """Return the karma a user has in a given chat. Stored on relationship to chat.
    #TODO: return optional or 0 by default?
    :param g:
    :param user_id:
    :param chat_id:
    :return:
    """
    get_user_karma_command = """
    MATCH (user:User)-[r:USER_IN_CHAT]->(chat:Chat)
    WHERE user.id = {user_id} AND chat.id = {chat_id}
    return r.karma as karma"""

    result = g.run(get_user_karma_command,
                   {"user_id": user_id,
                    "chat_id": chat_id}).data()

    if len(result) == 0:
        return None
    else:
        return result[0]["karma"]

def get_karma_for_users_in_chat(g: Graph, chat_id: str) -> List[Tuple[User, int]]:
    """Return the karma for all users in a given chat.
    #TODO: Should this return list of tuples, list of named tuples, class, or dict?
    :param g:
    :param user_id:
    :param chat_id:
    :return:
    """
    get_user_karma_command = """
    MATCH (user:User)-[r:USER_IN_CHAT]->(chat:Chat)
    WHERE chat.id = {chat_id}
    return user, r.karma as karma"""

    result = g.run(get_user_karma_command,
                   {"chat_id": chat_id}).data()

    # TODO: verify behavior when chat doesn't exist
    if len(result) == 0:
        return []
    else:
        user_result = list(map(lambda x: (get_model_user_from_graph_user(x['user']), x['karma']), result))
        return user_result


def vote_on_message(g: Graph, reply_message: Message, reply_to_message: Message, vote: int):
    """ Applies a karma vote to a user for a given message.
    #TODO: raise exceptions for error conditions such as invalid message, vote, etc
    #TODO: check if vote already given: how?

    :param g: graph to operate on
    :param reply_message: message with the +1 or -1
    :param reply_to_message: message being replied to
    :param vote: the value of the vote being applied. should only be 1 or -1 (filtered by server)
    :return:
    """
    #give karma to author of reply_to_message
    #make sure messages are saved
    #create replied to relationship frmo reply to replied
    assert vote in [-1, 1]
    create_or_update_message(g, reply_message)
    create_or_update_message(g, reply_to_message)

    check_if_user_already_voted_cmd = """
    MATCH (user:User)-[:AUTHORED_MESSAGE]->(reply_message:Message)-[r:REPLIED_TO]->(reply_to_message:Message)
    where  user.id = {user_id} AND reply_to_message.id = {reply_to_message_id}
    return r.vote as vote
    """
    result = g.run(check_if_user_already_voted_cmd,
                   {"user_id": reply_message.author_user_id,
                    "reply_to_message_id": reply_to_message.message_id}).data()

    if len(result) >= 1:# was already replied to
        existing_vote = result[0]['vote']
        if vote == existing_vote:
            return
        else:
            vote = 2 * vote
    #TODO: override existing react relation

    # if vote matches vote value then do nothing
    # else add (-2)*vote to karma

    #TODO: test that this relationship is created when it doesn't exist
    update_user_karma_command = """
    MERGE (user:User {id: {user_id}})
    -[r:USER_IN_CHAT]->(chat1)
    ON MATCH SET
    r.karma  = r.karma + {vote}
    ON CREATE SET
    r.karma = {vote}
    """
    g.run(update_user_karma_command,
                 {"user_id": reply_to_message.author_user_id,
                  "vote": vote}).data()

    create_react_relation = """
    MATCH (reply_message:Message), (reply_to_message:Message) 
    where  reply_message.id = {reply_message_id} AND reply_to_message.id = {reply_to_message_id}
    MERGE (reply_message)-[r:REPLIED_TO]->(reply_to_message)
    ON MATCH SET
    r.vote = {vote}
    ON CREATE SET
    r.vote = {vote}
    """

    result = g.run(create_react_relation,
                   {"reply_message_id": reply_message.message_id,
                    "reply_to_message_id": reply_to_message.message_id,
                       "vote": vote}).data()
    return result
