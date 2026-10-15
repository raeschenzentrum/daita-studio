LOCKING ROW FOR ACCESS
SELECT TOP 20
    r.start_time                                 AS STARTZEIT,
    j.job_name                                   AS JOB,
    SUBSTR(COALESCE(r.error_message, ''), 1, 160) AS FEHLER
FROM ${META_SCHEMA}.META_ETL_JOB_RUN r
JOIN ${META_SCHEMA}.META_ETL_JOB j ON j.etl_job_id = r.etl_job_id
WHERE CAST(r.start_time AS DATE) >= CURRENT_DATE - ${FILTER:tage}
  AND r.status = 'FAILED'
ORDER BY r.start_time DESC
