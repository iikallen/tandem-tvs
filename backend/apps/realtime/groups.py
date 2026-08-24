def user_control_group(user_id: object) -> str:
    return f"user.{user_id}.control"


def publication_group(publication_id: object) -> str:
    return f"publication.{str(publication_id).replace('-', '')}"


def conversation_group(conversation_id: object) -> str:
    return f"conversation.{str(conversation_id).replace('-', '')}"
