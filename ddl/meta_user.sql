-- ============================================================================
-- META_USER – Benutzer + Rolle für daita-studio RBAC
-- ============================================================================
-- Schema: MDP01_META (siehe cfg/database.yml -> metadata.schema)
-- Wird vom Backend / bin/create_user.py bei Bedarf automatisch angelegt.
-- Rollen: 'Viewer' | 'Editor' | 'Admin'
-- ============================================================================

CREATE TABLE MDP01_META.META_USER (
    USER_ID       INTEGER GENERATED ALWAYS AS IDENTITY
                  (START WITH 1 INCREMENT BY 1 MINVALUE 1
                   MAXVALUE 2147483647 NO CYCLE) NOT NULL,
    USERNAME      VARCHAR(128) CHARACTER SET UNICODE NOT CASESPECIFIC NOT NULL,
    PASSWORD_HASH VARCHAR(256) CHARACTER SET LATIN NOT CASESPECIFIC NOT NULL,
    USER_ROLE     VARCHAR(16)  CHARACTER SET LATIN NOT CASESPECIFIC NOT NULL,
    IS_ACTIVE     BYTEINT NOT NULL DEFAULT 1,
    CREATED_AT    TIMESTAMP(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0),
    UPDATED_AT    TIMESTAMP(0) NOT NULL DEFAULT CURRENT_TIMESTAMP(0)
)
UNIQUE PRIMARY INDEX (USERNAME);
