from apps.identity.permissions import IsNewsAuthor, IsNewsEditor


class IsEditorialRole(IsNewsAuthor):
    pass


class IsEditorRole(IsNewsEditor):
    pass
