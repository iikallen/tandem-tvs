from django.db import migrations

CREATE_SEARCH = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE TEXT SEARCH DICTIONARY public.tandem_kk_dict (
    TEMPLATE = pg_catalog.ispell,
    DictFile = tandem_kk,
    AffFile = tandem_kk
);
CREATE TEXT SEARCH CONFIGURATION public.tandem_kazakh (COPY = pg_catalog.simple);
ALTER TEXT SEARCH CONFIGURATION public.tandem_kazakh
    ALTER MAPPING FOR asciiword, asciihword, hword_asciipart, word, hword, hword_part
    WITH public.tandem_kk_dict, pg_catalog.simple;
"""

DROP_SEARCH = """
DROP TEXT SEARCH CONFIGURATION IF EXISTS public.tandem_kazakh;
DROP TEXT SEARCH DICTIONARY IF EXISTS public.tandem_kk_dict;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("discussions", "0003_remove_legacy_notification"),
        ("identity", "0008_user_last_activity_at"),
        ("messenger", "0003_conversation_discussion_enabled_and_more"),
        ("publications", "0010_mediaasset_is_messenger_only"),
    ]

    operations = [migrations.RunSQL(CREATE_SEARCH, DROP_SEARCH)]
