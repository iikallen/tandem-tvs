def user_control_group(user_id: object) -> str:
    return f"user.{user_id}.control"


def session_control_group(fingerprint: str) -> str:
    return f"session.{fingerprint[:48]}.control"


def messenger_user_group(user_id: object) -> str:
    return f"messenger.user.{user_id}"


def publication_group(publication_id: object) -> str:
    return f"publication.{str(publication_id).replace('-', '')}"


def conversation_group(conversation_id: object) -> str:
    return f"conversation.{str(conversation_id).replace('-', '')}"


def notification_group(user_id: object) -> str:
    return f"notification.{user_id}"
