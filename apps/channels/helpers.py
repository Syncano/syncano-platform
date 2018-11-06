# coding=UTF8


def create_author_dict(request):
    author = {}
    if request.user.is_authenticated:
        author['admin'] = request.user.id
    else:
        author['api_key'] = request.auth.id
        if request.auth_user:
            author['user'] = request.auth_user.id
    return author
