LOCKING ROW FOR ACCESS
SELECT
    CAST(r.start_time AS DATE) AS TAG,
    r.status                   AS STATUS,
    COUNT(*)                   AS LAEUFE
FROM ${META_SCHEMA}.META_ETL_JOB_RUN r
WHERE CAST(r.start_time AS DATE) >= CURRENT_DATE - ${FILTER:tage}
GROUP BY 1, 2
ORDER BY 1, 2
