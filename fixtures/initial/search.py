def unique_tags(documents):
    tags = []
    for document in documents:
        for tag in document['tags']:
            if tag not in tags:
                tags.append(tag)
    return tags
