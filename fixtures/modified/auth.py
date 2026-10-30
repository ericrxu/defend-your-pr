def can_read(user, document):
    if user is None:
        return False
    return document['public'] or document['owner_id'] == user['id']
