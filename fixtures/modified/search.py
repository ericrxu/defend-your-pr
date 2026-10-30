def unique_tags(documents):
    seen = set()
    tags = []
    for document in documents:
        for tag in document['tags']:
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
    return tags
