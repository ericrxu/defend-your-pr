def can_read(user, document):
    # BUG: Any signed-in user can read another user's private document.
    return user is not None
