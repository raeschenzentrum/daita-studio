LOCKING ROW FOR ACCESS
SELECT
    CAST(r.start_time AS DATE)                      AS TAG,
    CAST(AVG(r.duration_seconds) AS DECIMAL(12,1))  AS DAUER_AVG_S
FROM ${META_SCHEMA}.META_ETL_JOB_RUN r
WHERE CAST(r.start_time AS DATE) >= CURRENT_DATE - ${FILTER:tage}
  AND r.status = 'SUCCESS'
GROUP BY 1
ORDER BY 1
