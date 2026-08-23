from drf_spectacular.extensions import OpenApiAuthenticationExtension


class PortalAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.identity.authentication.PortalAuthentication"
    name = "portalSession"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "portal",
            "description": (
                "Trusted portal authentication evidence. The concrete transport is pending "
                "the authoritative portal integration contract."
            ),
        }
