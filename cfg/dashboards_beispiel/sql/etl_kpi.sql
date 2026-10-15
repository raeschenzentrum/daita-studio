LOCKING ROW FOR ACCESS
SELECT
    COUNT(*)                                                         AS LAEUFE,
    SUM(CASE WHEN r.status = 'FAILED' THEN 1 ELSE 0 END)             AS FEHLER,
    CAST(100.0 * SUM(CASE WHEN r.status = 'SUCCESS' THEN 1 ELSE 0 END)
         / NULLIF(SUM(CASE WHEN r.status IN ('SUCCESS', 'FAILED') THEN 1 ELSE 0 END), 0)
         AS DECIMAL(5,1))                                            AS ERFOLGSQUOTE,
    CAST(AVG(r.duration_seconds) AS DECIMAL(12,1))                   AS DAUER_AVG_S
FROM ${META_SCHEMA}.META_ETL_JOB_RUN r
WHERE CAST(r.start_time AS DATE) >= CURRENT_DATE - ${FILTER:tage}
