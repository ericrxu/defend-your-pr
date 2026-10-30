from .auth import can_read
from .search import unique_tags


def list_tags(user, documents):
    visible = [doc for doc in documents if can_read(user, doc)]
    return unique_tags(visible)
